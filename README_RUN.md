# How to Run the Complete Architecture

## Quick Start (3 Steps)

### 1. Set Up Database (One-time setup)

**Using Docker (Easiest):**
```bash
docker run -d \
  --name timescaledb \
  -p 5432:5432 \
  -e POSTGRES_PASSWORD=postgres \
  -e POSTGRES_DB=optionchain \
  timescale/timescaledb:latest-pg14
```

**Or using the automated script:**
```bash
cd "/Users/navneet/Desktop/Stock Option /OptionChainUsingUpstock"
./start_complete_system.sh
```

### 2. Set Database Credentials

```bash
export DB_HOST=localhost
export DB_PORT=5432
export DB_NAME=optionchain
export DB_USER=postgres
export DB_PASSWORD=postgres
```

### 3. Start Everything

**Option A: Automated (Recommended)**
```bash
./start_complete_system.sh
```

**Option B: Manual (Two Terminals)**

Terminal 1 - Background Service:
```bash
python3 background_service.py --interval 30
```

Terminal 2 - Streamlit UI:
```bash
streamlit run optionchain.py
```

---

## What Happens

### Background Service:
- ✅ Runs continuously in the background
- ✅ Fetches data for all symbols every 30 seconds
- ✅ Stores data in TimescaleDB
- ✅ Only runs during market hours (9:15 AM - 3:30 PM IST)

### Streamlit UI:
- ✅ Reads data from TimescaleDB (fast!)
- ✅ Shows "Production Mode" when database is connected
- ✅ Allows switching symbols without interruption
- ✅ Displays real-time option chain data

### Database:
- ✅ Stores all historical data
- ✅ Enables fast queries
- ✅ Supports time-series analysis

---

## Verify It's Working

### Check Background Service:
```bash
# View logs
tail -f background_service.log

# Should see:
# "Successfully stored data for NIFTY"
# "Successfully stored data for BANKNIFTY"
```

### Check Database:
```bash
psql -U postgres -d optionchain -c "SELECT COUNT(*) FROM option_chain_data;"
```

### Check UI:
1. Open http://localhost:8501
2. Should see "✅ Production Mode: Reading from TimescaleDB"
3. Select symbol and expiry
4. Click "Load from Database"
5. Data appears instantly!

---

## Architecture Flow

```
┌──────────────────┐
│  Upstox API      │
└────────┬─────────┘
         │
         │ (fetches every 30s)
         ▼
┌──────────────────┐
│  Background      │
│  Service         │
└────────┬─────────┘
         │
         │ (stores)
         ▼
┌──────────────────┐
│  TimescaleDB     │
│  (PostgreSQL)    │
└────────┬─────────┘
         │
         │ (reads)
         ▼
┌──────────────────┐
│  Streamlit UI    │
│  (User Interface)│
└──────────────────┘
```

---

## Troubleshooting

**Database not connecting?**
- Check: `docker ps | grep timescaledb` (if using Docker)
- Check: `brew services list | grep postgresql` (if using Homebrew)
- Verify credentials in environment variables

**Background service not fetching?**
- Check market hours (9:15 AM - 3:30 PM IST, Mon-Fri)
- Check logs: `tail -50 background_service.log`
- Verify Upstox credentials in `.streamlit/secrets.toml`

**UI showing "Direct API Mode"?**
- Database is not connected
- Run: `python3 -c "from database import TimescaleDBManager; db = TimescaleDBManager()"`

---

## Full Documentation

See `SETUP_GUIDE.md` for detailed setup instructions.

See `README_PRODUCTION.md` for production deployment options.

