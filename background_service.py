"""
Background Service for Continuous Option Chain Data Fetching
Runs independently to fetch data for all configured symbols
"""

import time
import logging
import signal
import sys
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import pytz
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
import os
import toml

from database import TimescaleDBManager
from upstox_api import UpstoxAPI
from websocket_manager import UpstoxWebSocketManager

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


class OptionChainBackgroundService:
    """Background service for fetching option chain data for all symbols"""
    
    def __init__(self, refresh_interval: int = 30, force_run: bool = False):
        """
        Initialize background service
        
        Args:
            refresh_interval: Default refresh interval in seconds
            force_run: If True, run even when market is closed (for testing)
        """
        self.refresh_interval = refresh_interval
        self.force_run = force_run
        self.running = False
        self.db_manager = None
        self.upstox_api = None
        self.websocket_manager = None
        self.symbol_configs = {}
        self.executor = None
        self.use_websocket = False  # Disabled - HTTP 530 errors, using REST API only
        self.expiry_cache = {}  # Cache expiry dates to avoid repeated API calls
        # Removed market_closed_fetched - always fetch continuously
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
            
            # Initialize Upstox API
            self.upstox_api = UpstoxAPI()
            self.upstox_api.access_token = self.credentials['access_token']
            logger.info("Upstox API initialized")
            
            # WebSocket disabled due to HTTP 530 errors - using REST API with aggressive rate limiting
            if self.use_websocket:
                try:
                    self.websocket_manager = UpstoxWebSocketManager(self.credentials['access_token'])
                    self.websocket_manager.start()
                    # Wait a bit for WebSocket to connect
                    time.sleep(2)
                    if self.websocket_manager.is_connected:
                        logger.info("WebSocket manager initialized and connected")
                    else:
                        logger.warning("WebSocket manager started but not connected. Falling back to REST API.")
                        self.use_websocket = False
                        self.websocket_manager = None
                except Exception as ws_error:
                    logger.warning(f"WebSocket initialization failed: {ws_error}. Falling back to REST API only.")
                    self.use_websocket = False
                    self.websocket_manager = None
            
            # Initialize thread pool executor with reduced workers to avoid rate limiting
            self.executor = ThreadPoolExecutor(max_workers=3, thread_name_prefix="OptionChainFetcher")
            logger.info("Thread pool executor initialized (3 workers to avoid rate limiting)")
            
        except Exception as e:
            logger.error(f"Failed to initialize components: {e}")
            raise
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals gracefully"""
        logger.info(f"Received signal {signum}, shutting down gracefully...")
        self.stop()
        sys.exit(0)
    
    def _is_market_open(self) -> bool:
        """Check if market is currently open"""
        now = datetime.now(IST)
        current_time = now.time()
        weekday = now.weekday()
        
        # Market is closed on weekends
        if weekday >= 5:  # Saturday = 5, Sunday = 6
            return False
        
        # Market hours: 9:15 AM to 3:30 PM IST
        market_open = datetime.strptime("09:15", "%H:%M").time()
        market_close = datetime.strptime("15:30", "%H:%M").time()
        
        return market_open <= current_time <= market_close
    
    def _get_fo_instruments(self) -> Dict[str, str]:
        """Get F&O instruments mapping"""
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
            fno_df = df[(df['segment'] == "NSE_FO") | (df['segment'] == "NSE_INDEX")]
            fno_stocks = [x for x in fno_df['name'].unique()]

            fo_instruments = {row['asset_symbol']: row['asset_key'] 
                            for _, row in fno_df.iterrows() 
                            if row['name'] in fno_stocks}

            # Add indices
            fo_instruments.update({
                "NIFTY": "NSE_INDEX|Nifty 50",
                "BANKNIFTY": "NSE_INDEX|Nifty Bank",
                "FINNIFTY": "NSE_INDEX|Nifty Fin Service",
                "MIDCPNIFTY": "NSE_INDEX|NIFTY MID SELECT",
                "SENSEX": "BSE_INDEX|SENSEX"
            })
            
            return fo_instruments
        except Exception as e:
            logger.error(f"Failed to get F&O instruments: {e}")
            return {
                "NIFTY": "NSE_INDEX|Nifty 50",
                "BANKNIFTY": "NSE_INDEX|Nifty Bank",
                "FINNIFTY": "NSE_INDEX|Nifty Fin Service",
                "MIDCPNIFTY": "NSE_INDEX|NIFTY MID SELECT"
            }
    
    def _get_active_symbols(self) -> List[Dict]:
        """Get list of active symbols - always fetch ALL F&O instruments"""
        # Always fetch ALL F&O instruments (like UI does) to ensure we process all symbols
        logger.info("Fetching all F&O instruments for background processing...")
        fo_instruments = self._get_fo_instruments()
        
        if not fo_instruments:
            logger.warning("Failed to fetch F&O instruments, using default list")
            default_symbols = ["NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY"]
            fo_instruments = {
                "NIFTY": "NSE_INDEX|Nifty 50",
                "BANKNIFTY": "NSE_INDEX|Nifty Bank",
                "FINNIFTY": "NSE_INDEX|Nifty Fin Service",
                "MIDCPNIFTY": "NSE_INDEX|NIFTY MID SELECT"
            }
        
        symbols = []
        symbol_count = 0
        
        # Process all F&O instruments
        for symbol, instrument_key in fo_instruments.items():
            try:
                # Only process if it's a valid F&O instrument
                # Skip if instrument_key is None or empty
                if not instrument_key or not symbol:
                    continue
                
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
                
                # Log progress for large lists
                if symbol_count % 50 == 0:
                    logger.info(f"Processed {symbol_count} symbols...")
                    
            except Exception as e:
                logger.warning(f"Failed to process symbol {symbol}: {e}")
                continue
        
        logger.info(f"Total {symbol_count} F&O symbols configured for background processing")
        return symbols
    
    def _get_latest_expiry(self, symbol: str, instrument_key: str) -> Optional[str]:
        """Get the latest (nearest) expiry date for a symbol with caching and aggressive rate limiting"""
        # Check cache first (expiry dates don't change frequently)
        cache_key = f"{symbol}_{instrument_key}"
        if cache_key in self.expiry_cache:
            cached_expiry, cache_time = self.expiry_cache[cache_key]
            # Cache valid for 1 hour (3600 seconds)
            if time.time() - cache_time < 3600:
                logger.debug(f"Using cached expiry for {symbol}: {cached_expiry}")
                return cached_expiry
        
        # If not in cache or expired, fetch from API
        # Upstox allows: 50/sec, 500/min, 2000/30min for standard APIs
        max_retries = 2
        retry_delay = 5  # 5 seconds delay on retry
        
        for attempt in range(max_retries):
            try:
                # Small delay to respect rate limits (50/sec = 0.02s per request, we use 0.2s for safety)
                time.sleep(0.2)  # 200ms delay before each expiry API call
                
                contracts_data, error = self.upstox_api.get_option_contracts(instrument_key)
                
                # Check for rate limit error
                if error and isinstance(error, dict):
                    errors = error.get('errors', [])
                    for err in errors:
                        if err.get('errorCode') == 'UDAPI10005' or 'Too Many Request' in str(err.get('message', '')):
                            if attempt < max_retries - 1:
                                wait_time = retry_delay * (2 ** attempt)  # Exponential backoff: 5s, 10s
                                logger.warning(f"Rate limit getting expiry for {symbol}. Waiting {wait_time}s before retry {attempt + 1}/{max_retries}...")
                                time.sleep(wait_time)
                                continue
                            else:
                                logger.error(f"Max retries reached getting expiry for {symbol} due to rate limiting. Using cached if available.")
                                # Try to return cached value even if expired
                                if cache_key in self.expiry_cache:
                                    cached_expiry, _ = self.expiry_cache[cache_key]
                                    logger.info(f"Using expired cache for {symbol}: {cached_expiry}")
                                    return cached_expiry
                                return None
                
                if contracts_data and 'data' in contracts_data:
                    # Get all expiry dates and sort them (earliest first = current expiry)
                    expiry_dates = sorted({c['expiry'] for c in contracts_data['data'] if 'expiry' in c})
                    if expiry_dates:
                        # Return the earliest (nearest/current) expiry
                        nearest_expiry = expiry_dates[0]
                        # Cache the result
                        self.expiry_cache[cache_key] = (nearest_expiry, time.time())
                        logger.debug(f"Found and cached nearest expiry for {symbol}: {nearest_expiry}")
                        return nearest_expiry
                
                # If no data but no error, might be valid (no contracts available)
                if not error:
                    logger.debug(f"No expiry dates found in contracts data for {symbol}")
                    return None
                
                # If error and not rate limit, log and retry
                if error and attempt < max_retries - 1:
                    logger.warning(f"Error getting expiry for {symbol} (attempt {attempt + 1}/{max_retries}): {error}")
                    time.sleep(retry_delay)
                    continue
                else:
                    logger.error(f"Failed to get expiry for {symbol}: {error}")
                    return None
                    
            except Exception as e:
                if attempt < max_retries - 1:
                    logger.warning(f"Exception getting expiry for {symbol} (attempt {attempt + 1}/{max_retries}): {e}")
                    time.sleep(retry_delay)
                    continue
                else:
                    logger.error(f"Failed to get expiry for {symbol}: {e}")
                    return None
        
        return None
    
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
            # Small delay to respect rate limits (50/sec = 0.02s per request, we use 0.2s for safety)
            time.sleep(0.2)  # 200ms delay before option chain API call
            
            # Fetch option chain data
            option_data, error = self.upstox_api.get_pc_option_chain(instrument_key, expiry_date)
            
            if not option_data or error is not None:
                # Check if it's a rate limit error
                if error and isinstance(error, dict):
                    errors = error.get('errors', [])
                    for err in errors:
                        if err.get('errorCode') == 'UDAPI10005' or 'Too Many Request' in str(err.get('message', '')):
                            logger.warning(f"Rate limit fetching option chain for {symbol}. Will skip and retry later.")
                            return False
                logger.warning(f"Failed to fetch data for {symbol}: {error}")
                return False
            
            if 'data' not in option_data or not option_data['data']:
                logger.warning(f"No data returned for {symbol}")
                return False
            
            # Extract spot price from API response
            spot_price = 0
            # Try to get spot price from response (could be at top level or in first strike)
            if 'underlying_spot_price' in option_data:
                spot_price = float(option_data.get('underlying_spot_price', 0))
            elif option_data['data'] and len(option_data['data']) > 0:
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
                # Note: Sentiment calculation is done ONLY in Option Chain Analysis (optionchain.py)
                # When user views a symbol in Option Chain Analysis, it calculates sentiment and stores it
                # This ensures single source of truth for sentiment calculation
            else:
                logger.warning(f"Failed to store data for {symbol}")
            
            return success
            
        except Exception as e:
            logger.error(f"Error fetching/storing data for {symbol}: {e}")
            return False
    
    def _process_symbol(self, symbol_config: Dict) -> bool:
        """
        Process a single symbol: get expiry and fetch data
        
        Args:
            symbol_config: Symbol configuration dictionary
            
        Returns:
            True if successful, False otherwise
        """
        symbol = symbol_config['symbol']
        instrument_key = symbol_config['instrument_key']
        
        try:
            # Get latest expiry
            expiry_date = self._get_latest_expiry(symbol, instrument_key)
            
            if not expiry_date:
                logger.warning(f"No expiry found for {symbol}")
                return False
            
            # Fetch and store data
            return self._fetch_and_store_option_chain(symbol, instrument_key, expiry_date)
            
        except Exception as e:
            logger.error(f"Error processing symbol {symbol}: {e}")
            return False
    
    def _fetch_all_symbols(self):
        """Fetch data for all active symbols - Only during market hours"""
        # Check if market is open (unless force_run is enabled for testing)
        if not self.force_run and not self._is_market_open():
            logger.info("Market is closed. Skipping data fetch. UI will show last fetched data from database.")
            return
        
        symbols = self._get_active_symbols()
        
        if not symbols:
            logger.warning("No active symbols to process")
            return
        
        logger.info(f"Fetching data for {len(symbols)} symbols...")
        
        # Process symbols in small batches to optimize rate limit usage
        # Upstox allows: 50/sec, 500/min, 2000/30min for standard APIs
        # Each symbol needs: 1 expiry call + 1 option chain call = 2 API calls
        # We can safely process 10 symbols in parallel (20 API calls) with small delays
        batch_size = 10  # Process 10 symbols at a time
        delay_between_batches = 1  # 1 second delay between batches
        delay_between_requests = 0.1  # 100ms delay between individual requests
        delay_on_rate_limit = 10  # 10 seconds wait if rate limited
        
        success_count = 0
        total_symbols = len([s for s in symbols if s.get('is_active', True)])
        rate_limit_hit = False
        
        # Process symbols in batches
        for i in range(0, len(symbols), batch_size):
            batch = symbols[i:i + batch_size]
            batch_futures = {}
            
            # If rate limit was hit previously, wait before processing batch
            if rate_limit_hit:
                logger.warning(f"Rate limit was hit. Waiting {delay_on_rate_limit} seconds before next batch...")
                time.sleep(delay_on_rate_limit)
                rate_limit_hit = False
            
            # Submit batch with small delays
            for symbol_config in batch:
                if not symbol_config.get('is_active', True):
                    continue
                
                # Small delay before each request
                time.sleep(delay_between_requests)
                
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
                        logger.warning(f"Rate limit detected for {symbol}")
                    else:
                        logger.error(f"Exception processing {symbol}: {e}")
            
            # Delay between batches
            if i + batch_size < len(symbols):
                time.sleep(delay_between_batches)
        
        logger.info(f"Completed fetching: {success_count}/{total_symbols} symbols successful")
    
    def start(self):
        """Start the background service - Only fetches during market hours"""
        if self.running:
            logger.warning("Service is already running")
            return
        
        self.running = True
        logger.info("Starting Option Chain Background Service...")
        logger.info("Market hours: 9:15 AM - 3:30 PM IST (Monday-Friday)")
        logger.info(f"Refresh interval: {self.refresh_interval} seconds (when market is open)")
        logger.info("Rate limiting: Batch processing (10 symbols), optimized for Upstox limits (50/sec, 500/min)")
        logger.info("Expiry caching: Enabled (1 hour cache) - reduces API calls significantly")
        logger.info("WebSocket: Disabled (using REST API only)")
        
        try:
            while self.running:
                start_time = time.time()
                
                # Check market status
                if not self.force_run and not self._is_market_open():
                    # Market is closed - wait and check again
                    now = datetime.now(IST)
                    logger.info(f"Market is closed (Current time: {now.strftime('%Y-%m-%d %H:%M:%S IST')}). Waiting 60 seconds before checking again...")
                    logger.info("UI will continue to show last fetched data from database.")
                    time.sleep(60)  # Check every minute when market is closed
                    continue
                
                # Market is open - fetch data
                logger.info("Market is open. Fetching data for all symbols...")
                self._fetch_all_symbols()
                
                # Calculate sleep time to maintain refresh interval
                elapsed = time.time() - start_time
                sleep_time = max(0, self.refresh_interval - elapsed)
                
                if sleep_time > 0:
                    logger.debug(f"Sleeping for {sleep_time:.2f} seconds...")
                    time.sleep(sleep_time)
                
        except KeyboardInterrupt:
            logger.info("Received keyboard interrupt")
        except Exception as e:
            logger.error(f"Unexpected error in main loop: {e}")
        finally:
            self.stop()
    
    def stop(self):
        """Stop the background service"""
        if not self.running:
            return
        
        logger.info("Stopping background service...")
        self.running = False
        
        if self.websocket_manager:
            self.websocket_manager.stop()
            logger.info("WebSocket manager stopped")
        
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
        default=60,
        help='Refresh interval in seconds when market is open (default: 60 = 1 minute)'
    )
    parser.add_argument(
        '--force',
        action='store_true',
        help='Run even when market is closed (for testing)'
    )
    
    args = parser.parse_args()
    
    service = OptionChainBackgroundService(refresh_interval=args.interval, force_run=args.force)
    
    try:
        service.start()
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()

