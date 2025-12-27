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
    
    def close(self):
        """Close all connections in the pool"""
        if self.pool:
            self.pool.closeall()
            logger.info("Database connection pool closed")

