"""
Script to calculate and store sentiment scores for existing option chain data in the database
This is useful when sentiment calculation was added after data was already collected
"""

import os
import sys
import logging
from datetime import datetime
import pytz
import pandas as pd

# Add current directory to path
sys.path.insert(0, os.path.dirname(__file__))

from database import TimescaleDBManager
from optionchain import (
    process_option_chain_data,
    calculate_bucket_summaries,
    calculate_comprehensive_pcr,
    calculate_comprehensive_sentiment_score
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

IST = pytz.timezone('Asia/Kolkata')


def calculate_sentiment_for_existing_data():
    """Calculate sentiment scores for all existing option chain data"""
    try:
        # Initialize database
        db_manager = TimescaleDBManager()
        
        if not db_manager or not db_manager.pool:
            logger.error("Database connection failed")
            return
        
        logger.info("Connected to database")
        
        # Get all unique symbols and expiries with data
        with db_manager.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT DISTINCT symbol, expiry_date, MAX(timestamp) as latest_ts
                    FROM option_chain_data
                    GROUP BY symbol, expiry_date
                    ORDER BY symbol, latest_ts DESC
                """)
                symbols_expiries = cur.fetchall()
        
        logger.info(f"Found {len(symbols_expiries)} symbol/expiry combinations with data")
        
        success_count = 0
        error_count = 0
        
        for symbol, expiry_date, latest_ts in symbols_expiries:
            try:
                logger.info(f"Processing {symbol} ({expiry_date})...")
                
                # Get latest option chain data
                data = db_manager.get_latest_option_chain(symbol, expiry_date.strftime('%Y-%m-%d'))
                
                if not data:
                    logger.warning(f"No data found for {symbol} ({expiry_date})")
                    continue
                
                # Get spot price from database
                spot_price = 0
                with db_manager.get_connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute("""
                            SELECT spot_price 
                            FROM option_chain_data 
                            WHERE symbol = %s AND expiry_date = %s 
                            AND spot_price > 0
                            ORDER BY timestamp DESC 
                            LIMIT 1
                        """, (symbol, expiry_date))
                        result = cur.fetchone()
                        if result and result[0] and result[0] > 0:
                            spot_price = float(result[0])
                
                if spot_price == 0:
                    logger.warning(f"Could not determine spot price for {symbol}")
                    continue
                
                # Process option chain data
                processed_data = process_option_chain_data(data, spot_price)
                
                if not processed_data:
                    logger.warning(f"Failed to process data for {symbol}")
                    continue
                
                table = pd.DataFrame(processed_data)
                table = table.dropna(subset=['Strike'])
                table = table[table['Strike'] > 0]
                table = table.sort_values('Strike').reset_index(drop=True)
                table = table.drop_duplicates(subset=["Strike"], keep='first')
                
                if len(table) == 0:
                    logger.warning(f"No valid strikes for {symbol}")
                    continue
                
                # Calculate sentiment
                atm_strike = table.loc[table["Strike"].sub(spot_price).abs().idxmin(), "Strike"]
                bucket_summary = calculate_bucket_summaries(table, atm_strike, spot_price)
                pcr_data = calculate_comprehensive_pcr(bucket_summary)
                sentiment_analysis = calculate_comprehensive_sentiment_score(
                    table, bucket_summary, pcr_data, spot_price
                )
                
                # Store sentiment score
                success = db_manager.insert_sentiment_score(
                    symbol=symbol,
                    expiry_date=expiry_date.strftime('%Y-%m-%d'),
                    sentiment_score=sentiment_analysis['final_score'],
                    sentiment=sentiment_analysis['sentiment'],
                    confidence=sentiment_analysis['confidence'],
                    spot_price=spot_price,
                    pcr_oi=pcr_data.get('OVERALL_PCR_OI'),
                    pcr_chgoi=pcr_data.get('OVERALL_PCR_CHGOI'),
                    pcr_volume=pcr_data.get('OVERALL_PCR_VOLUME')
                )
                
                if success:
                    success_count += 1
                    logger.info(f"✓ {symbol}: Sentiment = {sentiment_analysis['final_score']:.2f} ({sentiment_analysis['sentiment']})")
                else:
                    error_count += 1
                    logger.error(f"✗ Failed to store sentiment for {symbol}")
                    
            except Exception as e:
                error_count += 1
                logger.error(f"Error processing {symbol} ({expiry_date}): {e}")
        
        logger.info(f"\n{'='*60}")
        logger.info(f"Completed: {success_count} successful, {error_count} errors")
        logger.info(f"{'='*60}")
        
        db_manager.close()
        
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    calculate_sentiment_for_existing_data()

