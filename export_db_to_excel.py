#!/usr/bin/env python3
"""
Export data from cloud PostgreSQL database to Excel files locally
"""

import psycopg2
import pandas as pd
from datetime import datetime, timedelta
import os

# Database connection details (cloud server)
DB_CONFIG = {
    'host': '92.4.74.245',
    'port': 5432,
    'database': 'optionchain',
    'user': 'postgres',
    'password': 'navneetshukla'  # Change if different
}

def export_gamma_exposure_history(output_dir='exports', days_back=7):
    """Export gamma exposure history to Excel"""
    print(f"📊 Exporting gamma exposure history (last {days_back} days)...")
    
    conn = psycopg2.connect(**DB_CONFIG)
    
    query = f"""
        SELECT 
            symbol,
            timestamp AT TIME ZONE 'Asia/Kolkata' as timestamp_ist,
            spot_price,
            net_gex,
            gamma_blast_probability,
            direction,
            confidence,
            time_to_blast_mins,
            ce_delta,
            pe_delta,
            ce_itm_chg_oi,
            pe_itm_chg_oi
        FROM gamma_exposure_history
        WHERE timestamp > NOW() - INTERVAL '{days_back} days'
        ORDER BY timestamp DESC, symbol
    """
    
    df = pd.read_sql_query(query, conn)
    conn.close()
    
    # Create output directory
    os.makedirs(output_dir, exist_ok=True)
    
    # Generate filename with timestamp
    filename = f"{output_dir}/gamma_exposure_history_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    
    # Export to Excel
    df.to_excel(filename, index=False, sheet_name='Gamma Exposure')
    
    print(f"✅ Exported {len(df)} records to: {filename}")
    print(f"   Symbols: {df['symbol'].nunique()}")
    print(f"   Date range: {df['timestamp_ist'].min()} to {df['timestamp_ist'].max()}")
    
    return filename


def export_option_chain_data(symbol='NIFTY', output_dir='exports', days_back=1):
    """Export option chain data for a specific symbol"""
    print(f"📊 Exporting option chain data for {symbol} (last {days_back} days)...")
    
    conn = psycopg2.connect(**DB_CONFIG)
    
    query = f"""
        SELECT 
            symbol,
            timestamp AT TIME ZONE 'Asia/Kolkata' as timestamp_ist,
            expiry_date,
            spot_price,
            strike_price,
            call_oi,
            call_volume,
            call_ltp,
            call_iv,
            put_oi,
            put_volume,
            put_ltp,
            put_iv,
            pcr_oi,
            pcr_volume
        FROM option_chain_data
        WHERE symbol = '{symbol}'
        AND timestamp > NOW() - INTERVAL '{days_back} days'
        ORDER BY timestamp DESC, strike_price
        LIMIT 50000
    """
    
    df = pd.read_sql_query(query, conn)
    conn.close()
    
    # Create output directory
    os.makedirs(output_dir, exist_ok=True)
    
    # Generate filename with timestamp
    filename = f"{output_dir}/option_chain_{symbol}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    
    # Export to Excel
    df.to_excel(filename, index=False, sheet_name=symbol)
    
    print(f"✅ Exported {len(df)} records to: {filename}")
    print(f"   Date range: {df['timestamp_ist'].min()} to {df['timestamp_ist'].max()}")
    
    return filename


def export_latest_gamma_blasts(output_dir='exports', min_probability=0.3):
    """Export latest gamma blast signals above threshold"""
    print(f"📊 Exporting latest gamma blasts (probability > {min_probability})...")
    
    conn = psycopg2.connect(**DB_CONFIG)
    
    query = f"""
        WITH latest_data AS (
            SELECT DISTINCT ON (symbol)
                symbol,
                timestamp AT TIME ZONE 'Asia/Kolkata' as timestamp_ist,
                spot_price,
                net_gex,
                gamma_blast_probability,
                direction,
                confidence,
                time_to_blast_mins,
                ce_delta,
                pe_delta,
                ce_itm_chg_oi,
                pe_itm_chg_oi
            FROM gamma_exposure_history
            WHERE timestamp > NOW() - INTERVAL '1 day'
            ORDER BY symbol, timestamp DESC
        )
        SELECT * FROM latest_data
        WHERE gamma_blast_probability > {min_probability}
        ORDER BY gamma_blast_probability DESC
    """
    
    df = pd.read_sql_query(query, conn)
    conn.close()
    
    # Create output directory
    os.makedirs(output_dir, exist_ok=True)
    
    # Generate filename with timestamp
    filename = f"{output_dir}/gamma_blasts_latest_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    
    # Export to Excel with formatting
    with pd.ExcelWriter(filename, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Gamma Blasts')
        
        # Auto-adjust column widths
        worksheet = writer.sheets['Gamma Blasts']
        for idx, col in enumerate(df.columns):
            max_length = max(df[col].astype(str).map(len).max(), len(col)) + 2
            worksheet.column_dimensions[chr(65 + idx)].width = min(max_length, 50)
    
    print(f"✅ Exported {len(df)} gamma blast signals to: {filename}")
    if len(df) > 0:
        print(f"   Top 5 symbols:")
        for idx, row in df.head(5).iterrows():
            print(f"   - {row['symbol']}: {row['gamma_blast_probability']:.2%} ({row['direction']}, {row['confidence']})")
    
    return filename


def export_all_symbols_summary(output_dir='exports'):
    """Export summary statistics for all symbols"""
    print(f"📊 Exporting summary for all symbols...")
    
    conn = psycopg2.connect(**DB_CONFIG)
    
    query = """
        WITH latest_data AS (
            SELECT DISTINCT ON (symbol)
                symbol,
                timestamp AT TIME ZONE 'Asia/Kolkata' as latest_update,
                spot_price,
                net_gex,
                gamma_blast_probability,
                direction,
                confidence
            FROM gamma_exposure_history
            WHERE timestamp > NOW() - INTERVAL '7 days'
            ORDER BY symbol, timestamp DESC
        ),
        stats AS (
            SELECT 
                symbol,
                COUNT(*) as total_records,
                MIN(timestamp AT TIME ZONE 'Asia/Kolkata') as first_record,
                MAX(timestamp AT TIME ZONE 'Asia/Kolkata') as last_record,
                AVG(gamma_blast_probability) as avg_probability,
                MAX(gamma_blast_probability) as max_probability
            FROM gamma_exposure_history
            WHERE timestamp > NOW() - INTERVAL '7 days'
            GROUP BY symbol
        )
        SELECT 
            l.symbol,
            l.latest_update,
            l.spot_price,
            l.net_gex,
            l.gamma_blast_probability as current_probability,
            l.direction,
            l.confidence,
            s.total_records,
            s.avg_probability,
            s.max_probability,
            s.first_record,
            s.last_record
        FROM latest_data l
        JOIN stats s ON l.symbol = s.symbol
        ORDER BY l.gamma_blast_probability DESC
    """
    
    df = pd.read_sql_query(query, conn)
    conn.close()
    
    # Create output directory
    os.makedirs(output_dir, exist_ok=True)
    
    # Generate filename with timestamp
    filename = f"{output_dir}/all_symbols_summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    
    # Export to Excel
    df.to_excel(filename, index=False, sheet_name='Summary')
    
    print(f"✅ Exported summary for {len(df)} symbols to: {filename}")
    
    return filename


def export_bucket_summary(symbol='NIFTY', output_dir='exports'):
    """Export bucket-wise strike analysis (like the UI shows)"""
    print(f"📊 Exporting bucket summary for {symbol}...")
    
    conn = psycopg2.connect(**DB_CONFIG)
    
    # Get latest option chain data with bucket calculations
    query = f"""
        WITH latest_timestamp AS (
            SELECT MAX(timestamp) as ts
            FROM option_chain_data
            WHERE symbol = '{symbol}'
            AND timestamp > NOW() - INTERVAL '1 day'
        ),
        latest_data AS (
            SELECT 
                strike_price,
                spot_price,
                call_oi,
                call_volume,
                call_ltp,
                call_iv,
                put_oi,
                put_volume,
                put_ltp,
                put_iv,
                pcr_oi,
                timestamp AT TIME ZONE 'Asia/Kolkata' as timestamp_ist
            FROM option_chain_data
            WHERE symbol = '{symbol}'
            AND timestamp = (SELECT ts FROM latest_timestamp)
        )
        SELECT 
            strike_price,
            spot_price,
            call_oi,
            call_volume,
            call_ltp,
            call_iv,
            put_oi,
            put_volume,
            put_ltp,
            put_iv,
            pcr_oi,
            call_oi - LAG(call_oi, 1, 0) OVER (ORDER BY strike_price) as call_chg_oi,
            put_oi - LAG(put_oi, 1, 0) OVER (ORDER BY strike_price) as put_chg_oi,
            CASE 
                WHEN strike_price < spot_price THEN 'ITM Call / OTM Put'
                WHEN strike_price = spot_price THEN 'ATM'
                ELSE 'OTM Call / ITM Put'
            END as bucket_type,
            ABS(strike_price - spot_price) as distance_from_spot,
            timestamp_ist
        FROM latest_data
        ORDER BY strike_price
    """
    
    df = pd.read_sql_query(query, conn)
    conn.close()
    
    if df.empty:
        print(f"⚠️  No data found for {symbol}")
        return None
    
    # Create output directory
    os.makedirs(output_dir, exist_ok=True)
    
    # Generate filename with timestamp
    filename = f"{output_dir}/bucket_summary_{symbol}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    
    # Export to Excel with multiple sheets
    with pd.ExcelWriter(filename, engine='openpyxl') as writer:
        # Full data
        df.to_excel(writer, index=False, sheet_name='All Strikes')
        
        # ITM Calls (OTM Puts)
        itm_calls = df[df['bucket_type'] == 'ITM Call / OTM Put'].copy()
        itm_calls.to_excel(writer, index=False, sheet_name='ITM Calls')
        
        # ATM
        atm = df[df['bucket_type'] == 'ATM'].copy()
        atm.to_excel(writer, index=False, sheet_name='ATM')
        
        # OTM Calls (ITM Puts)
        otm_calls = df[df['bucket_type'] == 'OTM Call / ITM Put'].copy()
        otm_calls.to_excel(writer, index=False, sheet_name='OTM Calls')
        
        # Summary statistics
        summary = pd.DataFrame({
            'Metric': [
                'Total Strikes',
                'Spot Price',
                'ATM Strike',
                'Total Call OI',
                'Total Put OI',
                'PCR OI',
                'Total Call Volume',
                'Total Put Volume',
                'Data Timestamp'
            ],
            'Value': [
                len(df),
                df['spot_price'].iloc[0] if len(df) > 0 else 0,
                df[df['bucket_type'] == 'ATM']['strike_price'].iloc[0] if len(atm) > 0 else 0,
                df['call_oi'].sum(),
                df['put_oi'].sum(),
                df['put_oi'].sum() / df['call_oi'].sum() if df['call_oi'].sum() > 0 else 0,
                df['call_volume'].sum(),
                df['put_volume'].sum(),
                df['timestamp_ist'].iloc[0] if len(df) > 0 else None
            ]
        })
        summary.to_excel(writer, index=False, sheet_name='Summary')
    
    print(f"✅ Exported bucket summary to: {filename}")
    print(f"   Spot: {df['spot_price'].iloc[0]:.2f}")
    print(f"   Total Strikes: {len(df)}")
    print(f"   ITM Calls: {len(itm_calls)}, ATM: {len(atm)}, OTM Calls: {len(otm_calls)}")
    print(f"   PCR OI: {df['put_oi'].sum() / df['call_oi'].sum():.2f}")
    
    return filename


def export_full_option_chain_table(symbol='NIFTY', output_dir='exports', days_back=1):
    """Export complete option chain data in table format with all calculations"""
    print(f"📊 Exporting full option chain table for {symbol} (last {days_back} days)...")
    
    conn = psycopg2.connect(**DB_CONFIG)
    
    query = f"""
        SELECT 
            timestamp AT TIME ZONE 'Asia/Kolkata' as timestamp_ist,
            symbol,
            expiry_date,
            spot_price,
            strike_price,
            
            -- Call Options
            call_oi,
            call_volume,
            call_ltp,
            call_bid,
            call_ask,
            call_iv,
            call_delta,
            call_gamma,
            call_vega,
            call_theta,
            
            -- Put Options  
            put_oi,
            put_volume,
            put_ltp,
            put_bid,
            put_ask,
            put_iv,
            put_delta,
            put_gamma,
            put_vega,
            put_theta,
            
            -- Ratios
            pcr_oi,
            pcr_volume,
            
            -- Change in OI
            call_oi - LAG(call_oi, 1, 0) OVER (PARTITION BY strike_price ORDER BY timestamp) as call_chg_oi,
            put_oi - LAG(put_oi, 1, 0) OVER (PARTITION BY strike_price ORDER BY timestamp) as put_chg_oi,
            
            -- Position Analysis
            CASE 
                WHEN (call_ltp - LAG(call_ltp, 1, call_ltp) OVER (PARTITION BY strike_price ORDER BY timestamp)) > 0 
                     AND (call_oi - LAG(call_oi, 1, 0) OVER (PARTITION BY strike_price ORDER BY timestamp)) > 0 
                THEN 'Long Build'
                WHEN (call_ltp - LAG(call_ltp, 1, call_ltp) OVER (PARTITION BY strike_price ORDER BY timestamp)) > 0 
                     AND (call_oi - LAG(call_oi, 1, 0) OVER (PARTITION BY strike_price ORDER BY timestamp)) < 0 
                THEN 'Short Covering'
                WHEN (call_ltp - LAG(call_ltp, 1, call_ltp) OVER (PARTITION BY strike_price ORDER BY timestamp)) < 0 
                     AND (call_oi - LAG(call_oi, 1, 0) OVER (PARTITION BY strike_price ORDER BY timestamp)) > 0 
                THEN 'Short Buildup'
                WHEN (call_ltp - LAG(call_ltp, 1, call_ltp) OVER (PARTITION BY strike_price ORDER BY timestamp)) < 0 
                     AND (call_oi - LAG(call_oi, 1, 0) OVER (PARTITION BY strike_price ORDER BY timestamp)) < 0 
                THEN 'Long Unwinding'
                ELSE 'No Change'
            END as call_position,
            
            CASE 
                WHEN (put_ltp - LAG(put_ltp, 1, put_ltp) OVER (PARTITION BY strike_price ORDER BY timestamp)) > 0 
                     AND (put_oi - LAG(put_oi, 1, 0) OVER (PARTITION BY strike_price ORDER BY timestamp)) > 0 
                THEN 'Long Build'
                WHEN (put_ltp - LAG(put_ltp, 1, put_ltp) OVER (PARTITION BY strike_price ORDER BY timestamp)) > 0 
                     AND (put_oi - LAG(put_oi, 1, 0) OVER (PARTITION BY strike_price ORDER BY timestamp)) < 0 
                THEN 'Short Covering'
                WHEN (put_ltp - LAG(put_ltp, 1, put_ltp) OVER (PARTITION BY strike_price ORDER BY timestamp)) < 0 
                     AND (put_oi - LAG(put_oi, 1, 0) OVER (PARTITION BY strike_price ORDER BY timestamp)) > 0 
                THEN 'Short Buildup'
                WHEN (put_ltp - LAG(put_ltp, 1, put_ltp) OVER (PARTITION BY strike_price ORDER BY timestamp)) < 0 
                     AND (put_oi - LAG(put_oi, 1, 0) OVER (PARTITION BY strike_price ORDER BY timestamp)) < 0 
                THEN 'Long Unwinding'
                ELSE 'No Change'
            END as put_position,
            
            -- Strike Type
            CASE 
                WHEN strike_price < spot_price THEN 'ITM Call'
                WHEN strike_price = ROUND(spot_price / 50) * 50 THEN 'ATM'
                ELSE 'OTM Call'
            END as strike_type
            
        FROM option_chain_data
        WHERE symbol = '{symbol}'
        AND timestamp > NOW() - INTERVAL '{days_back} days'
        ORDER BY timestamp DESC, strike_price
        LIMIT 100000
    """
    
    df = pd.read_sql_query(query, conn)
    conn.close()
    
    if df.empty:
        print(f"⚠️  No data found for {symbol}")
        return None
    
    # Create output directory
    os.makedirs(output_dir, exist_ok=True)
    
    # Generate filename with timestamp
    filename = f"{output_dir}/full_option_chain_{symbol}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    
    # Group by timestamp for multiple sheets
    timestamps = df['timestamp_ist'].unique()[:5]  # Latest 5 timestamps
    
    with pd.ExcelWriter(filename, engine='openpyxl') as writer:
        # Full data
        df.to_excel(writer, index=False, sheet_name='All Data')
        
        # Latest snapshot
        latest = df[df['timestamp_ist'] == df['timestamp_ist'].max()].copy()
        latest.to_excel(writer, index=False, sheet_name='Latest')
        
        # Create sheets for each recent timestamp
        for i, ts in enumerate(timestamps[:3]):
            sheet_name = f"T{i+1}_{pd.Timestamp(ts).strftime('%H%M')}"
            df_ts = df[df['timestamp_ist'] == ts].copy()
            df_ts.to_excel(writer, index=False, sheet_name=sheet_name[:31])  # Excel sheet name limit
    
    print(f"✅ Exported full option chain to: {filename}")
    print(f"   Total records: {len(df)}")
    print(f"   Date range: {df['timestamp_ist'].min()} to {df['timestamp_ist'].max()}")
    print(f"   Unique timestamps: {len(df['timestamp_ist'].unique())}")
    
    return filename


def export_custom_query(query, filename_prefix='custom', output_dir='exports'):
    """Export results of a custom SQL query"""
    print(f"📊 Executing custom query...")
    
    conn = psycopg2.connect(**DB_CONFIG)
    df = pd.read_sql_query(query, conn)
    conn.close()
    
    # Create output directory
    os.makedirs(output_dir, exist_ok=True)
    
    # Generate filename with timestamp
    filename = f"{output_dir}/{filename_prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    
    # Export to Excel
    df.to_excel(filename, index=False)
    
    print(f"✅ Exported {len(df)} records to: {filename}")
    
    return filename


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Export cloud database to Excel')
    parser.add_argument('--export', choices=['gamma', 'option_chain', 'blasts', 'summary', 'bucket', 'table', 'all'], 
                       default='all', help='What to export')
    parser.add_argument('--symbol', default='NIFTY', help='Symbol for option chain export')
    parser.add_argument('--days', type=int, default=7, help='Days of history to export')
    parser.add_argument('--output', default='exports', help='Output directory')
    parser.add_argument('--min-prob', type=float, default=0.3, help='Minimum probability for blast export')
    
    args = parser.parse_args()
    
    print("=" * 70)
    print("📥 EXPORTING DATA FROM CLOUD DATABASE TO EXCEL")
    print("=" * 70)
    print(f"Database: {DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['database']}")
    print(f"Output directory: {args.output}/")
    print("=" * 70)
    print()
    
    try:
        files_created = []
        
        if args.export in ['gamma', 'all']:
            file = export_gamma_exposure_history(args.output, args.days)
            files_created.append(file)
            print()
        
        if args.export in ['option_chain', 'all']:
            file = export_option_chain_data(args.symbol, args.output, args.days)
            files_created.append(file)
            print()
        
        if args.export in ['blasts', 'all']:
            file = export_latest_gamma_blasts(args.output, args.min_prob)
            files_created.append(file)
            print()
        
        if args.export in ['summary', 'all']:
            file = export_all_symbols_summary(args.output)
            files_created.append(file)
            print()
        
        if args.export in ['bucket', 'all']:
            file = export_bucket_summary(args.symbol, args.output)
            if file:
                files_created.append(file)
            print()
        
        if args.export in ['table', 'all']:
            file = export_full_option_chain_table(args.symbol, args.output, args.days)
            if file:
                files_created.append(file)
            print()
        
        print("=" * 70)
        print("✅ EXPORT COMPLETE!")
        print("=" * 70)
        print(f"Files created: {len(files_created)}")
        for f in files_created:
            print(f"  - {f}")
        print()
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
