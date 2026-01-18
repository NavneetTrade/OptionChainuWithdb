"""
Background Service for Continuous Option Chain Data Fetching
Runs independently to fetch data for all configured symbols
"""

import time
import logging
import signal
import sys
import math
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import pytz
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
import os
import toml
import numpy as np
from dataclasses import dataclass

from database import TimescaleDBManager
from upstox_api import UpstoxAPI
from token_manager import get_token_manager
from auto_token_refresh import UpstoxTokenRefresher

# WebSocket implementation removed - using REST API only

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('background_service.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Note: Sentiment calculation is done ONLY in Option Chain Analysis (optionchain.py)
# Background Service only fetches and stores raw option chain data
# Sentiment is calculated on-the-fly in Option Chain Analysis and then stored

IST = pytz.timezone('Asia/Kolkata')


@dataclass
class GammaBlastSignal:
    """Real-time gamma blast signal with adaptive thresholds"""
    probability: float  # 0-1
    direction: str  # UP/DOWN/NEUTRAL
    confidence: str  # LOW/MEDIUM/HIGH/CRITICAL
    time_to_blast_min: int
    triggers: List[str]  # What caused high probability
    risk_level: str  # LOW/ELEVATED/HIGH/EXTREME


class AdaptiveGammaBlastDetector:
    """
    Adaptive gamma blast detector using statistical z-scores
    instead of constant thresholds
    """
    
    def __init__(self, lookback_periods: int = 20):
        self.lookback = lookback_periods
        
    @staticmethod
    def calculate_z_score_or_threshold(current: float, historical: List[float], fallback_threshold: float = 0) -> float:
        """Calculate z-score with fallback for insufficient data
        
        Args:
            current: Current value to evaluate
            historical: Historical values for statistical comparison
            fallback_threshold: Absolute threshold to use when insufficient data
            
        Returns:
            Z-score if sufficient data (>=10), percentile-based score (>=3), 
            or threshold-based score (0/1/-1) for sparse data
        """
        if len(historical) >= 10:  # Use z-score if sufficient data
            mean = np.mean(historical)
            std = np.std(historical)
            return (current - mean) / std if std > 0 else 0
        elif len(historical) >= 3:  # Use percentile-based for sparse data
            p75 = np.percentile(historical, 75)
            p25 = np.percentile(historical, 25)
            if current > p75:
                return 1  # Above 75th percentile
            elif current < p25:
                return -1  # Below 25th percentile
            else:
                return 0  # Within normal range
        else:  # Fallback to absolute threshold for very sparse data
            if fallback_threshold > 0:
                return 1 if current > fallback_threshold else 0
            else:
                return 0
    
    def detect_gamma_blast(
        self,
        symbol: str,
        current_data: dict,
        historical_data: List[dict]
    ) -> GammaBlastSignal:
        """
        Detect gamma blast using adaptive statistical thresholds
        
        Args:
            symbol: Trading symbol
            current_data: Current metrics {iv, oi, gamma_conc, gex, etc}
            historical_data: List of past metrics (last 20+ periods)
        """
        
        # Store individual signal strengths (each normalized 0-1)
        signals = {}
        triggers = []
        
        # Extract current metrics
        curr_iv = current_data.get('atm_iv', 0)
        curr_oi = current_data.get('atm_oi', 0)
        curr_gamma_conc = current_data.get('gamma_concentration', 0)
        curr_gex = current_data.get('net_gex', 0)
        spot = current_data.get('spot_price', 0)
        atm_strike = current_data.get('atm_strike', 0)
        
        # Build historical arrays
        hist_iv = [d.get('atm_iv', 0) for d in historical_data if d.get('atm_iv', 0) > 0]
        hist_oi = [d.get('atm_oi', 0) for d in historical_data if d.get('atm_oi', 0) > 0]
        hist_gamma_conc = [d.get('gamma_concentration', 0) for d in historical_data]
        hist_gex = [d.get('net_gex', 0) for d in historical_data]
        
        # SIGNAL 1: IV Z-Score Spike (normalized 0-1)
        # Fallback threshold: IV > 30 for indices/stocks is elevated
        iv_zscore = self.calculate_z_score_or_threshold(curr_iv, hist_iv, fallback_threshold=30)
        
        if len(hist_iv) >= 10:  # Z-score interpretation
            if iv_zscore > 2.5:  # 2.5 std devs above mean
                signals['iv'] = 1.0
                triggers.append(f"IV Spike ({iv_zscore:.1f}σ)")
            elif iv_zscore > 2.0:
                signals['iv'] = 0.6
                triggers.append(f"IV Elevated ({iv_zscore:.1f}σ)")
            elif iv_zscore < -2.0:  # IV collapsing
                signals['iv'] = 0.6  # IV collapse also predictive
                triggers.append(f"IV Collapse ({iv_zscore:.1f}σ)")
            else:
                # Linear scale from 1σ to 2.5σ
                signals['iv'] = max(0, min(1.0, (abs(iv_zscore) - 1.0) / 1.5))
        elif len(hist_iv) >= 3:  # Percentile interpretation
            if iv_zscore > 0:  # Above 75th percentile
                signals['iv'] = 0.8
                triggers.append("IV Elevated (>P75)")
            elif iv_zscore < 0:  # Below 25th percentile
                signals['iv'] = 0.6
                triggers.append("IV Collapsed (<P25)")
            else:
                signals['iv'] = 0.3
        elif iv_zscore > 0:  # Absolute threshold
            signals['iv'] = 0.5
            triggers.append(f"IV High (>{curr_iv:.1f})")
        else:
            signals['iv'] = 0.0
        
        # SIGNAL 2: OI Acceleration (2nd derivative with adaptive threshold)
        if len(historical_data) >= 3:
            # Calculate acceleration using last 3 points
            oi_series = [
                historical_data[-3].get('atm_oi', 0), 
                historical_data[-2].get('atm_oi', 0),
                curr_oi
            ]
            
            velocity_1 = oi_series[1] - oi_series[0]
            velocity_2 = oi_series[2] - oi_series[1]
            acceleration = velocity_2 - velocity_1
            
            # Build historical accelerations for z-score
            hist_accelerations = []
            for i in range(2, len(historical_data)):
                v1 = historical_data[i-1].get('atm_oi', 0) - historical_data[i-2].get('atm_oi', 0)
                v2 = historical_data[i].get('atm_oi', 0) - historical_data[i-1].get('atm_oi', 0)
                hist_accelerations.append(v2 - v1)
            
            if hist_accelerations:
                # Fallback: acceleration > 10000 for stocks, > 1000 for indices is significant
                fallback_accel = 1000 if curr_oi < 1000000 else 10000
                accel_zscore = self.calculate_z_score_or_threshold(acceleration, hist_accelerations, fallback_threshold=fallback_accel)
                
                if len(hist_accelerations) >= 10:  # Z-score interpretation
                    if accel_zscore < -2.0:  # Rapid unwinding (2σ below mean)
                        signals['oi_accel'] = 1.0  # Unwinding most predictive
                        triggers.append(f"OI Unwinding ({accel_zscore:.1f}σ)")
                    elif accel_zscore > 2.0:  # Rapid buildup (2σ above mean)
                        signals['oi_accel'] = 0.7  # Buildup somewhat predictive
                        triggers.append(f"OI Buildup ({accel_zscore:.1f}σ)")
                    else:
                        # Linear scale for moderate z-scores
                        signals['oi_accel'] = max(0, abs(accel_zscore) / 2.5)
                elif len(hist_accelerations) >= 3:  # Percentile interpretation
                    if accel_zscore < 0:  # Below 25th percentile (unwinding)
                        signals['oi_accel'] = 0.8
                        triggers.append("OI Unwinding (<P25)")
                    elif accel_zscore > 0:  # Above 75th percentile (buildup)
                        signals['oi_accel'] = 0.6
                        triggers.append("OI Buildup (>P75)")
                    else:
                        signals['oi_accel'] = 0.3
                elif abs(accel_zscore) > 0:  # Absolute threshold
                    if acceleration < 0:
                        signals['oi_accel'] = 0.6
                        triggers.append(f"OI Unwinding ({acceleration:.0f})")
                    else:
                        signals['oi_accel'] = 0.4
                        triggers.append(f"OI Buildup ({acceleration:.0f})")
                else:
                    signals['oi_accel'] = 0.0
            else:
                signals['oi_accel'] = 0.0
        else:
            signals['oi_accel'] = 0.0
        
        # SIGNAL 3: Gamma Concentration Expansion (normalized 0-1)
        # Fallback: concentration > 60% is high clustering
        gamma_zscore = self.calculate_z_score_or_threshold(curr_gamma_conc, hist_gamma_conc, fallback_threshold=0.6)
        
        if len(hist_gamma_conc) >= 10:
            if gamma_zscore > 2.0:
                signals['gamma_conc'] = 1.0
                triggers.append(f"Gamma Clustering ({gamma_zscore:.1f}σ)")
            else:
                signals['gamma_conc'] = max(0, min(1.0, gamma_zscore / 2.5))
        elif len(hist_gamma_conc) >= 3:
            if gamma_zscore > 0:  # Above 75th percentile
                signals['gamma_conc'] = 0.8
                triggers.append("Gamma Clustering (>P75)")
            else:
                signals['gamma_conc'] = 0.0
        elif gamma_zscore > 0:  # Absolute threshold
            signals['gamma_conc'] = 0.6
            triggers.append(f"High Gamma Conc ({curr_gamma_conc:.1%})")
        else:
            signals['gamma_conc'] = 0.0
        
        # SIGNAL 4: Strike Pin Risk (normalized 0-1)
        if atm_strike > 0:
            distance_pct = abs(spot - atm_strike) / spot * 100
            if distance_pct < 0.3:  # Very close to ATM
                signals['pin_risk'] = 1.0
                triggers.append(f"Pin Risk ({distance_pct:.2f}%)")
            elif distance_pct < 0.5:
                signals['pin_risk'] = 0.6
                triggers.append(f"Pin Risk ({distance_pct:.2f}%)")
            elif distance_pct < 1.0:
                signals['pin_risk'] = 0.3
            else:
                signals['pin_risk'] = 0.0
        else:
            signals['pin_risk'] = 0.0
        
        # SIGNAL 5: GEX Flip Detection (normalized 0-1)
        if len(hist_gex) > 0:
            prev_gex = hist_gex[-1]
            if (prev_gex > 0 and curr_gex < 0) or (prev_gex < 0 and curr_gex > 0):
                # Check magnitude of flip
                flip_magnitude = abs(curr_gex - prev_gex)
                if flip_magnitude > abs(prev_gex) * 0.5:  # Significant flip
                    signals['gex_flip'] = 1.0
                    triggers.append("GEX Flip Detected (Strong)")
                else:
                    signals['gex_flip'] = 0.6
                    triggers.append("GEX Flip Detected")
            else:
                signals['gex_flip'] = 0.0
        else:
            signals['gex_flip'] = 0.0
        
        # SIGNAL 6: GEX Extremes (normalized 0-1)
        if len(hist_gex) >= 10:
            gex_percentile = (sum(1 for g in hist_gex if g <= curr_gex) / len(hist_gex)) * 100
            if gex_percentile > 95:  # Top 5% (extreme resistance)
                signals['gex_extreme'] = 1.0
                triggers.append(f"Extreme GEX ({gex_percentile:.0f}th percentile)")
            elif gex_percentile > 90:  # Top 10%
                signals['gex_extreme'] = 0.7
                triggers.append(f"High GEX ({gex_percentile:.0f}th percentile)")
            elif gex_percentile < 5:  # Bottom 5% (extreme support)
                signals['gex_extreme'] = 1.0
                triggers.append(f"Extreme GEX ({gex_percentile:.0f}th percentile)")
            elif gex_percentile < 10:  # Bottom 10%
                signals['gex_extreme'] = 0.7
                triggers.append(f"Low GEX ({gex_percentile:.0f}th percentile)")
            else:
                signals['gex_extreme'] = 0.0
        else:
            signals['gex_extreme'] = 0.0
        
        # WEIGHTED PROBABILITY CALCULATION (weights sum to 1.0)
        weights = {
            'iv': 0.25,           # IV volatility spike - strong predictor
            'oi_accel': 0.30,     # OI acceleration - strongest predictor
            'gamma_conc': 0.20,   # Gamma concentration - moderate predictor
            'pin_risk': 0.10,     # Pin risk - minor predictor
            'gex_flip': 0.10,     # GEX flip - moderate predictor
            'gex_extreme': 0.05   # GEX extremes - weak predictor
        }
        
        probability = sum(signals.get(key, 0) * weight for key, weight in weights.items())
        # Cap probability at 0.95
        probability = min(0.95, probability)
        
        # DIRECTION PREDICTION using weighted signals
        direction_score = 0
        
        # PRIMARY SIGNAL: ITM Change in OI (most predictive - smart money)
        ce_itm_chg_oi = current_data.get('ce_itm_chg_oi', 0)
        pe_itm_chg_oi = current_data.get('pe_itm_chg_oi', 0)
        
        # ITM CE unwinding (negative) = Bullish (price expected to rise)
        # ITM PE unwinding (negative) = Bearish (price expected to fall)
        if ce_itm_chg_oi < -10000:  # Significant CE ITM unwinding
            direction_score += 3  # Strong bullish
        elif ce_itm_chg_oi < 0:
            direction_score += 2  # Bullish
        
        if pe_itm_chg_oi < -10000:  # Significant PE ITM unwinding
            direction_score -= 3  # Strong bearish
        elif pe_itm_chg_oi < 0:
            direction_score -= 2  # Bearish
        
        # SECONDARY: Overall PCR
        ce_oi_total = current_data.get('ce_oi_total', 0)
        pe_oi_total = current_data.get('pe_oi_total', 0)
        pcr = pe_oi_total / ce_oi_total if ce_oi_total > 0 else 1
        
        if pcr < 0.7:
            direction_score += 1  # Heavy call OI = bullish
        elif pcr > 1.3:
            direction_score -= 1  # Heavy put OI = bearish
        
        # GEX direction (adaptive using percentile)
        if len(hist_gex) >= 5:
            gex_75th = np.percentile(hist_gex, 75)
            gex_25th = np.percentile(hist_gex, 25)
            
            if curr_gex > gex_75th:
                direction_score -= 2  # Strong resistance = bearish
            elif curr_gex < gex_25th:
                direction_score += 2  # Strong support = bullish
        
        # IV skew
        ce_iv_avg = current_data.get('ce_iv_avg', 0)
        pe_iv_avg = current_data.get('pe_iv_avg', 0)
        if ce_iv_avg > 0 and pe_iv_avg > 0:
            if ce_iv_avg > pe_iv_avg * 1.1:
                direction_score -= 1  # Calls expensive = bearish expectation
            elif pe_iv_avg > ce_iv_avg * 1.1:
                direction_score += 1  # Puts expensive = bullish expectation
        
        # Spot price momentum (check recent trend)
        if len(historical_data) >= 3:
            recent_spots = [d.get('spot_price', 0) for d in list(historical_data)[-3:]]
            if all(recent_spots[i] > recent_spots[i+1] for i in range(len(recent_spots)-1)):
                direction_score -= 2  # Consistent downtrend
            elif all(recent_spots[i] < recent_spots[i+1] for i in range(len(recent_spots)-1)):
                direction_score += 2  # Consistent uptrend
        
        # Determine direction with lower threshold
        if direction_score >= 2:
            direction = "UPSIDE"
        elif direction_score <= -2:
            direction = "DOWNSIDE"
        else:
            direction = "NEUTRAL"
        
        # CONFIDENCE based on trigger count and probability
        # NOTE: time_to_blast removed - timing prediction requires historical calibration
        # which is not yet implemented. Until calibrated, time predictions are unreliable.
        if probability > 0.7 and len(triggers) >= 4:
            confidence = "CRITICAL"
        elif probability > 0.6 and len(triggers) >= 3:
            confidence = "VERY_HIGH"
        elif probability > 0.4:
            confidence = "HIGH"
        elif probability > 0.25:
            confidence = "MEDIUM"
        else:
            confidence = "LOW"
        
        # Time to blast: Removed - requires ML calibration with historical data
        # TODO: Implement ML-calibrated timing model using historical blast events
        time_to_blast = None  # Not available until calibrated
        
        # RISK LEVEL
        if probability > 0.75:
            risk_level = "EXTREME"
        elif probability > 0.6:
            risk_level = "HIGH"
        elif probability > 0.4:
            risk_level = "ELEVATED"
        else:
            risk_level = "LOW"
        
        return GammaBlastSignal(
            probability=probability,
            direction=direction,
            confidence=confidence,
            time_to_blast_min=time_to_blast,
            triggers=triggers,
            risk_level=risk_level
        )


class OptionChainBackgroundService:
    """Background service for fetching option chain data for all symbols"""
    
    def __init__(self, refresh_interval: int = 180, force_mode: bool = False):
        """
        Initialize background service - REST API MODE
        
        Args:
            refresh_interval: REST API refresh interval in seconds (180 = 3 minutes for stocks)
            force_mode: If True, bypasses market hours check (useful for testing)
        """
        self.refresh_interval = refresh_interval
        self.index_refresh_interval = 90  # Indices refresh every 90 seconds (avoid rate limits)
        self.running = False
        self.db_manager = None
        self.upstox_api = None
        self.token_manager = None
        self.symbol_configs = {}
        self.executor = None
        self.expiry_cache = {}  # Cache expiry dates to avoid repeated API calls
        self.force_mode = force_mode  # Force mode bypasses market hours check
        
        # Fast refresh indices (using REST API)
        self.realtime_indices = ['NIFTY', 'BANKNIFTY', 'FINNIFTY', 'SENSEX', 'MIDCPNIFTY']
        
        # Initialize adaptive gamma blast detector
        self.gamma_detector = AdaptiveGammaBlastDetector(lookback_periods=20)
        
        self._load_credentials()
        self._initialize_components()
        
        # Setup signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _load_credentials(self):
        """Load Upstox credentials from secrets.toml"""
        try:
            secrets_path = os.path.join(
                os.path.dirname(__file__), 
                '.streamlit', 
                'secrets.toml'
            )
            
            if not os.path.exists(secrets_path):
                raise FileNotFoundError(f"secrets.toml not found at {secrets_path}")
            
            with open(secrets_path) as f:
                secrets = toml.load(f)
            
            if 'upstox' not in secrets:
                raise ValueError("'upstox' section not found in secrets.toml")
            
            self.credentials = {
                'access_token': secrets['upstox']['access_token'],
                'api_key': secrets['upstox']['api_key'],
                'api_secret': secrets['upstox']['api_secret'],
                'redirect_uri': secrets['upstox']['redirect_uri']
            }
            
            logger.info("Credentials loaded successfully")
            
        except Exception as e:
            logger.error(f"Failed to load credentials: {e}")
            raise
    
    def _initialize_components(self):
        """Initialize database and API components"""
        try:
            # Initialize database (may fail if DB not available - that's OK for testing)
            try:
                self.db_manager = TimescaleDBManager()
                logger.info("Database manager initialized")
            except Exception as db_error:
                logger.warning(f"Database initialization failed: {db_error}")
                logger.warning("Service will continue but database operations will be disabled")
                self.db_manager = None
            
            # Initialize token manager for auto-refresh
            self.token_manager = get_token_manager()
            logger.info("Token manager initialized")
            
            # Initialize Upstox token refresher (handles extended_token per Upstox API v2)
            try:
                from auto_token_refresh import UpstoxTokenRefresher
                self.token_refresher = UpstoxTokenRefresher()
                logger.info("Upstox token refresher initialized (API v2)")
            except Exception as e:
                logger.warning(f"Could not initialize token refresher: {e}")
                self.token_refresher = None
            
            # Initialize Upstox API with auto-refresh token
            self.upstox_api = UpstoxAPI()
            self._refresh_access_token_if_needed()
            logger.info("Upstox API initialized (REST API only)")
            
            # Initialize thread pool executor with reduced workers to avoid rate limiting
            # REAL-TIME OPTIMIZATION: 5 workers for parallel processing
            self.executor = ThreadPoolExecutor(max_workers=5, thread_name_prefix="OptionChainFetcher")
            logger.info("Thread pool executor initialized (5 workers for real-time processing)")
            
        except Exception as e:
            logger.error(f"Failed to initialize components: {e}")
            raise
    
    
    def _refresh_access_token_if_needed(self):
        """
        Refresh access token if expired (automatic)
        Uses Upstox API v2 endpoint and handles extended_token
        Based on: https://upstox.com/developer/api-documentation/get-token/
        """
        try:
            # First, try to use extended_token if available (Upstox API v2 feature)
            if self.token_refresher:
                is_expired = self.token_refresher.check_token_expiration()
                if is_expired:
                    logger.info("🔄 Access token expired, checking for extended_token...")
                    if self.token_refresher.use_extended_token_if_available():
                        logger.info("✅ Switched to extended_token for read-only operations")
                        # Reload credentials
                        self._load_credentials()
                        self.upstox_api.access_token = self.credentials.get('access_token')
                        return True
            
            # Check if we have refresh_token in credentials (legacy support)
            refresh_token = self.credentials.get('refresh_token')
            if not refresh_token:
                # Try to get from token manager
                refresh_token = self.token_manager.get_refresh_token()
                if refresh_token:
                    # Update credentials with refresh token
                    self.credentials['refresh_token'] = refresh_token
                    logger.debug("Found refresh_token in token manager")
            
            # Get token with auto-refresh enabled
            access_token = self.token_manager.get_access_token(
                auto_refresh=True,
                api_key=self.credentials.get('api_key'),
                api_secret=self.credentials.get('api_secret')
            )
            
            if access_token:
                old_token = self.upstox_api.access_token
                self.upstox_api.access_token = access_token
                # Also update credentials for consistency
                self.credentials['access_token'] = access_token
                
                # Log if token changed
                if old_token != access_token:
                    logger.info(f"✅ Access token updated: {access_token[:20]}...")
                
                return True
            else:
                logger.warning("⚠️ Could not get access token")
                logger.warning("   Note: Upstox tokens expire at 3:30 AM daily (per API documentation)")
                logger.warning("   You may need to re-authenticate to get a new token")
                # Fallback to credentials file token
                self.upstox_api.access_token = self.credentials.get('access_token')
                return False
        except Exception as e:
            logger.error(f"Error refreshing access token: {e}")
            import traceback
            logger.debug(traceback.format_exc())
            # Fallback to credentials file token
            self.upstox_api.access_token = self.credentials.get('access_token')
            return False
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals gracefully"""
        logger.info(f"Received signal {signum}, shutting down gracefully...")
        self.stop()
        sys.exit(0)
    
    def _is_market_open(self) -> bool:
        """Check if market is currently open"""
        # Force mode bypasses market hours check
        if self.force_mode:
            return True
        
        now = datetime.now(IST)
        current_time = now.time()
        weekday = now.weekday()
        
        # Market is closed on weekends
        if weekday >= 5:  # Saturday = 5, Sunday = 6
            return False
        
        # Market hours: 9:15 AM to 3:30 PM IST
        market_open = datetime.strptime("09:15", "%H:%M").time()
        market_close = datetime.strptime("15:30", "%H:%M").time()
        
        # Market is open only between 9:15 AM and 3:30 PM
        # After 3:30 PM, return False so service stops fetching data
        return market_open <= current_time <= market_close
    
    def _cleanup_non_market_hours_data(self):
        """Delete data collected outside market hours (before 9:15 AM and after 3:30 PM IST)"""
        try:
            logger.info("🧹 Starting cleanup of non-market hours data...")
            
            with self.db_manager.get_connection() as conn:
                with conn.cursor() as cur:
                    # Delete option chain data outside market hours
                    cur.execute("""
                        DELETE FROM option_chain_data
                        WHERE (
                            EXTRACT(HOUR FROM timestamp AT TIME ZONE 'Asia/Kolkata') < 9
                            OR (EXTRACT(HOUR FROM timestamp AT TIME ZONE 'Asia/Kolkata') = 9 
                                AND EXTRACT(MINUTE FROM timestamp AT TIME ZONE 'Asia/Kolkata') < 15)
                            OR EXTRACT(HOUR FROM timestamp AT TIME ZONE 'Asia/Kolkata') > 15
                            OR (EXTRACT(HOUR FROM timestamp AT TIME ZONE 'Asia/Kolkata') = 15 
                                AND EXTRACT(MINUTE FROM timestamp AT TIME ZONE 'Asia/Kolkata') > 30)
                        )
                        AND timestamp > NOW() - INTERVAL '7 days'
                    """)
                    option_deleted = cur.rowcount
                    
                    # Delete gamma exposure history outside market hours
                    cur.execute("""
                        DELETE FROM gamma_exposure_history
                        WHERE (
                            EXTRACT(HOUR FROM timestamp AT TIME ZONE 'Asia/Kolkata') < 9
                            OR (EXTRACT(HOUR FROM timestamp AT TIME ZONE 'Asia/Kolkata') = 9 
                                AND EXTRACT(MINUTE FROM timestamp AT TIME ZONE 'Asia/Kolkata') < 15)
                            OR EXTRACT(HOUR FROM timestamp AT TIME ZONE 'Asia/Kolkata') > 15
                            OR (EXTRACT(HOUR FROM timestamp AT TIME ZONE 'Asia/Kolkata') = 15 
                                AND EXTRACT(MINUTE FROM timestamp AT TIME ZONE 'Asia/Kolkata') > 30)
                        )
                        AND timestamp > NOW() - INTERVAL '7 days'
                    """)
                    gamma_deleted = cur.rowcount
                    
                    conn.commit()
                    
                    if option_deleted > 0 or gamma_deleted > 0:
                        logger.info(f"✅ Cleanup complete: Deleted {option_deleted} option records and {gamma_deleted} gamma records outside market hours")
                    else:
                        logger.debug("No non-market hours data found to clean")
                        
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")
    
    def _get_fo_instruments(self) -> Dict[str, str]:
        """Get F&O instruments mapping - ONLY ACTIVE stocks with current expiry"""
        try:
            import requests
            import gzip
            import json
            from io import BytesIO
            import pandas as pd

            url = "https://assets.upstox.com/market-quote/instruments/exchange/NSE.json.gz"
            response = requests.get(url)
            
            with gzip.GzipFile(fileobj=BytesIO(response.content)) as gz:
                data = json.load(gz)

            df = pd.DataFrame(data)
            
            # Filter for NSE_FO segment only (exclude NSE_INDEX, we'll add manually)
            fno_df = df[df['segment'] == "NSE_FO"].copy()
            
            # CRITICAL FIX: Get only stocks with FUTURE expiry (current month)
            # This filters out delisted/junk symbols that have no active contracts
            if 'expiry' in fno_df.columns:
                # Filter for contracts with expiry dates (active stocks)
                fno_df = fno_df[fno_df['expiry'].notna()].copy()
                
                # Get the nearest expiry for each symbol
                fno_df['expiry_date'] = pd.to_datetime(fno_df['expiry'])
                current_expiries = fno_df.groupby('name')['expiry_date'].min().reset_index()
                active_stocks = current_expiries['name'].unique().tolist()
                
                logger.info(f"Found {len(active_stocks)} active F&O stocks with current expiry")
            else:
                # Fallback: use unique names
                active_stocks = fno_df['name'].unique().tolist()
                logger.warning("No expiry column found, using all symbols (may include junk)")
            
            # Build instrument mapping ONLY for active stocks
            # Use asset_symbol (trading symbol) not name (company name)
            fo_instruments = {}
            for stock in active_stocks:
                stock_data = fno_df[fno_df['name'] == stock].iloc[0]
                if 'asset_symbol' in stock_data:
                    symbol = stock_data['asset_symbol']  # Use trading symbol (e.g., "RELIANCE")
                    # Use the asset_key directly from NSE data (e.g., "NSE_EQ|INE002A01018")
                    instrument_key = stock_data['asset_key']
                    fo_instruments[symbol] = instrument_key
            
            # Add indices manually
            fo_instruments.update({
                "NIFTY": "NSE_INDEX|Nifty 50",
                "BANKNIFTY": "NSE_INDEX|Nifty Bank",
                "FINNIFTY": "NSE_INDEX|Nifty Fin Service",
                "MIDCPNIFTY": "NSE_INDEX|NIFTY MID SELECT",
                "SENSEX": "BSE_INDEX|SENSEX"
            })
            
            logger.info(f"Total symbols to monitor: {len(fo_instruments)} ({len(active_stocks)} stocks + 5 indices)")
            return fo_instruments
            
        except Exception as e:
            logger.error(f"Failed to get F&O instruments: {e}")
            # Fallback to indices only
            return {
                "NIFTY": "NSE_INDEX|Nifty 50",
                "BANKNIFTY": "NSE_INDEX|Nifty Bank",
                "FINNIFTY": "NSE_INDEX|Nifty Fin Service",
                "MIDCPNIFTY": "NSE_INDEX|NIFTY MID SELECT"
            }
    
    def _get_active_symbols(self) -> List[Dict]:
        """
        Get list of all F&O symbols to monitor dynamically from Upstox
        Automatically fetches all active F&O symbols (typically ~215 stocks + 5 indices)
        
        Returns:
            List of symbol configurations
        """
        # Get all F&O instruments dynamically
        all_symbols = self._get_fo_instruments()
        
        symbols = []
        symbol_count = 0
        
        # Add all symbols
        for symbol, instrument_key in all_symbols.items():
            if not instrument_key or not symbol:
                continue
            
            try:
                # Store in database
                if self.db_manager and self.db_manager.pool:
                    self.db_manager.update_symbol_config(symbol, instrument_key, self.refresh_interval)
                
                symbols.append({
                    'symbol': symbol,
                    'instrument_key': instrument_key,
                    'is_active': True,
                    'refresh_interval': self.refresh_interval
                })
                symbol_count += 1
                    
            except Exception as e:
                logger.warning(f"Failed to process symbol {symbol}: {e}")
                continue
        
        logger.info(f"Monitoring {symbol_count} F&O symbols on every {self.refresh_interval}s interval")
        return symbols
    
    def _get_latest_expiry(self, symbol: str, instrument_key: str) -> Optional[str]:
        """Get the latest (nearest) expiry date for a symbol - OPTIMIZED: Daily cache"""
        # Check cache first - Valid for entire trading day (until market close)
        cache_key = f"{symbol}_{instrument_key}"
        if cache_key in self.expiry_cache:
            cached_expiry, cache_time = self.expiry_cache[cache_key]
            # Cache valid until market close (expires at 3:30 PM IST)
            now = datetime.now(IST)
            cache_datetime = datetime.fromtimestamp(cache_time, IST)
            
            # If cached today and before market close, use it
            if cache_datetime.date() == now.date() and now.time() < datetime.strptime("15:30", "%H:%M").time():
                logger.debug(f"Using daily cached expiry for {symbol}: {cached_expiry}")
                return cached_expiry
        
        # If not in cache or expired, fetch from API
        # Upstox allows: 50/sec, 500/min, 2000/30min for standard APIs
        # REAL-TIME OPTIMIZATION: Reduced retries and delays
        max_retries = 2  # Reduced from 3
        base_delay = 0.1  # Reduced from 0.4s
        
        for attempt in range(max_retries):
            try:
                # Exponential backoff: 0.5s, 1s, 2s, 4s
                wait_time = base_delay * (2 ** attempt) if attempt > 0 else base_delay
                time.sleep(wait_time)  # Delay before each expiry API call
                
                contracts_data, error = self.upstox_api.get_option_contracts(instrument_key)
                
                # Check for rate limit error
                if error and isinstance(error, dict):
                    errors = error.get('errors', [])
                    for err in errors:
                        if err.get('errorCode') == 'UDAPI10005' or 'Too Many Request' in str(err.get('message', '')):
                            if attempt < max_retries - 1:
                                retry_wait = 5 * (2 ** attempt)  # Exponential backoff: 5s, 10s, 20s
                                logger.warning(f"⚠️  RATE LIMIT for {symbol}. Waiting {retry_wait}s before retry {attempt + 1}/{max_retries}...")
                                time.sleep(retry_wait)
                                continue
                            else:
                                logger.error(f"❌ Max retries reached for {symbol}. Using cached expiry if available.")
                                # Try to return cached value even if expired
                                if cache_key in self.expiry_cache:
                                    cached_expiry, _ = self.expiry_cache[cache_key]
                                    logger.info(f"✓ Using expired cache for {symbol}: {cached_expiry}")
                                    return cached_expiry
                                return None
                
                if contracts_data and 'data' in contracts_data:
                    # Get all expiry dates and sort them (earliest first = current expiry)
                    expiry_dates = sorted({c['expiry'] for c in contracts_data['data'] if 'expiry' in c})
                    if expiry_dates:
                        # Filter out expired dates (keep today and future dates only)
                        today = datetime.now(IST).date()
                        future_expiries = [exp for exp in expiry_dates if datetime.strptime(exp, '%Y-%m-%d').date() >= today]
                        
                        if future_expiries:
                            # Return the earliest non-expired expiry
                            nearest_expiry = future_expiries[0]
                            # Cache the result
                            self.expiry_cache[cache_key] = (nearest_expiry, time.time())
                            logger.debug(f"Found and cached nearest expiry for {symbol}: {nearest_expiry}")
                            return nearest_expiry
                        else:
                            logger.warning(f"All expiries are in the past for {symbol}")
                            return None
                
                # If no data but no error, might be valid (no contracts available)
                if not error:
                    logger.debug(f"No expiry dates found in contracts data for {symbol}")
                    return None
                
                # If error and not rate limit, log and retry
                if error and attempt < max_retries - 1:
                    logger.warning(f"Error getting expiry for {symbol} (attempt {attempt + 1}/{max_retries}): {error}")
                    time.sleep(wait_time)
                    continue
                else:
                    logger.error(f"Failed to get expiry for {symbol}: {error}")
                    return None
                    
            except Exception as e:
                if attempt < max_retries - 1:
                    logger.warning(f"Exception getting expiry for {symbol} (attempt {attempt + 1}/{max_retries}): {e}")
                    time.sleep(wait_time)
                    continue
                else:
                    logger.error(f"Failed to get expiry for {symbol}: {e}")
                    return None
        
        return None
    
    def _get_all_expiries(self, symbol: str, instrument_key: str, max_expiries: int = 2) -> List[str]:
        """Get multiple future expiry dates for a symbol to ensure next week's expiry is available
        
        Args:
            symbol: Trading symbol
            instrument_key: Upstox instrument key
            max_expiries: Maximum number of expiries to return (default 2 for current + next week)
            
        Returns:
            List of expiry dates in YYYY-MM-DD format, sorted ascending
        """
        max_retries = 2
        base_delay = 0.1
        
        for attempt in range(max_retries):
            try:
                wait_time = base_delay * (2 ** attempt) if attempt > 0 else base_delay
                time.sleep(wait_time)
                
                contracts_data, error = self.upstox_api.get_option_contracts(instrument_key)
                
                if error:
                    if attempt < max_retries - 1:
                        continue
                    logger.warning(f"Failed to get expiries for {symbol}: {error}")
                    return []
                
                if contracts_data and 'data' in contracts_data:
                    # Get all expiry dates and sort them
                    expiry_dates = sorted({c['expiry'] for c in contracts_data['data'] if 'expiry' in c})
                    
                    if expiry_dates:
                        # Filter for future dates only (today onwards)
                        today = datetime.now(IST).date()
                        future_expiries = [
                            exp for exp in expiry_dates 
                            if datetime.strptime(exp, '%Y-%m-%d').date() >= today
                        ]
                        
                        # Return up to max_expiries
                        result = future_expiries[:max_expiries]
                        logger.debug(f"Found {len(result)} future expiries for {symbol}: {result}")
                        return result
                
                return []
                    
            except Exception as e:
                if attempt < max_retries - 1:
                    continue
                logger.warning(f"Exception getting expiries for {symbol}: {e}")
                return []
        
        return []
    
    def _fetch_and_store_option_chain(self, symbol: str, instrument_key: str, 
                                      expiry_date: str) -> bool:
        """
        Fetch option chain data for a symbol and store in database
        
        Args:
            symbol: Symbol name
            instrument_key: Instrument key
            expiry_date: Expiry date in YYYY-MM-DD format
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Minimal delay - rate limits allow 50/sec, we're doing ~7/sec (215 symbols / 30 sec)
            time.sleep(0.1)  # 100ms delay (optimized for real-time)
            
            # Fetch option chain data with retry on network errors
            max_retries = 3
            retry_delay = 5
            
            for attempt in range(max_retries):
                try:
                    option_data, error = self.upstox_api.get_pc_option_chain(instrument_key, expiry_date)
                    
                    if not option_data or error is not None:
                        # Check if it's a rate limit error
                        if error and isinstance(error, dict):
                            errors = error.get('errors', [])
                            for err in errors:
                                if err.get('errorCode') == 'UDAPI10005' or 'Too Many Request' in str(err.get('message', '')):
                                    logger.warning(f"Rate limit fetching option chain for {symbol}. Will skip and retry later.")
                                    return False
                        
                        # Check if network error and retry
                        error_str = str(error)
                        is_network_error = any(keyword in error_str.lower() for keyword in 
                            ['connection', 'timeout', 'network', 'unreachable', 'resolve', 'dns'])
                        
                        if is_network_error and attempt < max_retries - 1:
                            logger.warning(f"Network error for {symbol} (attempt {attempt+1}/{max_retries}): {error}. Retrying in {retry_delay}s...")
                            time.sleep(retry_delay)
                            continue
                        
                        logger.warning(f"Failed to fetch data for {symbol}: {error}")
                        return False
                    
                    # Success - break retry loop
                    break
                    
                except Exception as api_error:
                    error_str = str(api_error)
                    is_network_error = any(keyword in error_str.lower() for keyword in 
                        ['connection', 'timeout', 'network', 'unreachable', 'resolve', 'dns'])
                    
                    if is_network_error and attempt < max_retries - 1:
                        logger.warning(f"Network exception for {symbol} (attempt {attempt+1}/{max_retries}): {api_error}. Retrying in {retry_delay}s...")
                        time.sleep(retry_delay)
                        continue
                    else:
                        raise
            
            if 'data' not in option_data or not option_data['data']:
                logger.warning(f"No data returned for {symbol}")
                return False
            
            # Extract spot price from API response
            spot_price = 0
            if 'underlying_spot_price' in option_data:
                spot_price = float(option_data.get('underlying_spot_price', 0))
            elif option_data.get('data') and len(option_data['data']) > 0:
                first_strike = option_data['data'][0]
                # Try to get spot from strike data
                spot_price = first_strike.get('underlying_spot_price', 0) or first_strike.get('strike_price', 0)
            
            # If still 0, try to infer from strikes (use middle strike as approximation)
            if spot_price == 0 and option_data['data']:
                strikes = [s.get('strike_price', 0) for s in option_data['data'] if s.get('strike_price', 0) > 0]
                if strikes:
                    strikes.sort()
                    spot_price = strikes[len(strikes) // 2]  # Use middle strike as approximation
            
            # Store option chain data in database
            success = self.db_manager.insert_option_chain_data(
                symbol=symbol,
                instrument_key=instrument_key,
                expiry_date=expiry_date,
                spot_price=spot_price,
                option_chain_data=option_data['data']
            )
            
            if success:
                logger.info(f"Successfully stored raw option chain data for {symbol} ({expiry_date})")
                
                # Calculate and store ITM bucket summaries (1-5 strikes)
                try:
                    self._calculate_and_store_itm_buckets(symbol, expiry_date, option_data['data'], spot_price)
                except Exception as e:
                    logger.warning(f"Failed to calculate ITM buckets for {symbol}: {e}")
                
                # Calculate and store sentiment (for Sentiment Dashboard)
                try:
                    self._calculate_and_store_sentiment(symbol, expiry_date, option_data['data'], spot_price)
                except Exception as e:
                    logger.warning(f"Failed to calculate sentiment for {symbol}: {e}")
                
                # Calculate and store gamma exposure (for gamma leading indicators)
                try:
                    self._calculate_and_store_gamma_exposure(symbol, expiry_date, option_data['data'], spot_price)
                except Exception as e:
                    logger.warning(f"Failed to calculate gamma exposure for {symbol}: {e}")
            else:
                logger.warning(f"Failed to store data for {symbol}")
            
            return success
            
        except Exception as e:
            logger.error(f"Error fetching/storing data for {symbol}: {e}")
            return False
    
    def _calculate_and_store_sentiment(self, symbol: str, expiry_date: str, option_data: List[Dict], spot_price: float):
        """
        Calculate comprehensive sentiment score (same as Option Chain Analysis) and store in database
        Uses ITM filtering (3 strikes by default) before sentiment calculation
        
        Args:
            symbol: Symbol name
            expiry_date: Expiry date
            option_data: Raw option chain data
            spot_price: Current spot price
        """
        try:
            import pandas as pd
            
            # ITM count for sentiment calculation (matches UI default: index=2 means 3 strikes)
            itm_count = 3
            
            # Process option chain data (same as optionchain.py)
            processed_data = []
            
            for strike_data in option_data:
                if 'call_options' not in strike_data or 'put_options' not in strike_data:
                    continue
                
                strike_price = strike_data.get('strike_price', 0)
                if strike_price <= 0:
                    continue
                
                call_market = strike_data['call_options'].get('market_data', {})
                call_greeks = strike_data['call_options'].get('option_greeks', {})
                put_market = strike_data['put_options'].get('market_data', {})
                put_greeks = strike_data['put_options'].get('option_greeks', {})
                
                ce_oi = call_market.get('oi', 0) or 0
                ce_volume = call_market.get('volume', 0) or 0
                ce_ltp = call_market.get('ltp', 0) or 0
                ce_close = call_market.get('close_price', 0) or 0
                ce_chgoi = ce_oi - (call_market.get('prev_oi', 0) or 0)
                ce_change = ce_ltp - ce_close if ce_close > 0 else 0
                ce_delta = call_greeks.get('delta', 0) or 0
                
                pe_oi = put_market.get('oi', 0) or 0
                pe_volume = put_market.get('volume', 0) or 0
                pe_ltp = put_market.get('ltp', 0) or 0
                pe_close = put_market.get('close_price', 0) or 0
                pe_chgoi = pe_oi - (put_market.get('prev_oi', 0) or 0)
                pe_change = pe_ltp - pe_close if pe_close > 0 else 0
                pe_delta = put_greeks.get('delta', 0) or 0
                
                # Calculate position signals
                def get_position_signal(ltp, change, chgoi):
                    if change > 0 and chgoi > 0:
                        return "Long Build"
                    elif change > 0 and chgoi < 0:
                        return "Short Covering"
                    elif change < 0 and chgoi > 0:
                        return "Short Buildup"
                    elif change < 0 and chgoi < 0:
                        return "Long Unwinding"
                    else:
                        return "No Change"
                
                processed_data.append({
                    'Strike': strike_price,
                    'CE_OI': ce_oi,
                    'CE_Volume': ce_volume,
                    'CE_ChgOI': ce_chgoi,
                    'CE_LTP': ce_ltp,
                    'CE_Change': ce_change,
                    'CE_Position': get_position_signal(ce_ltp, ce_change, ce_chgoi),
                    'ce_delta': ce_delta,
                    'PE_OI': pe_oi,
                    'PE_Volume': pe_volume,
                    'PE_ChgOI': pe_chgoi,
                    'PE_LTP': pe_ltp,
                    'PE_Change': pe_change,
                    'PE_Position': get_position_signal(pe_ltp, pe_change, pe_chgoi),
                    'pe_delta': pe_delta,
                })
            
            if not processed_data:
                return
            
            df = pd.DataFrame(processed_data)
            df = df[df['Strike'] > 0].sort_values('Strike').reset_index(drop=True)
            
            if df.empty or len(df) < 3:
                return
            
            # APPLY ITM FILTERING (using delta-based ATM for accuracy)
            # Delta-based ATM: CE delta closest to 0.5 (more accurate than strike-based)
            atm_strike = df.loc[df["ce_delta"].sub(0.5).abs().idxmin(), "Strike"]
            
            below_atm = df[df["Strike"] < atm_strike].tail(itm_count)
            above_atm = df[df["Strike"] > atm_strike].head(itm_count)
            atm_row = df[df["Strike"] == atm_strike]
            
            # Combine filtered tables
            filtered_parts = []
            if not below_atm.empty:
                filtered_parts.append(below_atm)
            if not atm_row.empty:
                filtered_parts.append(atm_row)
            if not above_atm.empty:
                filtered_parts.append(above_atm)
            
            if not filtered_parts:
                return
            
            filtered_df = pd.concat(filtered_parts, axis=0, ignore_index=True)
            filtered_df = filtered_df.sort_values('Strike').reset_index(drop=True)
            
            # Calculate PCR data on FILTERED data only
            ce_oi_total = filtered_df['CE_OI'].sum()
            pe_oi_total = filtered_df['PE_OI'].sum()
            ce_chgoi_total = filtered_df['CE_ChgOI'].sum()
            pe_chgoi_total = filtered_df['PE_ChgOI'].sum()
            
            pcr_oi = pe_oi_total / ce_oi_total if ce_oi_total > 0 else 0
            pcr_chgoi = pe_chgoi_total / ce_chgoi_total if ce_chgoi_total != 0 else 0
            
            pcr_data = {
                'OVERALL_PCR_OI': pcr_oi,
                'OVERALL_PCR_CHGOI': pcr_chgoi
            }
            
            # COMPREHENSIVE SENTIMENT CALCULATION on FILTERED data (same as Option Chain Analysis)
            scores = {
                "price_action": 0,
                "open_interest": 0,
                "fresh_activity": 0,
                "position_distribution": 0
            }
            
            # 1. PRICE ACTION ANALYSIS (25% weight) - using FILTERED data
            price_score = 0
            strikes_above_spot = len(filtered_df[filtered_df["Strike"] > spot_price])
            strikes_below_spot = len(filtered_df[filtered_df["Strike"] < spot_price])
            
            if strikes_above_spot > strikes_below_spot:
                price_score += 20
            elif strikes_below_spot > strikes_above_spot:
                price_score -= 20
            
            max_pain_strike = filtered_df.loc[filtered_df["CE_OI"].add(filtered_df["PE_OI"]).idxmax(), "Strike"]
            price_vs_max_pain = (spot_price - max_pain_strike) / max_pain_strike * 100
            
            if price_vs_max_pain > 2:
                price_score -= 30
            elif price_vs_max_pain < -2:
                price_score += 30
            
            scores["price_action"] = max(-100, min(100, price_score))
            
            # 2. OPEN INTEREST ANALYSIS (30% weight) - using FILTERED PCR
            oi_score = 0
            if pcr_oi < 0.6:
                oi_score += 40
            elif pcr_oi < 0.8:
                oi_score += 20
            elif pcr_oi > 1.4:
                oi_score -= 40
            elif pcr_oi > 1.2:
                oi_score -= 20
            
            scores["open_interest"] = max(-100, min(100, oi_score))
            
            # 3. FRESH ACTIVITY ANALYSIS (25% weight) - using FILTERED PCR ChgOI
            activity_score = 0
            if pcr_chgoi > 2.0:
                activity_score += 50
            elif pcr_chgoi > 1.5:
                activity_score += 30
            elif pcr_chgoi < 0.3:
                activity_score -= 50
            elif pcr_chgoi < 0.6:
                activity_score -= 30
            
            scores["fresh_activity"] = max(-100, min(100, activity_score))
            
            # 4. POSITION DISTRIBUTION ANALYSIS (20% weight) - using FILTERED positions
            position_score = 0
            ce_positions = filtered_df['CE_Position'].value_counts()
            pe_positions = filtered_df['PE_Position'].value_counts()
            
            bullish_ce = ce_positions.get("Long Build", 0) + ce_positions.get("Short Covering", 0)
            bullish_pe = pe_positions.get("Long Unwinding", 0) + pe_positions.get("Short Buildup", 0)
            bearish_ce = ce_positions.get("Short Buildup", 0) + ce_positions.get("Long Unwinding", 0)
            bearish_pe = pe_positions.get("Long Build", 0) + pe_positions.get("Short Covering", 0)
            
            total_strikes = len(filtered_df)
            net_bullish_activity = (bullish_ce - bearish_ce) + (bullish_pe - bearish_pe)
            position_bias_pct = (net_bullish_activity / total_strikes) * 100
            position_score = max(-100, min(100, position_bias_pct * 10))
            
            scores["position_distribution"] = position_score
            
            # Calculate weighted final score
            weights = {
                "price_action": 0.25,
                "open_interest": 0.30,
                "fresh_activity": 0.25,
                "position_distribution": 0.20
            }
            
            final_score = sum(scores[key] * weights[key] for key in scores.keys())
            
            # Determine sentiment category and confidence
            if final_score >= 60:
                sentiment = "STRONG BULLISH"
                confidence = "HIGH"
            elif final_score >= 30:
                sentiment = "BULLISH"
                confidence = "HIGH"
            elif final_score >= 15:
                sentiment = "BULLISH BIAS"
                confidence = "MEDIUM"
            elif final_score <= -60:
                sentiment = "STRONG BEARISH"
                confidence = "HIGH"
            elif final_score <= -30:
                sentiment = "BEARISH"
                confidence = "HIGH"
            elif final_score <= -15:
                sentiment = "BEARISH BIAS"
                confidence = "MEDIUM"
            else:
                sentiment = "NEUTRAL"
                confidence = "MEDIUM"
            
            # Store comprehensive sentiment in database
            self.db_manager.insert_sentiment_score(
                symbol=symbol,
                expiry_date=expiry_date,
                sentiment_score=final_score,
                sentiment=sentiment,
                confidence=confidence,
                spot_price=spot_price,
                pcr_oi=pcr_oi,
                pcr_volume=0  # Not calculated in background service
            )
            
            logger.info(f"Stored comprehensive sentiment for {symbol}: {final_score:.2f} ({sentiment})")
            
        except Exception as e:
            logger.error(f"Error calculating sentiment for {symbol}: {e}")
    
    def _calculate_and_store_gamma_exposure(self, symbol: str, expiry_date: str, option_data: List[Dict], spot_price: float):
        """
        Calculate gamma exposure and store in database for leading indicators
        
        Args:
            symbol: Symbol name
            expiry_date: Expiry date
            option_data: Raw option chain data
            spot_price: Current spot price
        """
        try:
            import pandas as pd
            
            # Process option chain data
            processed_data = []
            
            for strike_data in option_data:
                if 'call_options' not in strike_data or 'put_options' not in strike_data:
                    continue
                
                strike_price = strike_data.get('strike_price', 0)
                if strike_price <= 0:
                    continue
                
                call_market = strike_data['call_options'].get('market_data', {})
                call_greeks = strike_data['call_options'].get('option_greeks', {})
                put_market = strike_data['put_options'].get('market_data', {})
                put_greeks = strike_data['put_options'].get('option_greeks', {})
                
                ce_oi = call_market.get('oi', 0) or 0
                pe_oi = put_market.get('oi', 0) or 0
                ce_gamma = call_greeks.get('gamma', 0) or 0
                pe_gamma = put_greeks.get('gamma', 0) or 0
                ce_iv = call_greeks.get('iv', 0) or 0
                pe_iv = put_greeks.get('iv', 0) or 0
                ce_delta = call_greeks.get('delta', 0) or 0
                pe_delta = put_greeks.get('delta', 0) or 0
                
                # Calculate GEX (Gamma * OI * Spot^2 / 100)
                ce_gex = ce_gamma * ce_oi * (spot_price ** 2) / 100 if ce_gamma and ce_oi else 0
                pe_gex = pe_gamma * pe_oi * (spot_price ** 2) / 100 if pe_gamma and pe_oi else 0
                net_gex = ce_gex - pe_gex  # Market makers are short options
                
                processed_data.append({
                    'strike': strike_price,
                    'ce_oi': ce_oi,
                    'pe_oi': pe_oi,
                    'ce_gamma': ce_gamma,
                    'pe_gamma': pe_gamma,
                    'ce_gex': ce_gex,
                    'pe_gex': pe_gex,
                    'net_gex': net_gex,
                    'ce_iv': ce_iv,
                    'pe_iv': pe_iv,
                    'ce_delta': ce_delta,
                    'pe_delta': pe_delta,
                })
            
            if not processed_data:
                return
            
            df = pd.DataFrame(processed_data)
            df = df[df['strike'] > 0].sort_values('strike').reset_index(drop=True)
            
            if df.empty or len(df) < 3:
                return
            
            # Calculate gamma metrics
            total_net_gex = df['net_gex'].sum()
            total_positive_gex = df[df['net_gex'] > 0]['net_gex'].sum()
            total_negative_gex = df[df['net_gex'] < 0]['net_gex'].sum()
            
            atm_idx = df['strike'].sub(spot_price).abs().idxmin()
            atm_strike = df.loc[atm_idx, 'strike']
            atm_gamma = df.loc[atm_idx, 'net_gex']
            
            # Find zero gamma level (where net GEX crosses zero)
            zero_gamma_level = spot_price
            if len(df) > 0:
                min_gex_idx = df['net_gex'].abs().idxmin()
                zero_gamma_level = df.loc[min_gex_idx, 'strike']
            
            # Calculate gamma concentration (std dev of GEX)
            gamma_concentration = df['net_gex'].std() if len(df) > 1 else 0
            
            # Calculate gamma gradient (change in GEX per strike)
            gamma_gradient = 0
            if len(df) > 1:
                gamma_gradient = (df['net_gex'].iloc[-1] - df['net_gex'].iloc[0]) / len(df)
            
            # Calculate IV metrics
            avg_iv = (df['ce_iv'].mean() + df['pe_iv'].mean()) / 2
            atm_iv = (df.loc[atm_idx, 'ce_iv'] + df.loc[atm_idx, 'pe_iv']) / 2
            iv_skew = df['pe_iv'].mean() - df['ce_iv'].mean()
            
            # Calculate OI metrics
            total_oi = df['ce_oi'].sum() + df['pe_oi'].sum()
            atm_oi = int(df.loc[atm_idx, 'ce_oi'] + df.loc[atm_idx, 'pe_oi'])
            oi_imbalance = (df['pe_oi'].sum() - df['ce_oi'].sum()) / total_oi if total_oi > 0 else 0
            
            # Delta metrics
            delta_imbalance = (df['pe_delta'].sum() - df['ce_delta'].sum())
            
            # FETCH HISTORICAL DATA FOR VELOCITY/ACCELERATION CALCULATIONS
            # Note: Background service refreshes every 3 minutes, so velocities are per 3-minute interval
            refresh_interval_minutes = 3  # Data refreshes every 3 minutes
            
            # Get previous data point - must be at least 1 minute old to avoid fetching current record
            prev_data = None
            # IMPROVED APPROACH: Fetch last 10 insertions and filter for actual data changes
            # API sometimes returns same data multiple times - we need records where values actually changed
            is_index = symbol in self.realtime_indices
            
            try:
                with self.db_manager.get_connection() as conn:
                    with conn.cursor() as cur:
                        # Get last 10 data points to find records with actual changes
                        cur.execute("""
                            SELECT atm_iv, atm_oi, timestamp, gamma_concentration
                            FROM gamma_exposure_history
                            WHERE symbol = %s AND expiry_date = %s
                            ORDER BY timestamp DESC
                            LIMIT 10
                        """, (symbol, expiry_date))
                        all_historical_data = cur.fetchall()
            except Exception as e:
                logger.debug(f"No historical data for {symbol}: {e}")
                all_historical_data = []
            
            # Filter for records where OI or IV actually changed (not duplicate API responses)
            historical_data = []
            prev_oi = None
            prev_iv = None
            
            for record in all_historical_data:
                curr_iv = float(record[0]) if record[0] is not None else 0
                curr_oi = float(record[1]) if record[1] is not None else 0
                
                # Include record if it's the first OR if OI/IV changed from previous
                if prev_oi is None or curr_oi != prev_oi or curr_iv != prev_iv:
                    historical_data.append(record)
                    prev_oi = curr_oi
                    prev_iv = curr_iv
                    
                    # Stop after finding 3 unique records
                    if len(historical_data) >= 3:
                        break
            
            # Calculate velocities and accelerations from records with actual changes
            if len(historical_data) >= 1:
                # Point 1 (most recent DIFFERENT data in DB)
                p1_iv, p1_oi, p1_time, p1_gamma = historical_data[0]
                p1_iv = float(p1_iv) if p1_iv is not None else 0
                p1_oi = float(p1_oi) if p1_oi is not None else 0
                p1_gamma = float(p1_gamma) if p1_gamma is not None else 0
                
                # Check if current data is different from most recent DB record
                has_changed = (atm_oi != p1_oi or atm_iv != p1_iv)
                
                if has_changed:
                    # Time difference between current (point 0) and previous (point 1)
                    # Use actual data fetch timestamp for consistency
                    current_timestamp = datetime.now(IST)  # When this data was fetched
                    time_diff_seconds = (current_timestamp - p1_time).total_seconds()
                    time_divisor = time_diff_seconds if is_index else time_diff_seconds / 60
                    
                    # Define caps based on symbol type (used in multiple places)
                    iv_cap = 0.16 if is_index else 10
                    oi_cap = 1666 if is_index else 100000
                    accel_cap = 166 if is_index else 10000
                    
                    # VELOCITY calculation: (current - previous) / time_diff
                    # IV velocity
                    if p1_iv > 0 and atm_iv != p1_iv:
                        iv_velocity = (atm_iv - p1_iv) / time_divisor
                        # Cap: -10%/+10% per min for stocks, -0.16%/+0.16% per sec for indices
                        iv_velocity = max(-iv_cap, min(iv_cap, iv_velocity))
                    else:
                        iv_velocity = 0
                    
                    # OI velocity
                    if atm_oi != p1_oi:
                        oi_velocity = (atm_oi - p1_oi) / time_divisor
                        # Cap: +/- 100,000 per min for stocks, +/- 1,666 per sec for indices
                        oi_velocity = max(-oi_cap, min(oi_cap, oi_velocity))
                    else:
                        oi_velocity = 0
                    
                    # ACCELERATION calculation: need 2 different historical points
                    if len(historical_data) >= 2:
                        # Point 2 (second most recent DIFFERENT data in DB)
                        p2_oi, p2_time = historical_data[1][1], historical_data[1][2]
                        p2_oi = float(p2_oi) if p2_oi is not None else 0
                        
                        # Time difference between point 1 and point 2
                        prev_time_diff_seconds = (p1_time - p2_time).total_seconds()
                        prev_time_divisor = prev_time_diff_seconds if is_index else prev_time_diff_seconds / 60
                        
                        # Previous velocity: (point1 - point2) / time_diff
                        if p1_oi != p2_oi and prev_time_divisor > 0:
                            prev_oi_velocity = (p1_oi - p2_oi) / prev_time_divisor
                            prev_oi_velocity = max(-oi_cap, min(oi_cap, prev_oi_velocity))
                            
                            # Acceleration: (current_velocity - previous_velocity) / time_diff
                            oi_acceleration = (oi_velocity - prev_oi_velocity) / time_divisor
                            # Cap: +/- 10,000/min² for stocks, +/- 166/sec² for indices
                            oi_acceleration = max(-accel_cap, min(accel_cap, oi_acceleration))
                        else:
                            oi_acceleration = 0
                    else:
                        # Only 1 previous different point - can't calculate acceleration
                        oi_acceleration = 0
                    
                    # UNWINDING INTENSITY calculation (percentage of starting OI being closed per hour)
                    # Unwinding = positions closing (negative OI change)
                    # Calculate as: (change / starting_OI) * 100, then annualize to per-hour rate
                    starting_oi = p1_oi  # OI at previous timestamp
                    oi_change = atm_oi - starting_oi
                    
                    if starting_oi > 0 and oi_change < 0:
                        # What % of previous OI has been closed?
                        unwinding_pct = abs(oi_change / starting_oi) * 100
                        # Standardize to per-hour rate for comparability
                        time_hours = time_diff_seconds / 3600
                        unwinding_intensity = (unwinding_pct / time_hours) if time_hours > 0 else 0
                        unwinding_intensity = min(100, unwinding_intensity)  # Cap at 100%/hour
                        
                        if is_index:
                            logger.info(f"   Unwinding: {oi_change:.0f} contracts ({unwinding_pct:.2f}% of {starting_oi:.0f}) in {time_diff_seconds:.0f}s = {unwinding_intensity:.2f}%/hour")
                    else:
                        unwinding_intensity = 0
                    
                    # Other metrics
                    gamma_conc_trend = (gamma_concentration - p1_gamma) / time_divisor if p1_gamma and gamma_concentration != p1_gamma else 0
                    iv_trend = 1 if atm_iv > p1_iv else -1 if atm_iv < p1_iv else 0
                    total_oi_change_rate = oi_velocity / total_oi if total_oi > 0 else 0
                    
                    # DEBUG: Log velocity calculations for indices
                    if is_index and (oi_velocity != 0 or iv_velocity != 0):
                        logger.info(f"🔍 {symbol} VELOCITY: IV={iv_velocity:.4f}%/sec, OI={oi_velocity:.2f}/sec, Accel={oi_acceleration:.2f}, Unwinding={unwinding_intensity:.2f}%")
                        logger.info(f"   Current: IV={atm_iv:.2f}, OI={atm_oi}, Previous: IV={p1_iv:.2f}, OI={p1_oi}, Time diff={time_diff_seconds:.1f}s")
                else:
                    # Current data same as last DB record - no change from API
                    logger.info(f"{symbol}: ⚠️ No change from previous record - Current OI={atm_oi}, IV={atm_iv:.2f} | Previous OI={p1_oi}, IV={p1_iv:.2f}")
                    iv_velocity = oi_velocity = oi_acceleration = 0
                    unwinding_intensity = 0
                    gamma_conc_trend = iv_trend = total_oi_change_rate = 0
                
            else:
                # First data point - no historical comparison
                logger.info(f"{symbol}: No historical data - first insertion")
                iv_velocity = oi_velocity = oi_acceleration = 0
                unwinding_intensity = 0
                gamma_conc_trend = iv_trend = total_oi_change_rate = 0
            
            # Calculate IV percentile (position in range)
            iv_values = list(df['ce_iv']) + list(df['pe_iv'])
            iv_values = [v for v in iv_values if v > 0]
            if iv_values and len(iv_values) > 1:
                iv_percentile = sum(1 for v in iv_values if v <= atm_iv) / len(iv_values)
            else:
                iv_percentile = 0.5
            
            # ==================================================================
            # ADAPTIVE GAMMA BLAST DETECTION WITH STATISTICAL THRESHOLDS
            # ==================================================================
            
            # Fetch historical data for adaptive z-score calculation (last 20 periods)
            try:
                with self.db_manager.get_connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute("""
                            SELECT atm_iv, atm_oi, gamma_concentration, net_gex
                            FROM gamma_exposure_history
                            WHERE symbol = %s AND expiry_date = %s
                            ORDER BY timestamp DESC
                            LIMIT 20
                        """, (symbol, expiry_date))
                        
                        historical_rows = cur.fetchall()
                        historical_data = [
                            {
                                'atm_iv': float(row[0]) if row[0] else 0,
                                'atm_oi': float(row[1]) if row[1] else 0,
                                'gamma_concentration': float(row[2]) if row[2] else 0,
                                'net_gex': float(row[3]) if row[3] else 0
                            }
                            for row in historical_rows
                        ]
            except Exception as hist_err:
                logger.debug(f"Could not fetch historical data for {symbol}: {hist_err}")
                historical_data = []
            
            # Calculate average IVs for skew
            call_ivs = [iv for iv in df['ce_iv'] if iv > 0]
            put_ivs = [iv for iv in df['pe_iv'] if iv > 0]
            ce_iv_avg = sum(call_ivs) / len(call_ivs) if call_ivs else 0
            pe_iv_avg = sum(put_ivs) / len(put_ivs) if put_ivs else 0
            
            # Calculate ITM change in OI (key directional indicator)
            ce_itm_chg_oi = df[df['strike'] < spot_price]['ce_chg_oi'].sum() if 'ce_chg_oi' in df.columns else 0
            pe_itm_chg_oi = df[df['strike'] > spot_price]['pe_chg_oi'].sum() if 'pe_chg_oi' in df.columns else 0
            
            # Prepare current data for detector
            current_data = {
                'atm_iv': atm_iv,
                'atm_oi': atm_oi,
                'gamma_concentration': gamma_concentration,
                'net_gex': total_net_gex,
                'spot_price': spot_price,
                'atm_strike': atm_strike,
                'ce_oi_total': df['ce_oi'].sum() if 'ce_oi' in df.columns else 0,
                'pe_oi_total': df['pe_oi'].sum() if 'pe_oi' in df.columns else 0,
                'ce_iv_avg': ce_iv_avg,
                'pe_iv_avg': pe_iv_avg,
                'ce_itm_chg_oi': ce_itm_chg_oi,
                'pe_itm_chg_oi': pe_itm_chg_oi
            }
            
            # Use adaptive detector (handles insufficient data gracefully with z-score=0)
            blast_signal = self.gamma_detector.detect_gamma_blast(
                symbol=symbol,
                current_data=current_data,
                historical_data=historical_data
            )
            
            gamma_blast_probability = blast_signal.probability
            predicted_direction = blast_signal.direction
            confidence_level = blast_signal.confidence
            time_to_blast_minutes = blast_signal.time_to_blast_min
            
            # Log adaptive triggers for transparency
            if blast_signal.triggers:
                logger.info(f"{symbol} Adaptive Gamma Blast: {gamma_blast_probability:.1%} | "
                           f"Triggers: {', '.join(blast_signal.triggers)}")
            elif len(historical_data) < 5:
                logger.debug(f"{symbol} Insufficient history ({len(historical_data)} periods) - using non-statistical signals only")
            
            # ==================================================================
            
            # Store gamma exposure history with calculated velocities
            timestamp = datetime.now(IST)
            self.db_manager.insert_gamma_exposure_history(
                symbol=symbol,
                expiry_date=expiry_date,
                timestamp=timestamp,
                atm_strike=atm_strike,
                net_gex=total_net_gex,
                total_positive_gex=total_positive_gex,
                total_negative_gex=total_negative_gex,
                zero_gamma_level=zero_gamma_level,
                atm_iv=atm_iv,
                iv_trend=iv_trend,
                iv_velocity=iv_velocity,  # Per-second for indices, per-minute for stocks
                iv_percentile=iv_percentile,
                implied_move=avg_iv * spot_price / 100,
                atm_oi=atm_oi,
                oi_acceleration=oi_acceleration,  # Per-sec² for indices, per-min² for stocks
                oi_velocity=oi_velocity,  # Per-second for indices, per-minute for stocks
                total_oi_change_rate=total_oi_change_rate,
                atm_gamma=atm_gamma,
                gamma_concentration=gamma_concentration,
                gamma_gradient=gamma_gradient,
                delta_skew=iv_skew,
                delta_ladder_imbalance=delta_imbalance,
                volatility_regime="NORMAL",
                regime_transition_score=0,
                gamma_blast_probability=gamma_blast_probability,
                time_to_blast_minutes=time_to_blast_minutes,
                predicted_direction=predicted_direction,
                confidence_level=confidence_level
            )
            
            logger.info(f"Stored gamma exposure for {symbol}: Prob={gamma_blast_probability:.2%}, Direction={predicted_direction}")
            
        except Exception as e:
            logger.error(f"Error calculating gamma exposure for {symbol}: {e}")
    
    def _calculate_and_store_itm_buckets(self, symbol: str, expiry_date: str, option_data: List[Dict], spot_price: float):
        """
        Calculate ITM bucket summaries (1-5 strikes) and store in database
        
        Args:
            symbol: Symbol name
            expiry_date: Expiry date
            option_data: Raw option chain data
            spot_price: Current spot price
        """
        try:
            import pandas as pd
            
            # Process option chain data into DataFrame
            processed_data = []
            
            for strike_data in option_data:
                if 'call_options' not in strike_data or 'put_options' not in strike_data:
                    continue
                
                strike_price = strike_data.get('strike_price', 0)
                if strike_price <= 0:
                    continue
                
                # Call options
                call_market = strike_data['call_options'].get('market_data', {})
                call_greeks = strike_data['call_options'].get('option_greeks', {})
                
                # Put options
                put_market = strike_data['put_options'].get('market_data', {})
                put_greeks = strike_data['put_options'].get('option_greeks', {})
                
                processed_data.append({
                    'strike': strike_price,
                    'ce_oi': call_market.get('oi', 0) or 0,
                    'ce_vol': call_market.get('volume', 0) or 0,
                    'ce_chgoi': (call_market.get('oi', 0) or 0) - (call_market.get('prev_oi', 0) or 0),
                    'ce_iv': call_greeks.get('iv', 0) or 0,
                    'ce_delta': call_greeks.get('delta', 0) or 0,
                    'pe_oi': put_market.get('oi', 0) or 0,
                    'pe_vol': put_market.get('volume', 0) or 0,
                    'pe_chgoi': (put_market.get('oi', 0) or 0) - (put_market.get('prev_oi', 0) or 0),
                    'pe_iv': put_greeks.get('iv', 0) or 0,
                    'pe_delta': put_greeks.get('delta', 0) or 0,
                })
            
            if not processed_data:
                return
            
            df = pd.DataFrame(processed_data)
            df = df[df['strike'] > 0].sort_values('strike').reset_index(drop=True)
            
            if df.empty:
                return
            
            # Find ATM strike
            atm_strike = df.loc[df['strike'].sub(spot_price).abs().idxmin(), 'strike']
            
            # Calculate ITM buckets for 1-5 strikes
            timestamp = datetime.now(IST)
            
            for itm_count in range(1, 6):
                # ITM Calls: below ATM (lower strikes)
                itm_calls = df[df['strike'] < atm_strike].tail(itm_count)
                
                # ITM Puts: above ATM (higher strikes)
                itm_puts = df[df['strike'] > atm_strike].head(itm_count)
                
                # Aggregate
                ce_oi = int(itm_calls['ce_oi'].sum()) if not itm_calls.empty else 0
                pe_oi = int(itm_puts['pe_oi'].sum()) if not itm_puts.empty else 0
                ce_vol = int(itm_calls['ce_vol'].sum()) if not itm_calls.empty else 0
                pe_vol = int(itm_puts['pe_vol'].sum()) if not itm_puts.empty else 0
                ce_chgoi = int(itm_calls['ce_chgoi'].sum()) if not itm_calls.empty else 0
                pe_chgoi = int(itm_puts['pe_chgoi'].sum()) if not itm_puts.empty else 0
                
                # Weighted IV and Delta
                ce_iv = (itm_calls['ce_iv'] * itm_calls['ce_oi']).sum() / ce_oi if ce_oi > 0 else 0
                ce_delta = (itm_calls['ce_delta'] * itm_calls['ce_oi']).sum() / ce_oi if ce_oi > 0 else 0
                pe_iv = (itm_puts['pe_iv'] * itm_puts['pe_oi']).sum() / pe_oi if pe_oi > 0 else 0
                pe_delta = (itm_puts['pe_delta'] * itm_puts['pe_oi']).sum() / pe_oi if pe_oi > 0 else 0
                
                # Insert into database
                self.db_manager.insert_itm_bucket_summary(
                    symbol=symbol,
                    expiry_date=expiry_date,
                    timestamp=timestamp,
                    itm_count=itm_count,
                    spot_price=spot_price,
                    atm_strike=atm_strike,
                    ce_oi=ce_oi,
                    ce_volume=ce_vol,
                    ce_chgoi=ce_chgoi,
                    ce_iv=ce_iv,
                    ce_delta=ce_delta,
                    pe_oi=pe_oi,
                    pe_volume=pe_vol,
                    pe_chgoi=pe_chgoi,
                    pe_iv=pe_iv,
                    pe_delta=pe_delta
                )
            
            logger.debug(f"Successfully calculated and stored ITM buckets for {symbol}")
            
        except Exception as e:
            logger.error(f"Error calculating ITM buckets for {symbol}: {e}", exc_info=True)
    
    def _process_symbol(self, symbol_config: Dict) -> bool:
        """
        Process a single symbol: get expiries and fetch data for multiple weeks
        UPDATED: Fetches current + next week expiries to ensure continuity
        
        Args:
            symbol_config: Symbol configuration dictionary
            
        Returns:
            True if at least one expiry was successfully processed
        """
        symbol = symbol_config['symbol']
        instrument_key = symbol_config['instrument_key']
        
        try:
            # Get multiple expiries (current + next week)
            expiry_dates = self._get_all_expiries(symbol, instrument_key, max_expiries=2)
            
            if not expiry_dates:
                # Fallback to single expiry method
                single_expiry = self._get_latest_expiry(symbol, instrument_key)
                if single_expiry:
                    expiry_dates = [single_expiry]
                else:
                    logger.warning(f"No expiry found for {symbol}")
                    return False
            
            # Fetch data for each expiry (typically current week and next week)
            success_count = 0
            for expiry_date in expiry_dates:
                try:
                    if self._fetch_and_store_option_chain(symbol, instrument_key, expiry_date):
                        success_count += 1
                        # Small delay between expiries to avoid rate limits
                        if len(expiry_dates) > 1:
                            time.sleep(0.2)
                except Exception as e:
                    logger.debug(f"Error fetching {symbol} {expiry_date}: {e}")
                    continue
            
            # Consider successful if at least one expiry was fetched
            if success_count > 0:
                logger.debug(f"✓ {symbol}: Fetched {success_count}/{len(expiry_dates)} expiries")
                return True
            else:
                logger.warning(f"Failed to fetch any expiry for {symbol}")
                return False
            
        except Exception as e:
            logger.error(f"Error processing symbol {symbol}: {e}")
            return False
    
    def _fetch_all_symbols(self):
        """Fetch data for all active symbols - OPTIMIZED FOR REAL-TIME"""
        # Check if market is open
        if not self._is_market_open():
            logger.info("Market is closed. Skipping data fetch. UI will show last fetched data from database.")
            return
        
        symbols = self._get_active_symbols()
        
        if not symbols:
            logger.warning("No active symbols to process")
            return
        
        # Filter out indices from main loop (they're handled by fast refresh thread)
        symbols = [s for s in symbols if s['symbol'] not in self.realtime_indices]
        
        if not symbols:
            logger.info("No stock symbols to process (indices handled by fast refresh)")
            return
        
        logger.info(f"📡 Fetching {len(symbols)} stock symbols via REST API (3-min cycle)...")
        logger.info(f"⚡ {len(self.realtime_indices)} indices updating every {self.index_refresh_interval}s via fast refresh thread")
        
        # HYBRID OPTIMIZATION:
        # - Indices: Fast refresh thread (90-second updates)
        # - Stocks: REST API every 3 minutes (~210 symbols)
        # - Rate limit friendly: ~1.2 calls/sec average
        
        batch_size = 43  # ~210 / 5 workers = ~42 per batch
        delay_between_batches = 0.5  # 500ms delay between batches
        delay_on_rate_limit = 30  # 30 seconds wait if rate limited
        
        success_count = 0
        total_symbols = len([s for s in symbols if s.get('is_active', True)])
        rate_limit_hit = False
        
        start_time = time.time()
        
        # Process symbols in batches with parallel workers
        for i in range(0, len(symbols), batch_size):
            batch = symbols[i:i + batch_size]
            batch_futures = {}
            
            # If rate limit was hit previously, wait before processing batch
            if rate_limit_hit:
                logger.warning(f"⏸️  Waiting {delay_on_rate_limit}s due to rate limit...")
                time.sleep(delay_on_rate_limit)
                rate_limit_hit = False
            
            # Submit entire batch to thread pool (5 workers process in parallel)
            for symbol_config in batch:
                if not symbol_config.get('is_active', True):
                    continue
                
                future = self.executor.submit(self._process_symbol, symbol_config)
                batch_futures[future] = symbol_config['symbol']
            
            # Wait for batch to complete
            for future in as_completed(batch_futures):
                symbol = batch_futures[future]
                try:
                    success = future.result()
                    if success:
                        success_count += 1
                except Exception as e:
                    error_str = str(e)
                    if 'UDAPI10005' in error_str or 'Too Many Request' in error_str or 'rate limit' in error_str.lower():
                        rate_limit_hit = True
                        logger.warning(f"⚠️  Rate limit hit on {symbol}")
                    else:
                        logger.debug(f"Exception processing {symbol}: {e}")
            
            # Small delay between batches
            if i + batch_size < len(symbols):
                time.sleep(delay_between_batches)
        
        elapsed = time.time() - start_time
        logger.info(f"✅ Completed in {elapsed:.1f}s: {success_count}/{total_symbols} symbols successful")
        logger.info(f"📊 Processing rate: {success_count/elapsed:.1f} symbols/sec")
    
    def _fast_index_refresh_loop(self):
        """Fast refresh loop for indices (90-second updates)"""
        logger.info("⚡ Index fast-refresh thread started")
        last_refresh = 0
        
        while self.running:
            try:
                now = time.time()
                
                # Check if it's time to refresh (every 30 seconds)
                if now - last_refresh >= self.index_refresh_interval:
                    # Check market status
                    if not self._is_market_open():
                        logger.debug("Market closed, skipping index refresh")
                        time.sleep(60)
                        continue
                    
                    # Get index symbols
                    all_symbols = self._get_active_symbols()
                    index_symbols = [s for s in all_symbols if s['symbol'] in self.realtime_indices]
                    
                    if index_symbols:
                        logger.debug(f"⚡ Refreshing {len(index_symbols)} indices...")
                        success_count = 0
                        
                        # Process indices one by one with delay to avoid rate limits
                        for idx, symbol_config in enumerate(index_symbols):
                            try:
                                if self._process_symbol(symbol_config):
                                    success_count += 1
                                # Add delay between indices to avoid rate limits (3s each = 15s total for 5 indices)
                                if idx < len(index_symbols) - 1:
                                    time.sleep(3.0)
                            except Exception as e:
                                logger.debug(f"Error refreshing {symbol_config['symbol']}: {e}")
                        
                        logger.info(f"⚡ Indices updated: {success_count}/{len(index_symbols)} successful")
                    
                    last_refresh = now
                
                # Sleep briefly to avoid busy-waiting
                time.sleep(1)
                
            except Exception as e:
                logger.error(f"Error in index fast-refresh loop: {e}")
                time.sleep(5)
        
        logger.info("⚡ Index fast-refresh thread stopped")
    
    def start(self):
        """Start the background service - Only fetches during market hours"""
        if self.running:
            logger.warning("Service is already running")
            return
        
        self.running = True
        mode_str = "REST API MODE"
        if self.force_mode:
            mode_str += " [FORCE MODE - Market hours check disabled]"
        logger.info(f"🚀 Starting Option Chain Background Service - {mode_str}")
        logger.info("=" * 70)
        
        if self.force_mode:
            logger.warning("⚠️  FORCE MODE ENABLED: Service will run regardless of market hours")
            logger.warning("   This is useful for testing but should be disabled in production")
            logger.info("")
        
        logger.info(f"⚡ FAST REFRESH: Indices (REST API)")
        logger.info(f"   • {', '.join(self.realtime_indices)}")
        logger.info(f"   • Refresh interval: {self.index_refresh_interval} seconds")
        logger.info("")
        
        logger.info(f"📊 PERIODIC: All stocks (REST API)")
        logger.info(f"   • Refresh interval: {self.refresh_interval} seconds (3 minutes)")
        logger.info("   • Symbols: 215 F&O stocks")
        logger.info("   • Workers: 5 parallel threads")
        logger.info("")
        logger.info("💾 Expiry cache: Daily (reset at market close)")
        logger.info("🕐 Market hours: 9:15 AM - 3:30 PM IST (Monday-Friday)")
        logger.info("=" * 70)
        
        # Clean up non-market hours data at startup
        try:
            self._cleanup_non_market_hours_data()
        except Exception as e:
            logger.error(f"Error during startup cleanup: {e}")
        
        # Start separate thread for fast index refresh
        index_thread = threading.Thread(target=self._fast_index_refresh_loop, daemon=True)
        index_thread.start()
        logger.info("⚡ Started fast refresh thread for indices (90-second updates)")
        
        consecutive_errors = 0
        max_consecutive_errors = 10  # Allow 10 consecutive errors before stopping
        last_token_check = 0
        token_check_interval = 300  # Check token every 5 minutes
        
        try:
            while self.running:
                start_time = time.time()
                
                try:
                    # Periodically check and refresh token if needed (every 5 minutes)
                    now = time.time()
                    if now - last_token_check >= token_check_interval:
                        logger.info("🔄 Periodic token check (every 5 minutes)...")
                        if self._refresh_access_token_if_needed():
                            logger.info("✅ Token refreshed during periodic check")
                        last_token_check = now
                    
                    # Check market status (unless force mode is enabled)
                    if not self._is_market_open():
                        if self.force_mode:
                            # Force mode: continue even when market is closed
                            logger.info("⚠️  Force mode: Market is closed but continuing to fetch data...")
                        else:
                            # Market is closed - wait and check again
                            now = datetime.now(IST)
                            current_time = now.time()
                            market_close = datetime.strptime("15:30", "%H:%M").time()
                            
                            # If it's after 3:30 PM, stop the service until next market open
                            if current_time > market_close:
                                logger.info(f"Market closed at 3:30 PM. Current time: {now.strftime('%Y-%m-%d %H:%M:%S IST')}")
                                logger.info("Background service will stop fetching data. Dashboard will display data until 3:30 PM.")
                                logger.info("Restart the service tomorrow during market hours (9:15 AM - 3:30 PM).")
                                logger.info("Or use --force flag to run during market closed hours for testing.")
                                self.stop()
                                break
                            else:
                                logger.info(f"Market not yet open (Current time: {now.strftime('%Y-%m-%d %H:%M:%S IST')}). Waiting 60 seconds...")
                                logger.info("Market hours: 9:15 AM - 3:30 PM IST (Monday-Friday)")
                                time.sleep(60)  # Check every minute when market is closed
                            continue
                    
                    # Market is open - fetch data
                    logger.info("Market is open. Fetching data for all symbols...")
                    self._fetch_all_symbols()
                    
                    # Reset error counter on successful fetch
                    consecutive_errors = 0
                    
                except Exception as fetch_error:
                    consecutive_errors += 1
                    error_str = str(fetch_error)
                    
                    # Check if it's a token expiration error (UDAPI100050)
                    is_token_error = any(keyword in error_str for keyword in 
                        ['UDAPI100050', 'Invalid token', 'token expired', 'authentication failed'])
                    
                    # Check if it's a network/connection error
                    is_network_error = any(keyword in error_str.lower() for keyword in 
                        ['connection', 'timeout', 'network', 'unreachable', 'resolve', 'dns'])
                    
                    if is_token_error:
                        logger.warning("=" * 70)
                        logger.warning("⚠️ UPSTOX API TOKEN EXPIRED OR INVALID - Attempting auto-refresh...")
                        logger.warning(f"Error: {fetch_error}")
                        logger.warning("=" * 70)
                        
                        # Attempt automatic token refresh (fully automatic, no manual steps needed)
                        logger.info("🔄 Attempting automatic token refresh...")
                        if self._refresh_access_token_if_needed():
                            logger.info("✅ Token automatically refreshed! Continuing with new token...")
                            consecutive_errors = 0  # Reset error count on successful refresh
                            time.sleep(5)  # Brief pause before retry
                        else:
                            # Auto-refresh failed - try to get refresh_token from token file
                            logger.warning("⚠️ Auto-refresh failed. Checking for refresh_token in token file...")
                            try:
                                import json
                                from pathlib import Path
                                token_file = Path('data/upstox_tokens.json')
                                if token_file.exists():
                                    with open(token_file) as f:
                                        token_data = json.load(f)
                                    refresh_token = token_data.get('refresh_token')
                                    if refresh_token:
                                        logger.info("📦 Found refresh_token in token file, updating secrets.toml...")
                                        self.credentials['refresh_token'] = refresh_token
                                        # Try refresh again with the found refresh_token
                                        if self._refresh_access_token_if_needed():
                                            logger.info("✅ Token automatically refreshed using refresh_token from token file!")
                                            consecutive_errors = 0
                                            time.sleep(5)
                                            continue
                            except Exception as e:
                                logger.debug(f"Error checking token file: {e}")
                            
                            logger.error("❌ Automatic token refresh failed!")
                            logger.error("⚠️  The system cannot automatically refresh the token.")
                            logger.error("   This usually means:")
                            logger.error("   1. No refresh_token is available")
                            logger.error("   2. The refresh_token has expired")
                            logger.error("   3. API credentials are invalid")
                            logger.error("")
                            logger.error("   SOLUTION: Re-authenticate with Upstox to get new tokens.")
                            logger.error("   The system will continue retrying, but data collection will fail until tokens are updated.")
                            logger.error("=" * 70)
                            logger.error(f"Token error detected (attempt {consecutive_errors}/{max_consecutive_errors})")
                            time.sleep(60)  # Wait longer for token errors
                    elif is_network_error:
                        logger.warning(f"Network error detected (attempt {consecutive_errors}/{max_consecutive_errors}): {fetch_error}")
                        logger.info("Waiting 30 seconds before retry...")
                        time.sleep(30)
                    else:
                        logger.error(f"Error in fetch cycle (attempt {consecutive_errors}/{max_consecutive_errors}): {fetch_error}")
                        time.sleep(10)
                    
                    # Only stop if we've had too many consecutive errors (but allow more for token errors)
                    max_errors_for_token = max_consecutive_errors * 2  # Allow more retries for token errors
                    error_limit = max_errors_for_token if is_token_error else max_consecutive_errors
                    
                    if consecutive_errors >= error_limit:
                        logger.error("=" * 70)
                        logger.error(f"Too many consecutive errors ({consecutive_errors}). Stopping service.")
                        if is_token_error:
                            logger.error("CRITICAL: Token expiration detected. Please update your Upstox API token.")
                        else:
                            logger.error("Please check your internet connection and API credentials.")
                        logger.error("=" * 70)
                        self.stop()
                        break
                    
                    # Continue to next iteration even after error
                    logger.info("Continuing to next cycle despite error...")
                
                # Calculate sleep time to maintain refresh interval
                elapsed = time.time() - start_time
                sleep_time = max(0, self.refresh_interval - elapsed)
                
                if sleep_time > 0:
                    logger.debug(f"Sleeping for {sleep_time:.2f} seconds...")
                    time.sleep(sleep_time)
                
        except KeyboardInterrupt:
            logger.info("Received keyboard interrupt")
        except Exception as e:
            logger.error(f"Fatal error in main loop: {e}")
        finally:
            self.stop()
    
    def stop(self):
        """Stop the background service"""
        if not self.running:
            return
        
        logger.info("Stopping background service...")
        self.running = False
        
        if self.executor:
            self.executor.shutdown(wait=True)
            logger.info("Thread pool executor shut down")
        
        if self.db_manager:
            self.db_manager.close()
            logger.info("Database connections closed")
        
        logger.info("Background service stopped")


def main():
    """Main entry point for background service"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Option Chain Background Service')
    parser.add_argument(
        '--interval',
        type=int,
        default=180,
        help='Refresh interval in seconds when market is open (default: 180 = 3 minutes, optimized to avoid rate limiting)'
    )
    parser.add_argument(
        '--force',
        action='store_true',
        help='Force mode: Run service regardless of market hours (useful for testing)'
    )
    
    args = parser.parse_args()
    
    service = OptionChainBackgroundService(refresh_interval=args.interval, force_mode=args.force)
    
    try:
        service.start()
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()

