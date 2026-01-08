"""
TimescaleDB Database Layer for Option Chain Data Storage
Production-grade database operations with connection pooling and error handling
"""

import psycopg2
from psycopg2.extras import execute_values
from psycopg2.pool import ThreadedConnectionPool
from contextlib import contextmanager
import logging
from datetime import datetime
import pytz
from typing import List, Dict, Optional, Tuple
import os
import pandas as pd
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

IST = pytz.timezone('Asia/Kolkata')


class TimescaleDBManager:
    """Manages TimescaleDB connections and operations for option chain data"""
    
    def __init__(self, min_conn=2, max_conn=10):
        """
        Initialize database connection pool
        
        Args:
            min_conn: Minimum number of connections in pool
            max_conn: Maximum number of connections in pool
        """
        self.min_conn = min_conn
        self.max_conn = max_conn
        self.pool = None
        self._initialize_pool()
        self._ensure_schema()
    
    def _get_db_config(self):
        """Get database configuration from environment variables"""
        return {
            'host': os.getenv('DB_HOST', 'localhost'),
            'port': os.getenv('DB_PORT', '5432'),
            'database': os.getenv('DB_NAME', 'optionchain'),
            'user': os.getenv('DB_USER', 'postgres'),
            'password': os.getenv('DB_PASSWORD', 'postgres')
        }
    
    def _initialize_pool(self):
        """Initialize connection pool"""
        try:
            config = self._get_db_config()
            self.pool = ThreadedConnectionPool(
                self.min_conn,
                self.max_conn,
                **config
            )
            logger.info("Database connection pool initialized successfully")
        except Exception as e:
            logger.warning(f"Failed to initialize connection pool: {e}")
            logger.warning("Database operations will be disabled. Please ensure TimescaleDB is running.")
            self.pool = None
    
    @contextmanager
    def get_connection(self):
        """Get a connection from the pool (context manager)"""
        if self.pool is None:
            raise ConnectionError("Database connection pool not initialized. Please ensure TimescaleDB is running.")
        
        conn = None
        try:
            conn = self.pool.getconn()
            yield conn
            conn.commit()
        except Exception as e:
            if conn:
                conn.rollback()
            logger.error(f"Database operation failed: {e}")
            raise
        finally:
            if conn:
                self.pool.putconn(conn)
    
    def _ensure_schema(self):
        """Create database schema and enable TimescaleDB extension"""
        if self.pool is None:
            logger.warning("Skipping schema creation - database not available")
            return
        
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    # Enable TimescaleDB extension
                    cur.execute("""
                        CREATE EXTENSION IF NOT EXISTS timescaledb;
                    """)
                    
                    # Create option_chain_data hypertable
                    cur.execute("""
                        CREATE TABLE IF NOT EXISTS option_chain_data (
                        timestamp TIMESTAMPTZ NOT NULL,
                        symbol VARCHAR(50) NOT NULL,
                        instrument_key VARCHAR(100) NOT NULL,
                        expiry_date DATE NOT NULL,
                        strike_price NUMERIC(10, 2) NOT NULL,
                        option_type VARCHAR(2) NOT NULL CHECK (option_type IN ('CE', 'PE')),
                        
                        -- Market Data
                        ltp NUMERIC(10, 2),
                        volume BIGINT,
                        oi BIGINT,
                        prev_oi BIGINT,
                        chg_oi BIGINT,
                        close_price NUMERIC(10, 2),
                        change NUMERIC(10, 2),
                        
                        -- Greeks
                        iv NUMERIC(8, 4),
                        delta NUMERIC(8, 6),
                        gamma NUMERIC(10, 8),
                        theta NUMERIC(10, 6),
                        vega NUMERIC(10, 6),
                        
                        -- Spot price at time of data capture
                        spot_price NUMERIC(10, 2),
                        
                            PRIMARY KEY (timestamp, symbol, expiry_date, strike_price, option_type)
                        );
                    """)
                    
                    # Convert to hypertable if not already
                    cur.execute("""
                        SELECT COUNT(*) FROM timescaledb_information.hypertables 
                        WHERE hypertable_name = 'option_chain_data';
                    """)
                    if cur.fetchone()[0] == 0:
                        cur.execute("""
                            SELECT create_hypertable('option_chain_data', 'timestamp', 
                                chunk_time_interval => INTERVAL '1 day',
                                if_not_exists => TRUE);
                        """)
                        logger.info("Created hypertable for option_chain_data")
                    
                    # Create indexes for faster queries
                    cur.execute("""
                        CREATE INDEX IF NOT EXISTS idx_option_chain_symbol_expiry 
                        ON option_chain_data (symbol, expiry_date, timestamp DESC);
                    """)
                    
                    cur.execute("""
                        CREATE INDEX IF NOT EXISTS idx_option_chain_latest 
                        ON option_chain_data (symbol, expiry_date, timestamp DESC);
                    """)
                    
                    # Create metadata table for tracking symbol configurations
                    cur.execute("""
                        CREATE TABLE IF NOT EXISTS symbol_config (
                            symbol VARCHAR(50) PRIMARY KEY,
                            instrument_key VARCHAR(100) NOT NULL,
                            is_active BOOLEAN DEFAULT TRUE,
                            last_updated TIMESTAMPTZ DEFAULT NOW(),
                            refresh_interval_seconds INTEGER DEFAULT 30
                        );
                    """)
                    
                    # Create sentiment_scores table to store calculated sentiment
                    cur.execute("""
                        CREATE TABLE IF NOT EXISTS sentiment_scores (
                            timestamp TIMESTAMPTZ NOT NULL,
                            symbol VARCHAR(50) NOT NULL,
                            expiry_date DATE NOT NULL,
                            sentiment_score NUMERIC(8, 2) NOT NULL,
                            sentiment VARCHAR(50) NOT NULL,
                            confidence VARCHAR(20) NOT NULL,
                            spot_price NUMERIC(10, 2) NOT NULL,
                            pcr_oi NUMERIC(8, 4),
                            pcr_chgoi NUMERIC(8, 4),
                            pcr_volume NUMERIC(8, 4),
                            PRIMARY KEY (timestamp, symbol, expiry_date)
                        );
                    """)
                    
                    # Convert sentiment_scores to hypertable if not already
                    cur.execute("""
                        SELECT COUNT(*) FROM timescaledb_information.hypertables 
                        WHERE hypertable_name = 'sentiment_scores';
                    """)
                    if cur.fetchone()[0] == 0:
                        cur.execute("""
                            SELECT create_hypertable('sentiment_scores', 'timestamp', 
                                chunk_time_interval => INTERVAL '1 day',
                                if_not_exists => TRUE);
                        """)
                        logger.info("Created hypertable for sentiment_scores")
                    
                    # Create index for sentiment queries
                    cur.execute("""
                        CREATE INDEX IF NOT EXISTS idx_sentiment_latest 
                        ON sentiment_scores (symbol, expiry_date, timestamp DESC);
                    """)
                    
                    cur.execute("""
                        CREATE INDEX IF NOT EXISTS idx_sentiment_score 
                        ON sentiment_scores (sentiment_score, timestamp DESC);
                    """)
                    
                    # Create ITM bucket summaries table for storing pre-calculated ITM data
                    cur.execute("""
                        CREATE TABLE IF NOT EXISTS itm_bucket_summaries (
                            timestamp TIMESTAMPTZ NOT NULL,
                            symbol VARCHAR(50) NOT NULL,
                            expiry_date DATE NOT NULL,
                            itm_count INTEGER NOT NULL CHECK (itm_count BETWEEN 1 AND 5),
                            
                            -- Spot price at time of calculation
                            spot_price NUMERIC(10, 2) NOT NULL,
                            atm_strike NUMERIC(10, 2) NOT NULL,
                            
                            -- Call OI/Volume aggregates (ITM calls below ATM)
                            ce_oi BIGINT,
                            ce_volume BIGINT,
                            ce_chgoi BIGINT,
                            ce_iv NUMERIC(8, 4),
                            ce_delta NUMERIC(8, 6),
                            
                            -- Put OI/Volume aggregates (ITM puts above ATM)
                            pe_oi BIGINT,
                            pe_volume BIGINT,
                            pe_chgoi BIGINT,
                            pe_iv NUMERIC(8, 4),
                            pe_delta NUMERIC(8, 6),
                            
                            -- PCR metrics
                            pcr_oi NUMERIC(8, 4),
                            pcr_volume NUMERIC(8, 4),
                            pcr_chgoi NUMERIC(8, 4),
                            
                            PRIMARY KEY (timestamp, symbol, expiry_date, itm_count)
                        );
                    """)
                    
                    # Convert to hypertable if not already
                    cur.execute("""
                        SELECT COUNT(*) FROM timescaledb_information.hypertables 
                        WHERE hypertable_name = 'itm_bucket_summaries';
                    """)
                    if cur.fetchone()[0] == 0:
                        cur.execute("""
                            SELECT create_hypertable('itm_bucket_summaries', 'timestamp', 
                                chunk_time_interval => INTERVAL '1 day',
                                if_not_exists => TRUE);
                        """)
                        logger.info("Created hypertable for itm_bucket_summaries")
                    
                    # Create indexes for ITM queries
                    cur.execute("""
                        CREATE INDEX IF NOT EXISTS idx_itm_bucket_symbol_expiry 
                        ON itm_bucket_summaries (symbol, expiry_date, itm_count, timestamp DESC);
                    """)
                    
                    cur.execute("""
                        CREATE INDEX IF NOT EXISTS idx_itm_bucket_latest 
                        ON itm_bucket_summaries (symbol, expiry_date, itm_count, timestamp DESC);
                    """)
                    
                    # Create gamma_exposure_history table for leading indicators
                    cur.execute("""
                        CREATE TABLE IF NOT EXISTS gamma_exposure_history (
                            timestamp TIMESTAMPTZ NOT NULL,
                            symbol VARCHAR(50) NOT NULL,
                            expiry_date DATE NOT NULL,
                            
                            -- Current GEX snapshot
                            atm_strike NUMERIC(10, 2),
                            net_gex NUMERIC(18, 2),
                            total_positive_gex NUMERIC(18, 2),
                            total_negative_gex NUMERIC(18, 2),
                            zero_gamma_level NUMERIC(10, 2),
                            
                            -- IV Metrics (LEADING)
                            atm_iv NUMERIC(8, 4),
                            iv_trend NUMERIC(8, 4),
                            iv_velocity NUMERIC(8, 4),
                            iv_percentile NUMERIC(8, 4),
                            implied_move NUMERIC(10, 4),
                            
                            -- OI Metrics (LEADING)
                            atm_oi BIGINT,
                            oi_acceleration NUMERIC(15, 2),
                            oi_velocity NUMERIC(15, 2),
                            total_oi_change_rate NUMERIC(8, 4),
                            
                            -- Gamma Metrics (LEADING) - Increased precision for large values
                            atm_gamma NUMERIC(20, 8),
                            gamma_concentration NUMERIC(20, 8),
                            gamma_gradient NUMERIC(20, 8),
                            
                            -- Delta Metrics (LEADING)
                            delta_skew NUMERIC(8, 4),
                            delta_ladder_imbalance NUMERIC(8, 4),
                            
                            -- Volatility Regime (LEADING)
                            volatility_regime VARCHAR(20),
                            regime_transition_score NUMERIC(8, 4),
                            
                            -- Blast Probability (LEADING)
                            gamma_blast_probability NUMERIC(8, 4),
                            time_to_blast_minutes INTEGER,
                            predicted_direction VARCHAR(20),
                            confidence_level VARCHAR(20),
                            
                            PRIMARY KEY (timestamp, symbol, expiry_date)
                        );
                    """)
                    
                    # Convert to hypertable if not already
                    cur.execute("""
                        SELECT COUNT(*) FROM timescaledb_information.hypertables 
                        WHERE hypertable_name = 'gamma_exposure_history';
                    """)
                    if cur.fetchone()[0] == 0:
                        cur.execute("""
                            SELECT create_hypertable('gamma_exposure_history', 'timestamp', 
                                chunk_time_interval => INTERVAL '1 day',
                                if_not_exists => TRUE);
                        """)
                        logger.info("Created hypertable for gamma_exposure_history")
                    
                    # Create indexes for gamma exposure queries
                    cur.execute("""
                        CREATE INDEX IF NOT EXISTS idx_gamma_exposure_symbol_expiry 
                        ON gamma_exposure_history (symbol, expiry_date, timestamp DESC);
                    """)
                    
                    cur.execute("""
                        CREATE INDEX IF NOT EXISTS idx_gamma_exposure_blast_prob 
                        ON gamma_exposure_history (gamma_blast_probability DESC, timestamp DESC);
                    """)
                    
                    logger.info("Database schema initialized successfully")
        except ConnectionError:
            logger.warning("Database not available - schema creation skipped")
        except Exception as e:
            logger.error(f"Error creating schema: {e}")
    
    def insert_option_chain_data(self, symbol: str, instrument_key: str, 
                                 expiry_date: str, spot_price: float, 
                                 option_chain_data: List[Dict]) -> bool:
        """
        Insert option chain data into TimescaleDB
        
        Args:
            symbol: Symbol name (e.g., 'NIFTY')
            instrument_key: Instrument key (e.g., 'NSE_INDEX|Nifty 50')
            expiry_date: Expiry date in YYYY-MM-DD format
            spot_price: Current spot price
            option_chain_data: List of strike data dictionaries from API
            
        Returns:
            True if successful, False otherwise
        """
        try:
            timestamp = datetime.now(IST)
            records = []
            
            for strike_data in option_chain_data:
                if 'call_options' not in strike_data or 'put_options' not in strike_data:
                    continue
                
                strike_price = strike_data.get('strike_price', 0)
                if strike_price <= 0:
                    continue
                
                # Process Call Option (CE)
                call_data = strike_data.get('call_options', {})
                call_market = call_data.get('market_data', {})
                call_greeks = call_data.get('option_greeks', {})
                
                records.append({
                    'timestamp': timestamp,
                    'symbol': symbol,
                    'instrument_key': instrument_key,
                    'expiry_date': expiry_date,
                    'strike_price': strike_price,
                    'option_type': 'CE',
                    'ltp': call_market.get('ltp') or 0,
                    'volume': call_market.get('volume') or 0,
                    'oi': call_market.get('oi') or 0,
                    'prev_oi': call_market.get('prev_oi') or 0,
                    'chg_oi': (call_market.get('oi') or 0) - (call_market.get('prev_oi') or 0),
                    'close_price': call_market.get('close_price') or 0,
                    'change': (call_market.get('ltp') or 0) - (call_market.get('close_price') or 0),
                    'iv': call_greeks.get('iv') or 0,
                    'delta': call_greeks.get('delta') or 0,
                    'gamma': call_greeks.get('gamma') or 0,
                    'theta': call_greeks.get('theta') or 0,
                    'vega': call_greeks.get('vega') or 0,
                    'spot_price': spot_price
                })
                
                # Process Put Option (PE)
                put_data = strike_data.get('put_options', {})
                put_market = put_data.get('market_data', {})
                put_greeks = put_data.get('option_greeks', {})
                
                records.append({
                    'timestamp': timestamp,
                    'symbol': symbol,
                    'instrument_key': instrument_key,
                    'expiry_date': expiry_date,
                    'strike_price': strike_price,
                    'option_type': 'PE',
                    'ltp': put_market.get('ltp') or 0,
                    'volume': put_market.get('volume') or 0,
                    'oi': put_market.get('oi') or 0,
                    'prev_oi': put_market.get('prev_oi') or 0,
                    'chg_oi': (put_market.get('oi') or 0) - (put_market.get('prev_oi') or 0),
                    'close_price': put_market.get('close_price') or 0,
                    'change': (put_market.get('ltp') or 0) - (put_market.get('close_price') or 0),
                    'iv': put_greeks.get('iv') or 0,
                    'delta': put_greeks.get('delta') or 0,
                    'gamma': put_greeks.get('gamma') or 0,
                    'theta': put_greeks.get('theta') or 0,
                    'vega': put_greeks.get('vega') or 0,
                    'spot_price': spot_price
                })
            
            if not records:
                logger.warning(f"No valid records to insert for {symbol}")
                return False
            
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    # Use execute_values for bulk insert
                    insert_query = """
                        INSERT INTO option_chain_data (
                            timestamp, symbol, instrument_key, expiry_date, strike_price, option_type,
                            ltp, volume, oi, prev_oi, chg_oi, close_price, change,
                            iv, delta, gamma, theta, vega, spot_price
                        ) VALUES %s
                        ON CONFLICT (timestamp, symbol, expiry_date, strike_price, option_type) 
                        DO UPDATE SET
                            ltp = EXCLUDED.ltp,
                            volume = EXCLUDED.volume,
                            oi = EXCLUDED.oi,
                            prev_oi = EXCLUDED.prev_oi,
                            chg_oi = EXCLUDED.chg_oi,
                            close_price = EXCLUDED.close_price,
                            change = EXCLUDED.change,
                            iv = EXCLUDED.iv,
                            delta = EXCLUDED.delta,
                            gamma = EXCLUDED.gamma,
                            theta = EXCLUDED.theta,
                            vega = EXCLUDED.vega,
                            spot_price = EXCLUDED.spot_price;
                    """
                    
                    values = [
                        (
                            r['timestamp'], r['symbol'], r['instrument_key'], r['expiry_date'],
                            r['strike_price'], r['option_type'], r['ltp'], r['volume'],
                            r['oi'], r['prev_oi'], r['chg_oi'], r['close_price'], r['change'],
                            r['iv'], r['delta'], r['gamma'], r['theta'], r['vega'], r['spot_price']
                        )
                        for r in records
                    ]
                    
                    execute_values(cur, insert_query, values)
                    logger.info(f"Inserted {len(records)} records for {symbol} at {timestamp}")
                    return True
                    
        except Exception as e:
            logger.error(f"Failed to insert option chain data for {symbol}: {e}")
            return False
    
    def get_latest_option_chain(self, symbol: str, expiry_date: str) -> Optional[List[Dict]]:
        """
        Get the latest option chain data for a symbol and expiry
        
        Args:
            symbol: Symbol name
            expiry_date: Expiry date in YYYY-MM-DD format
            
        Returns:
            List of strike data dictionaries in the same format as API response
        """
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    # Get the latest timestamp for this symbol and expiry
                    cur.execute("""
                        SELECT MAX(timestamp) 
                        FROM option_chain_data 
                        WHERE symbol = %s AND expiry_date = %s
                    """, (symbol, expiry_date))
                    
                    result = cur.fetchone()
                    if not result or not result[0]:
                        return None
                    
                    latest_timestamp = result[0]
                    
                    # Get all strike data for this timestamp
                    cur.execute("""
                        SELECT 
                            strike_price, option_type,
                            ltp, volume, oi, prev_oi, chg_oi, close_price, change,
                            iv, delta, gamma, theta, vega, spot_price
                        FROM option_chain_data
                        WHERE symbol = %s AND expiry_date = %s AND timestamp = %s
                        ORDER BY strike_price, option_type
                    """, (symbol, expiry_date, latest_timestamp))
                    
                    rows = cur.fetchall()
                    if not rows:
                        return None
                    
                    # Reconstruct the API response format
                    strikes = {}
                    spot_price = None
                    
                    for row in rows:
                        strike_price, option_type, ltp, volume, oi, prev_oi, chg_oi, \
                        close_price, change, iv, delta, gamma, theta, vega, spot = row
                        
                        if spot_price is None:
                            spot_price = float(spot)
                        
                        if strike_price not in strikes:
                            strikes[strike_price] = {
                                'strike_price': float(strike_price),
                                'call_options': {},
                                'put_options': {}
                            }
                        
                        option_data = {
                            'market_data': {
                                'ltp': float(ltp),
                                'volume': int(volume),
                                'oi': int(oi),
                                'prev_oi': int(prev_oi),
                                'close_price': float(close_price)
                            },
                            'option_greeks': {
                                'iv': float(iv),
                                'delta': float(delta),
                                'gamma': float(gamma),
                                'theta': float(theta),
                                'vega': float(vega)
                            }
                        }
                        
                        if option_type == 'CE':
                            strikes[strike_price]['call_options'] = option_data
                        else:
                            strikes[strike_price]['put_options'] = option_data
                    
                    # Convert to list format
                    result = list(strikes.values())
                    return result
                    
        except Exception as e:
            logger.error(f"Failed to get latest option chain for {symbol}: {e}")
            return None
    
    def get_available_symbols(self) -> List[Dict]:
        """Get list of available symbols with their configurations"""
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT symbol, instrument_key, is_active, refresh_interval_seconds
                        FROM symbol_config
                        WHERE is_active = TRUE
                        ORDER BY symbol
                    """)
                    
                    return [
                        {
                            'symbol': row[0],
                            'instrument_key': row[1],
                            'is_active': row[2],
                            'refresh_interval': row[3]
                        }
                        for row in cur.fetchall()
                    ]
        except Exception as e:
            logger.error(f"Failed to get available symbols: {e}")
            return []
    
    def update_symbol_config(self, symbol: str, instrument_key: str, 
                            refresh_interval: int = 30) -> bool:
        """Update or insert symbol configuration"""
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO symbol_config (symbol, instrument_key, refresh_interval_seconds)
                        VALUES (%s, %s, %s)
                        ON CONFLICT (symbol) 
                        DO UPDATE SET
                            instrument_key = EXCLUDED.instrument_key,
                            refresh_interval_seconds = EXCLUDED.refresh_interval_seconds,
                            last_updated = NOW()
                    """, (symbol, instrument_key, refresh_interval))
                    return True
        except Exception as e:
            logger.error(f"Failed to update symbol config for {symbol}: {e}")
            return False
    
    def insert_itm_bucket_summary(self, symbol: str, expiry_date: str, timestamp,
                                  itm_count: int, spot_price: float, atm_strike: float,
                                  ce_oi: int, ce_volume: int, ce_chgoi: int, ce_iv: float, ce_delta: float,
                                  pe_oi: int, pe_volume: int, pe_chgoi: int, pe_iv: float, pe_delta: float) -> bool:
        """
        Insert pre-calculated ITM bucket summary
        
        Args:
            symbol: Symbol name
            expiry_date: Expiry date in YYYY-MM-DD format
            timestamp: Timestamp of calculation
            itm_count: Number of ITM strikes (1-5)
            spot_price: Spot price at time of calculation
            atm_strike: ATM strike price
            ce_oi/pe_oi: Call/Put OI for ITM strikes
            ce_volume/pe_volume: Call/Put volume for ITM strikes
            ce_chgoi/pe_chgoi: Call/Put change in OI
            ce_iv/pe_iv: Call/Put IV
            ce_delta/pe_delta: Call/Put delta
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Calculate PCR metrics
            pcr_oi = pe_oi / ce_oi if ce_oi > 0 else 0
            pcr_volume = pe_volume / ce_volume if ce_volume > 0 else 0
            pcr_chgoi = pe_chgoi / ce_chgoi if ce_chgoi != 0 else 0
            
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO itm_bucket_summaries (
                            timestamp, symbol, expiry_date, itm_count,
                            spot_price, atm_strike,
                            ce_oi, ce_volume, ce_chgoi, ce_iv, ce_delta,
                            pe_oi, pe_volume, pe_chgoi, pe_iv, pe_delta,
                            pcr_oi, pcr_volume, pcr_chgoi
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (timestamp, symbol, expiry_date, itm_count)
                        DO UPDATE SET
                            spot_price = EXCLUDED.spot_price,
                            atm_strike = EXCLUDED.atm_strike,
                            ce_oi = EXCLUDED.ce_oi,
                            ce_volume = EXCLUDED.ce_volume,
                            ce_chgoi = EXCLUDED.ce_chgoi,
                            ce_iv = EXCLUDED.ce_iv,
                            ce_delta = EXCLUDED.ce_delta,
                            pe_oi = EXCLUDED.pe_oi,
                            pe_volume = EXCLUDED.pe_volume,
                            pe_chgoi = EXCLUDED.pe_chgoi,
                            pe_iv = EXCLUDED.pe_iv,
                            pe_delta = EXCLUDED.pe_delta,
                            pcr_oi = EXCLUDED.pcr_oi,
                            pcr_volume = EXCLUDED.pcr_volume,
                            pcr_chgoi = EXCLUDED.pcr_chgoi
                    """, (timestamp, symbol, expiry_date, itm_count,
                          spot_price, atm_strike,
                          ce_oi, ce_volume, ce_chgoi, ce_iv, ce_delta,
                          pe_oi, pe_volume, pe_chgoi, pe_iv, pe_delta,
                          pcr_oi, pcr_volume, pcr_chgoi))
                    return True
        except Exception as e:
            logger.error(f"Failed to insert ITM bucket summary for {symbol}: {e}")
            return False
    
    def get_itm_bucket_summaries(self, symbol: str, expiry_date: str, itm_count: int, hours: int = 24) -> Optional[pd.DataFrame]:
        """
        Get pre-calculated ITM bucket summaries over time
        ONLY returns data during market hours (up to 3:30 PM IST each day)
        
        Args:
            symbol: Symbol name
            expiry_date: Expiry date in YYYY-MM-DD format
            itm_count: Number of ITM strikes (1-5)
            hours: Number of hours to look back (default 24)
            
        Returns:
            DataFrame with ITM bucket summary data over time (filtered to market hours only)
        """
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT 
                            timestamp, spot_price, atm_strike,
                            ce_oi, ce_volume, ce_chgoi, ce_iv, ce_delta,
                            pe_oi, pe_volume, pe_chgoi, pe_iv, pe_delta,
                            pcr_oi, pcr_volume, pcr_chgoi
                        FROM itm_bucket_summaries
                        WHERE symbol = %s 
                        AND expiry_date = %s
                        AND itm_count = %s
                        AND timestamp > NOW() - INTERVAL '%s hours'
                        AND EXTRACT(HOUR FROM timestamp AT TIME ZONE 'Asia/Kolkata') * 60 + 
                            EXTRACT(MINUTE FROM timestamp AT TIME ZONE 'Asia/Kolkata') <= 15 * 60 + 30
                        ORDER BY timestamp ASC
                    """, (symbol, expiry_date, itm_count, hours))
                    
                    rows = cur.fetchall()
                    
                    if not rows:
                        logger.warning(f"No ITM bucket data found for {symbol} {expiry_date} itm_count={itm_count}")
                        return None
                    
                    # Convert to DataFrame
                    df = pd.DataFrame(rows, columns=[
                        'timestamp', 'spot_price', 'atm_strike',
                        'ce_oi', 'ce_volume', 'ce_chgoi', 'ce_iv', 'ce_delta',
                        'pe_oi', 'pe_volume', 'pe_chgoi', 'pe_iv', 'pe_delta',
                        'pcr_oi', 'pcr_volume', 'pcr_chgoi'
                    ])
                    
                    # Ensure proper data types
                    df['timestamp'] = pd.to_datetime(df['timestamp'])
                    numeric_cols = ['spot_price', 'atm_strike', 'ce_oi', 'ce_volume', 'ce_chgoi', 
                                   'pe_oi', 'pe_volume', 'pe_chgoi', 'ce_iv', 'pe_iv', 'ce_delta', 
                                   'pe_delta', 'pcr_oi', 'pcr_volume', 'pcr_chgoi']
                    for col in numeric_cols:
                        df[col] = pd.to_numeric(df[col], errors='coerce')
                    
                    logger.info(f"Successfully fetched {len(df)} ITM bucket records for {symbol} {expiry_date} itm_count={itm_count}")
                    return df
                    
        except Exception as e:
            logger.error(f"Failed to get ITM bucket summaries: {e}")
            return None
    
    def insert_gamma_exposure_history(self, symbol: str, expiry_date: str, timestamp,
                                      atm_strike: float, net_gex: float, total_positive_gex: float,
                                      total_negative_gex: float, zero_gamma_level: float,
                                      atm_iv: float, iv_trend: float, iv_velocity: float,
                                      iv_percentile: float, implied_move: float,
                                      atm_oi: int, oi_acceleration: float, oi_velocity: float,
                                      total_oi_change_rate: float,
                                      atm_gamma: float, gamma_concentration: float, gamma_gradient: float,
                                      delta_skew: float, delta_ladder_imbalance: float,
                                      volatility_regime: str, regime_transition_score: float,
                                      gamma_blast_probability: float, time_to_blast_minutes: int,
                                      predicted_direction: str, confidence_level: str) -> bool:
        """
        Insert gamma exposure history with leading indicators
        Called every 5 minutes during market hours
        
        Returns:
            True if successful, False otherwise
        """
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO gamma_exposure_history (
                            timestamp, symbol, expiry_date, atm_strike, net_gex,
                            total_positive_gex, total_negative_gex, zero_gamma_level,
                            atm_iv, iv_trend, iv_velocity, iv_percentile, implied_move,
                            atm_oi, oi_acceleration, oi_velocity, total_oi_change_rate,
                            atm_gamma, gamma_concentration, gamma_gradient,
                            delta_skew, delta_ladder_imbalance,
                            volatility_regime, regime_transition_score,
                            gamma_blast_probability, time_to_blast_minutes,
                            predicted_direction, confidence_level
                        ) VALUES (
                            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                        )
                        ON CONFLICT (timestamp, symbol, expiry_date) DO UPDATE SET
                            atm_strike = EXCLUDED.atm_strike,
                            net_gex = EXCLUDED.net_gex,
                            total_positive_gex = EXCLUDED.total_positive_gex,
                            total_negative_gex = EXCLUDED.total_negative_gex,
                            zero_gamma_level = EXCLUDED.zero_gamma_level,
                            atm_iv = EXCLUDED.atm_iv,
                            iv_trend = EXCLUDED.iv_trend,
                            iv_velocity = EXCLUDED.iv_velocity,
                            iv_percentile = EXCLUDED.iv_percentile,
                            implied_move = EXCLUDED.implied_move,
                            atm_oi = EXCLUDED.atm_oi,
                            oi_acceleration = EXCLUDED.oi_acceleration,
                            oi_velocity = EXCLUDED.oi_velocity,
                            total_oi_change_rate = EXCLUDED.total_oi_change_rate,
                            atm_gamma = EXCLUDED.atm_gamma,
                            gamma_concentration = EXCLUDED.gamma_concentration,
                            gamma_gradient = EXCLUDED.gamma_gradient,
                            delta_skew = EXCLUDED.delta_skew,
                            delta_ladder_imbalance = EXCLUDED.delta_ladder_imbalance,
                            volatility_regime = EXCLUDED.volatility_regime,
                            regime_transition_score = EXCLUDED.regime_transition_score,
                            gamma_blast_probability = EXCLUDED.gamma_blast_probability,
                            time_to_blast_minutes = EXCLUDED.time_to_blast_minutes,
                            predicted_direction = EXCLUDED.predicted_direction,
                            confidence_level = EXCLUDED.confidence_level
                    """, (
                        timestamp, symbol, expiry_date, atm_strike, net_gex,
                        total_positive_gex, total_negative_gex, zero_gamma_level,
                        atm_iv, iv_trend, iv_velocity, iv_percentile, implied_move,
                        atm_oi, oi_acceleration, oi_velocity, total_oi_change_rate,
                        atm_gamma, gamma_concentration, gamma_gradient,
                        delta_skew, delta_ladder_imbalance,
                        volatility_regime, regime_transition_score,
                        gamma_blast_probability, time_to_blast_minutes,
                        predicted_direction, confidence_level
                    ))
                    conn.commit()
                    return True
        except Exception as e:
            logger.error(f"Failed to insert gamma exposure history for {symbol}: {e}")
            return False
    
    def get_gamma_exposure_history(self, symbol: str, expiry_date: str, hours: int = 24) -> Optional[pd.DataFrame]:
        """
        Retrieve gamma exposure history for trend analysis
        
        Args:
            symbol: Symbol name
            expiry_date: Expiry date in YYYY-MM-DD format
            hours: Number of hours of historical data to retrieve
            
        Returns:
            DataFrame with gamma exposure history or None if not found
        """
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT timestamp, atm_strike, net_gex, total_positive_gex, total_negative_gex,
                               zero_gamma_level, atm_iv, iv_trend, iv_velocity, iv_percentile,
                               implied_move, atm_oi, oi_acceleration, oi_velocity, total_oi_change_rate,
                               atm_gamma, gamma_concentration, gamma_gradient, delta_skew, 
                               delta_ladder_imbalance, volatility_regime, regime_transition_score,
                               gamma_blast_probability, time_to_blast_minutes, predicted_direction,
                               confidence_level
                        FROM gamma_exposure_history
                        WHERE symbol = %s 
                        AND expiry_date = %s
                        AND timestamp > NOW() - INTERVAL '%s hours'
                        ORDER BY timestamp ASC
                    """, (symbol, expiry_date, hours))
                    
                    rows = cur.fetchall()
                    
                    if not rows:
                        logger.debug(f"No gamma exposure history found for {symbol} {expiry_date}")
                        return None
                    
                    # Convert to DataFrame
                    columns = [
                        'timestamp', 'atm_strike', 'net_gex', 'total_positive_gex', 'total_negative_gex',
                        'zero_gamma_level', 'atm_iv', 'iv_trend', 'iv_velocity', 'iv_percentile',
                        'implied_move', 'atm_oi', 'oi_acceleration', 'oi_velocity', 'total_oi_change_rate',
                        'atm_gamma', 'gamma_concentration', 'gamma_gradient', 'delta_skew',
                        'delta_ladder_imbalance', 'volatility_regime', 'regime_transition_score',
                        'gamma_blast_probability', 'time_to_blast_minutes', 'predicted_direction',
                        'confidence_level'
                    ]
                    df = pd.DataFrame(rows, columns=columns)
                    
                    # Ensure proper data types
                    df['timestamp'] = pd.to_datetime(df['timestamp'])
                    numeric_cols = [col for col in df.columns if col != 'timestamp']
                    for col in numeric_cols:
                        if col not in ['volatility_regime', 'predicted_direction', 'confidence_level']:
                            df[col] = pd.to_numeric(df[col], errors='coerce')
                    
                    logger.info(f"Successfully fetched {len(df)} gamma exposure records for {symbol} {expiry_date}")
                    return df
                    
        except Exception as e:
            logger.error(f"Failed to get gamma exposure history: {e}")
            return None
    
    def insert_sentiment_score(self, symbol: str, expiry_date: str, sentiment_score: float,
                              sentiment: str, confidence: str, spot_price: float,
                              pcr_oi: float = None, pcr_chgoi: float = None, 
                              pcr_volume: float = None) -> bool:
        """
        Insert sentiment score for a symbol and expiry
        
        Args:
            symbol: Symbol name
            expiry_date: Expiry date in YYYY-MM-DD format
            sentiment_score: Calculated sentiment score
            sentiment: Sentiment category (e.g., "STRONG BULLISH")
            confidence: Confidence level (e.g., "HIGH")
            spot_price: Spot price at time of calculation
            pcr_oi: PCR OI value
            pcr_chgoi: PCR ChgOI value
            pcr_volume: PCR Volume value
            
        Returns:
            True if successful, False otherwise
        """
        try:
            timestamp = datetime.now(IST)
            
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO sentiment_scores (
                            timestamp, symbol, expiry_date, sentiment_score,
                            sentiment, confidence, spot_price, pcr_oi, pcr_chgoi, pcr_volume
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (timestamp, symbol, expiry_date) 
                        DO UPDATE SET
                            sentiment_score = EXCLUDED.sentiment_score,
                            sentiment = EXCLUDED.sentiment,
                            confidence = EXCLUDED.confidence,
                            spot_price = EXCLUDED.spot_price,
                            pcr_oi = EXCLUDED.pcr_oi,
                            pcr_chgoi = EXCLUDED.pcr_chgoi,
                            pcr_volume = EXCLUDED.pcr_volume;
                    """, (timestamp, symbol, expiry_date, sentiment_score, sentiment,
                          confidence, spot_price, pcr_oi, pcr_chgoi, pcr_volume))
                    return True
        except Exception as e:
            logger.error(f"Failed to insert sentiment score for {symbol}: {e}")
            return False
    
    def get_extreme_sentiment_symbols(self, min_score: float = 20, max_score: float = -20) -> List[Dict]:
        """
        Get symbols with extreme sentiment scores for CURRENT (earliest) expiry only
        This ensures consistency with Option Chain Analysis which uses current expiry
        
        Args:
            min_score: Minimum sentiment score (default 20 for bullish)
            max_score: Maximum sentiment score (default -20 for bearish)
            
        Returns:
            List of dictionaries with symbol, sentiment score, and details
        """
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    # Get sentiment for CURRENT (earliest) expiry only for each symbol
                    cur.execute("""
                        SELECT DISTINCT ON (symbol)
                            symbol, expiry_date, sentiment_score, sentiment, confidence,
                            spot_price, pcr_oi, pcr_chgoi, pcr_volume, timestamp
                        FROM sentiment_scores
                        WHERE sentiment_score > %s OR sentiment_score < %s
                        ORDER BY symbol, expiry_date ASC, timestamp DESC
                    """, (min_score, max_score))
                    
                    rows = cur.fetchall()
                    
                    results = []
                    for row in rows:
                        symbol, expiry, score, sentiment, confidence, spot, pcr_oi, pcr_chgoi, pcr_vol, ts = row
                        results.append({
                            'symbol': symbol,
                            'expiry_date': expiry.strftime('%Y-%m-%d') if hasattr(expiry, 'strftime') else str(expiry),
                            'sentiment_score': float(score),
                            'sentiment': sentiment,
                            'confidence': confidence,
                            'spot_price': float(spot),
                            'pcr_oi': float(pcr_oi) if pcr_oi else 0,
                            'pcr_chgoi': float(pcr_chgoi) if pcr_chgoi else 0,
                            'pcr_volume': float(pcr_vol) if pcr_vol else 0,
                            'timestamp': ts
                        })
                    
                    # Sort by absolute sentiment score (highest first)
                    results.sort(key=lambda x: abs(x['sentiment_score']), reverse=True)
                    return results
                    
        except Exception as e:
            logger.error(f"Failed to get extreme sentiment symbols: {e}")
            return []
    
    def get_latest_timestamp(self, symbol: str, expiry_date: str) -> Optional[datetime]:
        """Get the latest data timestamp for a symbol and expiry"""
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT MAX(timestamp) 
                        FROM option_chain_data 
                        WHERE symbol = %s AND expiry_date = %s
                    """, (symbol, expiry_date))
                    
                    result = cur.fetchone()
                    return result[0] if result and result[0] else None
        except Exception as e:
            logger.error(f"Failed to get latest timestamp: {e}")
            return None
    
    def get_all_symbols_with_latest_data(self) -> List[Dict]:
        """
        Get all symbols with their CURRENT (earliest) expiry and latest data timestamp
        This ensures we get the same expiry as Option Chain Analysis uses
        
        Returns:
            List of dictionaries with symbol, expiry_date, and latest_timestamp
        """
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    # Get the earliest (current) expiry for each symbol, then latest timestamp for that expiry
                    cur.execute("""
                        WITH earliest_expiry AS (
                            SELECT symbol, MIN(expiry_date) as expiry_date
                            FROM option_chain_data
                            GROUP BY symbol
                        )
                        SELECT 
                            e.symbol,
                            e.expiry_date,
                            MAX(oc.timestamp) as latest_timestamp
                        FROM earliest_expiry e
                        JOIN option_chain_data oc ON e.symbol = oc.symbol AND e.expiry_date = oc.expiry_date
                        GROUP BY e.symbol, e.expiry_date
                        ORDER BY e.symbol
                    """)
                    
                    rows = cur.fetchall()
                    symbol_data = {}
                    
                    for row in rows:
                        symbol, expiry_date, timestamp = row
                        if symbol not in symbol_data:
                            # Get the actual data for this symbol/expiry (current expiry)
                            data = self.get_latest_option_chain(symbol, expiry_date.strftime('%Y-%m-%d'))
                            if data:  # Only add if we have data
                                symbol_data[symbol] = {
                                    'symbol': symbol,
                                    'expiry_date': expiry_date.strftime('%Y-%m-%d'),
                                    'latest_timestamp': timestamp,
                                    'data': data
                                }
                    
                    return list(symbol_data.values())
        except Exception as e:
            logger.error(f"Failed to get all symbols with latest data: {e}")
            return []
    
    def get_itm_data_over_time(self, symbol: str, expiry_date: str, hours: int = 24) -> Optional[pd.DataFrame]:
        """
        Get ITM Call and Put OI, Volume, and Change in OI data over time
        
        Args:
            symbol: Symbol name (e.g., 'NIFTY')
            expiry_date: Expiry date in YYYY-MM-DD format
            hours: Number of hours to look back (default 24)
            
        Returns:
            DataFrame with columns: timestamp, ce_oi, pe_oi, ce_volume, pe_volume, ce_chgoi, pe_chgoi, spot_price
        """
        try:
            
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    # Get data from the last N hours with proper ordering
                    cur.execute("""
                        SELECT 
                            timestamp,
                            strike_price,
                            option_type,
                            oi,
                            volume,
                            chg_oi,
                            spot_price
                        FROM option_chain_data
                        WHERE symbol = %s 
                        AND expiry_date = %s
                        AND timestamp > NOW() - INTERVAL '%s hours'
                        ORDER BY timestamp DESC, strike_price, option_type
                    """, (symbol, expiry_date, hours))
                    
                    rows = cur.fetchall()
                    
                    if not rows:
                        logger.warning(f"No ITM data found for {symbol} {expiry_date} in last {hours} hours")
                        return None
                    
                    # Convert to DataFrame
                    df = pd.DataFrame(
                        rows,
                        columns=['timestamp', 'strike_price', 'option_type', 'oi', 'volume', 'chg_oi', 'spot_price']
                    )
                    
                    # Ensure proper data types
                    df['timestamp'] = pd.to_datetime(df['timestamp'])
                    df['strike_price'] = pd.to_numeric(df['strike_price'], errors='coerce')
                    df['oi'] = pd.to_numeric(df['oi'], errors='coerce').fillna(0).astype(int)
                    df['volume'] = pd.to_numeric(df['volume'], errors='coerce').fillna(0).astype(int)
                    df['chg_oi'] = pd.to_numeric(df['chg_oi'], errors='coerce').fillna(0).astype(int)
                    df['spot_price'] = pd.to_numeric(df['spot_price'], errors='coerce')
                    
                    # Remove any invalid rows
                    df = df.dropna(subset=['spot_price', 'strike_price'])
                    
                    if df.empty:
                        logger.warning(f"No valid ITM data after cleaning for {symbol} {expiry_date}")
                        return None
                    
                    # Get unique timestamps (sorted chronologically)
                    timestamps = sorted(df['timestamp'].unique())
                    
                    # For each timestamp, calculate ITM aggregates
                    itm_data_list = []
                    
                    for ts in timestamps:
                        ts_data = df[df['timestamp'] == ts].copy()
                        
                        if ts_data.empty:
                            continue
                            
                        spot = ts_data['spot_price'].iloc[0]
                        
                        # Get unique strikes for this timestamp
                        strikes = sorted(ts_data['strike_price'].unique())
                        
                        if len(strikes) < 2:
                            continue  # Need at least 2 strikes to determine ATM
                        
                        # Find ATM strike (closest to spot)
                        atm_strike = min(strikes, key=lambda x: abs(x - spot))
                        
                        # ITM Calls: below ATM (lower strikes)
                        itm_calls = ts_data[
                            (ts_data['option_type'] == 'CE') & 
                            (ts_data['strike_price'] < atm_strike)
                        ]
                        
                        # ITM Puts: above ATM (higher strikes)
                        itm_puts = ts_data[
                            (ts_data['option_type'] == 'PE') & 
                            (ts_data['strike_price'] > atm_strike)
                        ]
                        
                        # Aggregate values
                        ce_oi = int(itm_calls['oi'].sum()) if not itm_calls.empty else 0
                        pe_oi = int(itm_puts['oi'].sum()) if not itm_puts.empty else 0
                        ce_vol = int(itm_calls['volume'].sum()) if not itm_calls.empty else 0
                        pe_vol = int(itm_puts['volume'].sum()) if not itm_puts.empty else 0
                        ce_chgoi = int(itm_calls['chg_oi'].sum()) if not itm_calls.empty else 0
                        pe_chgoi = int(itm_puts['chg_oi'].sum()) if not itm_puts.empty else 0
                        
                        itm_data_list.append({
                            'timestamp': ts,
                            'spot_price': spot,
                            'ce_oi': ce_oi,
                            'pe_oi': pe_oi,
                            'ce_volume': ce_vol,
                            'pe_volume': pe_vol,
                            'ce_chgoi': ce_chgoi,
                            'pe_chgoi': pe_chgoi,
                            'atm_strike': atm_strike
                        })
                    
                    if not itm_data_list:
                        logger.warning(f"No ITM aggregates generated for {symbol} {expiry_date}")
                        return None
                    
                    result_df = pd.DataFrame(itm_data_list)
                    logger.info(f"Successfully fetched {len(result_df)} ITM records for {symbol} {expiry_date}")
                    return result_df
                    
        except Exception as e:
            logger.error(f"Failed to get ITM data over time for {symbol}: {e}", exc_info=True)
            return None
    
    def check_available_data(self, symbol: str, expiry_date: str) -> Dict:
        """
        Check if data is available in database for a symbol and expiry
        
        Args:
            symbol: Symbol name
            expiry_date: Expiry date in YYYY-MM-DD format
            
        Returns:
            Dictionary with data availability info
        """
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    # Get data count and date range
                    cur.execute("""
                        SELECT 
                            COUNT(*) as total_records,
                            MIN(timestamp) as earliest_timestamp,
                            MAX(timestamp) as latest_timestamp,
                            COUNT(DISTINCT timestamp) as unique_timestamps,
                            COUNT(DISTINCT strike_price) as unique_strikes,
                            COUNT(DISTINCT DATE(timestamp)) as unique_dates
                        FROM option_chain_data
                        WHERE symbol = %s AND expiry_date = %s
                    """, (symbol, expiry_date))
                    
                    result = cur.fetchone()
                    if result and result[0] > 0:
                        return {
                            'available': True,
                            'total_records': result[0],
                            'earliest_timestamp': result[1],
                            'latest_timestamp': result[2],
                            'unique_timestamps': result[3],
                            'unique_strikes': result[4],
                            'unique_dates': result[5]
                        }
                    else:
                        return {'available': False, 'total_records': 0}
        except Exception as e:
            logger.error(f"Failed to check data availability: {e}")
            return {'available': False, 'error': str(e)}
    
    def close(self):
        """Close all connections in the pool"""
        if self.pool:
            self.pool.closeall()
            logger.info("Database connection pool closed")

