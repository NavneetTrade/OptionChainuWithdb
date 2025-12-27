"""
Script to clear all data from the database
Use this to start fresh with new data collection
"""

import os
import sys
import logging
import psycopg2
from psycopg2.extras import RealDictCursor

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def clear_database():
    """Clear all data from the database"""
    try:
        # Get database connection parameters
        db_host = os.getenv('DB_HOST', 'localhost')
        db_port = os.getenv('DB_PORT', '5432')
        db_name = os.getenv('DB_NAME', 'optionchain')
        db_user = os.getenv('DB_USER', 'navneet')
        
        logger.info(f"Connecting to database: {db_name}@{db_host}:{db_port}")
        
        conn = psycopg2.connect(
            host=db_host,
            port=db_port,
            database=db_name,
            user=db_user
        )
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        logger.info("Connected to database")
        
        # Get counts before deletion
        cur.execute('SELECT COUNT(*) as count FROM option_chain_data')
        option_chain_count = cur.fetchone()['count']
        
        cur.execute('SELECT COUNT(*) as count FROM sentiment_scores')
        sentiment_count = cur.fetchone()['count']
        
        cur.execute('SELECT COUNT(*) as count FROM symbol_config')
        config_count = cur.fetchone()['count']
        
        print(f"\n{'='*60}")
        print("DATABASE CLEAR - Current Data")
        print(f"{'='*60}")
        print(f"Option Chain Records: {option_chain_count}")
        print(f"Sentiment Scores: {sentiment_count}")
        print(f"Symbol Configurations: {config_count}")
        print(f"{'='*60}\n")
        
        # Confirm deletion
        confirm = input("⚠️  Are you sure you want to delete ALL data? (yes/no): ")
        if confirm.lower() != 'yes':
            print("❌ Operation cancelled")
            conn.close()
            return
        
        logger.info("Starting database cleanup...")
        
        # Delete data (keep schema and config)
        cur.execute('TRUNCATE TABLE option_chain_data CASCADE')
        logger.info("✓ Cleared option_chain_data table")
        
        cur.execute('TRUNCATE TABLE sentiment_scores CASCADE')
        logger.info("✓ Cleared sentiment_scores table")
        
        # Clear symbol_config to force re-fetch of all F&O instruments
        cur.execute('TRUNCATE TABLE symbol_config CASCADE')
        logger.info("✓ Cleared symbol_config table (will re-fetch all F&O symbols)")
        
        conn.commit()
        
        print(f"\n{'='*60}")
        print("✅ DATABASE CLEARED SUCCESSFULLY")
        print(f"{'='*60}")
        print("All option chain data and sentiment scores have been deleted.")
        print("Symbol configurations are preserved.")
        print()
        print("📡 Next Steps:")
        print("  1. Start background service: python3 background_service.py --interval 60 &")
        print("  2. Service will fetch REAL data from Upstox API:")
        print("     - If market closed: Fetches once (last available data)")
        print("     - If market open: Fetches every 1 minute (real-time)")
        print()
        print("✅ All data comes from REAL Upstox API (not test/manual data)")
        print(f"{'='*60}\n")
        
        conn.close()
        
    except Exception as e:
        logger.error(f"Error clearing database: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    clear_database()

