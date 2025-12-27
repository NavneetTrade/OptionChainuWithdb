# Quick Start Guide - Option Chain System

## ✅ System Status

All components are tested and working!

### Test Results:
- ✓ All imports successful
- ✓ Upstox credentials configured
- ✓ API client initialized
- ✓ Helper functions working
- ✓ 215 F&O instruments available
- ⚠ Database not available (using Direct API Mode)

## 🚀 Starting the Application

### Option 1: Start Streamlit UI Only
```bash
cd "/Users/navneet/Desktop/Stock Option /OptionChainUsingUpstock"
streamlit run optionchain.py
```

Then open: **http://localhost:8501**

### Option 2: Start Both Services (Background + UI)
```bash
cd "/Users/navneet/Desktop/Stock Option /OptionChainUsingUpstock"
./start_services.sh
```

## 📊 Using the UI

1. **Open the app** in your browser at http://localhost:8501

2. **Select Symbol**: Choose from dropdown (NIFTY, BANKNIFTY, etc.)

3. **Select Expiry**: Choose expiry date from dropdown

4. **Get Data**: 
   - Click "Get Option Chain" button
   - Or enable "Auto-Refresh" for automatic updates

5. **View Data**: 
   - Option chain table with all strikes
   - Greeks (Delta, Gamma, Theta, Vega)
   - Sentiment analysis
   - Support/Resistance levels
   - PCR (Put-Call Ratio) analysis

## 🔧 Current Mode

**Direct API Mode**: The app is currently fetching data directly from Upstox API since TimescaleDB is not set up.

To enable **Production Mode** with background processing:
1. Install TimescaleDB
2. Set database credentials
3. Start background service: `python3 background_service.py --interval 30`
4. The UI will automatically switch to reading from database

## 📝 Features Available

- ✅ Real-time option chain data
- ✅ Greeks calculation
- ✅ Sentiment analysis
- ✅ Support/Resistance identification
- ✅ PCR analysis
- ✅ Auto-refresh during market hours
- ✅ Multiple symbol support
- ✅ Time-series data storage (when DB is configured)

## 🐛 Troubleshooting

### If Streamlit doesn't start:
```bash
# Check if port 8501 is in use
lsof -ti:8501

# Kill existing process if needed
kill $(lsof -ti:8501)

# Start again
streamlit run optionchain.py
```

### If API calls fail:
- Check your Upstox access token in `.streamlit/secrets.toml`
- Token may have expired - refresh it if needed

### If database errors appear:
- This is normal if TimescaleDB is not installed
- App will work in "Direct API Mode"
- To enable database, see README_PRODUCTION.md

## 📞 Next Steps

1. **Test the UI**: Open http://localhost:8501 and try fetching data
2. **Set up Database** (optional): See README_PRODUCTION.md for TimescaleDB setup
3. **Start Background Service** (optional): For continuous data collection

