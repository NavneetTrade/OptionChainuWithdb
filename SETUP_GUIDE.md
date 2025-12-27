# Complete Setup Guide - Background Service + Database Architecture

This guide will help you set up and run the complete production system with:
- ✅ TimescaleDB for data storage
- ✅ Background service for continuous data fetching
- ✅ Streamlit UI for visualization

---

## Step 1: Install TimescaleDB

### Option A: Using Docker (Recommended - Easiest)

```bash
# Pull TimescaleDB image
docker pull timescale/timescaledb:latest-pg14

# Run TimescaleDB container
docker run -d \
  --name timescaledb \
  -p 5432:5432 \
  -e POSTGRES_PASSWORD=postgres \
  -e POSTGRES_DB=optionchain \
  -v timescaledb_data:/var/lib/postgresql/data \
  timescale/timescaledb:latest-pg14

# Verify it's running
docker ps | grep timescaledb
```

### Option B: Using Homebrew (macOS)

```bash
# Install PostgreSQL with TimescaleDB
brew install timescaledb

# Start PostgreSQL service
brew services start postgresql

# Create database
createdb optionchain

# Connect and enable TimescaleDB extension
psql optionchain -c "CREATE EXTENSION IF NOT EXISTS timescaledb;"
```

### Option C: Using apt (Ubuntu/Debian)

```bash
# Add TimescaleDB repository
sudo sh -c "echo 'deb https://packagecloud.io/timescale/timescaledb/ubuntu/ $(lsb_release -c -s) main' > /etc/apt/sources.list.d/timescaledb.list"
wget --quiet -O - https://packagecloud.io/timescale/timescaledb/gpgkey | sudo apt-key add -
sudo apt-get update
sudo apt-get install timescaledb-2-postgresql-14

# Tune PostgreSQL
sudo timescaledb-tune

# Restart PostgreSQL
sudo systemctl restart postgresql

# Create database
sudo -u postgres createdb optionchain
sudo -u postgres psql optionchain -c "CREATE EXTENSION IF NOT EXISTS timescaledb;"
```

---

## Step 2: Configure Database Credentials

### Option A: Environment Variables (Recommended)

Create a `.env` file or export variables:

```bash
export DB_HOST=localhost
export DB_PORT=5432
export DB_NAME=optionchain
export DB_USER=postgres
export DB_PASSWORD=postgres
export REFRESH_INTERVAL=30
```

Or add to your `~/.zshrc` or `~/.bashrc`:
```bash
echo 'export DB_HOST=localhost' >> ~/.zshrc
echo 'export DB_PORT=5432' >> ~/.zshrc
echo 'export DB_NAME=optionchain' >> ~/.zshrc
echo 'export DB_USER=postgres' >> ~/.zshrc
echo 'export DB_PASSWORD=postgres' >> ~/.zshrc
source ~/.zshrc
```

### Option B: Modify config.py

Edit `config.py` and update the `DB_CONFIG` dictionary:

```python
DB_CONFIG = {
    'host': 'localhost',
    'port': '5432',
    'database': 'optionchain',
    'user': 'postgres',
    'password': 'your_password_here'
}
```

---

## Step 3: Verify Database Connection

Test the database connection:

```bash
cd "/Users/navneet/Desktop/Stock Option /OptionChainUsingUpstock"
python3 -c "
from database import TimescaleDBManager
try:
    db = TimescaleDBManager()
    if db.pool:
        print('✓ Database connection successful!')
        print('✓ Schema will be created automatically on first run')
    else:
        print('✗ Database connection failed')
except Exception as e:
    print(f'✗ Error: {e}')
"
```

---

## Step 4: Start Background Service

The background service will:
- Fetch data for all configured symbols every 30 seconds (or your configured interval)
- Store data in TimescaleDB
- Only run during market hours (9:15 AM - 3:30 PM IST, Mon-Fri)

### Start in Foreground (for testing):

```bash
cd "/Users/navneet/Desktop/Stock Option /OptionChainUsingUpstock"
python3 background_service.py --interval 30
```

You should see:
```
INFO:background_service:Starting Option Chain Background Service...
INFO:background_service:Refresh interval: 30 seconds
INFO:database:Database connection pool initialized successfully
INFO:database:Database schema initialized successfully
INFO:background_service:Database manager initialized
INFO:background_service:Upstox API initialized
INFO:background_service:Fetching data for 4 symbols...
```

### Start in Background (for production):

```bash
cd "/Users/navneet/Desktop/Stock Option /OptionChainUsingUpstock"

# Start background service
nohup python3 background_service.py --interval 30 > background_service.log 2>&1 &

# Check if it's running
ps aux | grep background_service

# View logs
tail -f background_service.log
```

### Stop Background Service:

```bash
# Find the process
ps aux | grep background_service

# Kill it (replace PID with actual process ID)
kill <PID>

# Or kill all Python background_service processes
pkill -f background_service.py
```

---

## Step 5: Start Streamlit UI

In a **new terminal window** (keep background service running):

```bash
cd "/Users/navneet/Desktop/Stock Option /OptionChainUsingUpstock"
streamlit run optionchain.py
```

The UI will:
- Automatically detect database is available
- Show "✅ Production Mode: Reading from TimescaleDB"
- Load data from database instead of fetching from API
- Allow switching symbols without interrupting background processing

Open: **http://localhost:8501**

---

## Step 6: Verify Everything is Working

### Check Background Service:

```bash
# View recent logs
tail -20 background_service.log

# Check if it's fetching data
grep "Successfully stored" background_service.log | tail -5
```

### Check Database:

```bash
# Connect to database
psql -U postgres -d optionchain

# Check if data is being stored
SELECT COUNT(*) FROM option_chain_data;

# Check latest data
SELECT symbol, MAX(timestamp) as latest 
FROM option_chain_data 
GROUP BY symbol;

# Check data for a specific symbol
SELECT * FROM option_chain_data 
WHERE symbol = 'NIFTY' 
ORDER BY timestamp DESC 
LIMIT 5;

# Exit
\q
```

### Check UI:

1. Open http://localhost:8501
2. You should see "✅ Production Mode: Reading from TimescaleDB"
3. Select a symbol (e.g., NIFTY)
4. Select an expiry
5. Click "Load from Database"
6. Data should appear instantly (from database, not API)

---

## Step 7: Production Deployment (Optional)

### Using systemd (Linux):

Create `/etc/systemd/system/optionchain-background.service`:

```ini
[Unit]
Description=Option Chain Background Service
After=network.target postgresql.service

[Service]
Type=simple
User=your_username
WorkingDirectory=/Users/navneet/Desktop/Stock Option /OptionChainUsingUpstock
Environment="DB_HOST=localhost"
Environment="DB_NAME=optionchain"
Environment="DB_USER=postgres"
Environment="DB_PASSWORD=postgres"
ExecStart=/usr/bin/python3 /Users/navneet/Desktop/Stock Option /OptionChainUsingUpstock/background_service.py --interval 30
Restart=always
RestartSec=10
StandardOutput=append:/var/log/optionchain/background_service.log
StandardError=append:/var/log/optionchain/background_service.error.log

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl enable optionchain-background
sudo systemctl start optionchain-background
sudo systemctl status optionchain-background
```

### Using Docker Compose:

Create `docker-compose.yml`:

```yaml
version: '3.8'

services:
  timescaledb:
    image: timescale/timescaledb:latest-pg14
    environment:
      POSTGRES_PASSWORD: postgres
      POSTGRES_DB: optionchain
    ports:
      - "5432:5432"
    volumes:
      - timescaledb_data:/var/lib/postgresql/data

  background-service:
    build: .
    command: python3 background_service.py --interval 30
    environment:
      DB_HOST: timescaledb
      DB_NAME: optionchain
      DB_USER: postgres
      DB_PASSWORD: postgres
    depends_on:
      - timescaledb
    volumes:
      - ./.streamlit:/app/.streamlit
    restart: unless-stopped

volumes:
  timescaledb_data:
```

Start:
```bash
docker-compose up -d
```

---

## Troubleshooting

### Database Connection Issues

**Error: "Connection refused"**
```bash
# Check if PostgreSQL is running
docker ps | grep timescaledb  # For Docker
# OR
brew services list | grep postgresql  # For Homebrew
# OR
sudo systemctl status postgresql  # For Linux

# Start if not running
docker start timescaledb
# OR
brew services start postgresql
```

**Error: "Authentication failed"**
- Check DB_USER and DB_PASSWORD in environment variables
- For Docker: Default is `postgres/postgres`
- For local install: Check PostgreSQL user permissions

### Background Service Issues

**Service not fetching data:**
```bash
# Check if market is open (9:15 AM - 3:30 PM IST, Mon-Fri)
# Check logs for errors
tail -50 background_service.log

# Verify Upstox credentials
cat .streamlit/secrets.toml
```

**Service stops unexpectedly:**
```bash
# Check logs for errors
tail -100 background_service.log

# Restart with more verbose logging
python3 background_service.py --interval 30
```

### UI Issues

**UI shows "Direct API Mode" instead of "Production Mode":**
- Database is not connected
- Check database connection: `python3 -c "from database import TimescaleDBManager; db = TimescaleDBManager()"`
- Verify environment variables are set

**No data in UI:**
- Check if background service is running and has fetched data
- Check database: `SELECT COUNT(*) FROM option_chain_data;`
- Try manual fetch: Click "Get Option Chain" button

---

## Architecture Overview

```
┌─────────────────┐
│  Background     │
│  Service        │───┐
│  (Python)       │   │
└─────────────────┘   │
                      │
                      ▼
              ┌───────────────┐
              │  TimescaleDB  │
              │  (PostgreSQL) │
              └───────────────┘
                      │
                      │
                      ▼
              ┌───────────────┐
              │  Streamlit    │
              │  UI           │
              │  (Python)     │
              └───────────────┘
```

**Data Flow:**
1. Background Service fetches data from Upstox API every 30 seconds
2. Data is stored in TimescaleDB
3. Streamlit UI reads from TimescaleDB (fast, no API calls)
4. User can switch symbols without interrupting background processing

---

## Quick Reference

### Start Everything:
```bash
# Terminal 1: Background Service
cd "/Users/navneet/Desktop/Stock Option /OptionChainUsingUpstock"
python3 background_service.py --interval 30

# Terminal 2: Streamlit UI
cd "/Users/navneet/Desktop/Stock Option /OptionChainUsingUpstock"
streamlit run optionchain.py
```

### Check Status:
```bash
# Background service
ps aux | grep background_service
tail -f background_service.log

# Database
psql -U postgres -d optionchain -c "SELECT COUNT(*) FROM option_chain_data;"

# UI
curl http://localhost:8501/_stcore/health
```

### Stop Everything:
```bash
# Stop background service
pkill -f background_service.py

# Stop Streamlit (Ctrl+C in terminal or)
pkill -f streamlit
```

---

## Next Steps

1. ✅ Set up TimescaleDB
2. ✅ Configure database credentials
3. ✅ Start background service
4. ✅ Start Streamlit UI
5. ✅ Verify data is being stored and displayed
6. ✅ Monitor logs and performance
7. ✅ Set up production deployment (optional)

Your production-grade option chain system is now ready! 🚀

