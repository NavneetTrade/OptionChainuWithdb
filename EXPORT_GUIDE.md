# Database Export to Excel - Quick Guide

## Installation (Already Done)
```bash
pip install psycopg2-binary openpyxl pandas
```

## Usage Examples

### 1. Export Everything (Recommended)
```bash
cd "/Users/navneet/Desktop/Stock Option /OptionChainUsingUpstock"
python3 export_db_to_excel.py --export all --days 7
```

This creates 6 Excel files in the `exports/` folder:
- `gamma_exposure_history_*.xlsx` - All gamma blast data
- `option_chain_NIFTY_*.xlsx` - NIFTY option chain data
- `gamma_blasts_latest_*.xlsx` - Latest high-probability signals
- `all_symbols_summary_*.xlsx` - Summary of all symbols
- `bucket_summary_NIFTY_*.xlsx` - Strike buckets (ITM/ATM/OTM) with analysis
- `full_option_chain_NIFTY_*.xlsx` - Complete option chain with greeks & positions

### 2. Export Only Gamma Blasts (Last 7 Days)
```bash
python3 export_db_to_excel.py --export gamma --days 7
```

### 3. Export Option Chain for Specific Symbol
```bash
python3 export_db_to_excel.py --export option_chain --symbol BANKNIFTY --days 1
```

### 4. Export Latest High-Probability Gamma Blasts
```bash
python3 export_db_to_excel.py --export blasts --min-prob 0.4
```

### 5. Export Summary of All Symbols
```bash
python3 export_db_to_excel.py --export summary
```

### 6. Export Bucket Summary (Strike Analysis)
```bash
python3 export_db_to_excel.py --export bucket --symbol NIFTY
```
Creates Excel with multiple sheets:
- All Strikes - Complete data
- ITM Calls - In-the-money call strikes
- ATM - At-the-money strikes
- OTM Calls - Out-of-the-money call strikes
- Summary - Statistics and totals

### 7. Export Full Option Chain Table
```bash
python3 export_db_to_excel.py --export table --symbol BANKNIFTY --days 1
```
Includes:
- All Greeks (delta, gamma, vega, theta)
- Position analysis (Long Build, Short Covering, etc.)
- Change in OI calculations
- Multiple sheets for different timestamps

### 8. Custom Days Range
```bash
# Last 30 days of data
python3 export_db_to_excel.py --export all --days 30
```

### 9. Custom Output Directory
```bash
python3 export_db_to_excel.py --export all --output my_exports
```

## Command Line Options

- `--export` : What to export (gamma, option_chain, blasts, summary, bucket, table, all)
- `--symbol` : Symbol for option chain export (default: NIFTY)
- `--days` : Number of days of history (default: 7)
- `--output` : Output directory (default: exports)
- `--min-prob` : Minimum probability for blast export (default: 0.3)

## Output Files

All files are created with timestamps in the filename:
- Format: `exports/[type]_[YYYYMMDD_HHMMSS].xlsx`
- Example: `exports/gamma_exposure_history_20260110_063000.xlsx`

## What Each Export Contains

### Gamma Exposure History
- Symbol, timestamp (IST), spot price
- Net GEX, gamma blast probability
- Direction (UPSIDE/DOWNSIDE/NEUTRAL)
- Confidence level
- CE/PE delta and ITM change in OI

### Option Chain Data
- Strike-by-strike data for a symbol
- Call/Put OI, volume, LTP, IV
- PCR ratios
- Limited to 50,000 rows per export

### Latest Gamma Blasts
- Only symbols with probability > threshold
- Sorted by probability (highest first)
- Shows latest data point for each symbol

### All Symbols Summary
- Latest update time for each symbol
- Current probability and direction
- Statistics: avg probability, max probability
- Total records count

### Bucket Summary (NEW!)
- Strike-wise data grouped by ITM/ATM/OTM
- Separate sheets for each bucket type
- Change in OI calculations
- Distance from spot price
- Summary statistics (Total OI, PCR, etc.)
- Perfect for analyzing strike distribution

### Full Option Chain Table (NEW!)
- Complete option chain with all fields
- All Greeks: delta, gamma, vega, theta
- Position signals: Long Build, Short Covering, etc.
- Change in OI for both calls and puts
- Strike type classification
- Multiple sheets for different timestamps
- Includes bid/ask spreads

## Database Connection

The script connects to your cloud PostgreSQL:
- Host: 92.4.74.245
- Port: 5432
- Database: optionchain
- User: postgres

**Note:** Make sure your cloud server firewall allows PostgreSQL connections (port 5432) from your IP if you get connection errors.

## Examples

```bash
# Quick export - everything from today
python3 export_db_to_excel.py --export all --days 1

# Get all BANKNIFTY data from last week
python3 export_db_to_excel.py --export option_chain --symbol BANKNIFTY --days 7

# Only high-confidence signals (>50% probability)
python3 export_db_to_excel.py --export blasts --min-prob 0.5

# Export bucket analysis for NIFTY (latest snapshot)
python3 export_db_to_excel.py --export bucket --symbol NIFTY

# Export full table with greeks for BANKNIFTY (last 2 days)
python3 export_db_to_excel.py --export table --symbol BANKNIFTY --days 2

# Export only bucket and table for analysis
python3 export_db_to_excel.py --export bucket --symbol NIFTY && \
python3 export_db_to_excel.py --export table --symbol NIFTY --days 1
```

## Opening Excel Files

The files are created in the `exports/` folder. You can:
1. Open directly in Excel/Numbers
2. Import into Google Sheets
3. Process further with pandas in Python

Enjoy! 🎉
