# Production-Grade Option Chain System

This is a production-grade option chain monitoring system with background processing and TimescaleDB storage.

## Architecture

The system consists of three main components:

1. **Background Service** (`background_service.py`) - Continuously fetches data for all configured symbols
2. **Database Layer** (`database.py`) - TimescaleDB integration for time-series data storage
3. **Streamlit Dashboard** (`optionchain.py`) - User interface that reads from database

## Features

- ✅ **Background Processing**: Automatically fetches data for all symbols without user interaction
- ✅ **TimescaleDB Storage**: Efficient time-series storage with automatic data retention
- ✅ **Non-Blocking**: User can switch symbols without interrupting background processing
- ✅ **Production Ready**: Connection pooling, error handling, logging
- ✅ **Market Hours Aware**: Only fetches data during market hours
- ✅ **Parallel Processing**: Fetches multiple symbols simultaneously

## Setup Instructions

### 1. Install TimescaleDB

#### On macOS (using Homebrew):
```bash
brew install timescaledb
brew services start timescaledb
```

#### On Ubuntu/Debian:
```bash
# Add TimescaleDB repository
sudo sh -c "echo 'deb https://packagecloud.io/timescale/timescaledb/ubuntu/ $(lsb_release -c -s) main' > /etc/apt/sources.list.d/timescaledb.list"
wget --quiet -O - https://packagecloud.io/timescale/timescaledb/gpgkey | sudo apt-key add -
sudo apt-get update
sudo apt-get install timescaledb-2-postgresql-14

# Tune PostgreSQL for TimescaleDB
sudo timescaledb-tune
sudo systemctl restart postgresql
```

#### On Docker:
```bash
docker run -d \
  --name timescaledb \
  -p 5432:5432 \
  -e POSTGRES_PASSWORD=postgres \
  -e POSTGRES_DB=optionchain \
  timescale/timescaledb:latest-pg14
```

### 2. Create Database

```bash
# Connect to PostgreSQL
psql -U postgres

# Create database
CREATE DATABASE optionchain;

# Connect to the database
\c optionchain

# Enable TimescaleDB extension
CREATE EXTENSION IF NOT EXISTS timescaledb;
```

### 3. Install Python Dependencies

```bash
cd OptionChainUsingUpstock
pip install -r requirements.txt
```

### 4. Configure Environment Variables

Create a `.env` file or set environment variables:

```bash
export DB_HOST=localhost
export DB_PORT=5432
export DB_NAME=optionchain
export DB_USER=postgres
export DB_PASSWORD=postgres
export REFRESH_INTERVAL=30
```

Or modify `config.py` with your database credentials.

### 5. Configure Upstox Credentials

Ensure `.streamlit/secrets.toml` exists with your Upstox credentials:

```toml
[upstox]
access_token="your_access_token"
api_key="your_api_key"
api_secret="your_api_secret"
redirect_uri="your_redirect_uri"
```

### 6. Start Background Service

```bash
# Start the background service
python background_service.py --interval 30

# Or run in background
nohup python background_service.py --interval 30 > background_service.log 2>&1 &
```

The background service will:
- Fetch data for all configured symbols every 30 seconds (or your configured interval)
- Only run during market hours (9:15 AM - 3:30 PM IST, Mon-Fri)
- Store data in TimescaleDB
- Continue running even when Streamlit app is not open

### 7. Start Streamlit Dashboard

```bash
streamlit run optionchain.py
```

The dashboard will:
- Automatically detect if database is available
- Read data from TimescaleDB (if available) or fallback to direct API calls
- Show data source status (Database vs API)
- Allow switching between symbols without interrupting background processing

## Usage

### Background Service

The background service runs independently and continuously fetches data:

```bash
# Start with default 30-second interval
python background_service.py

# Start with custom interval (60 seconds)
python background_service.py --interval 60

# View logs
tail -f background_service.log
```

### Streamlit Dashboard

1. Open the dashboard: `streamlit run optionchain.py`
2. Select a symbol from the dropdown
3. Select an expiry date
4. Click "Load from Database" (or "Get Option Chain" if database unavailable)
5. Data will be displayed from the database (if available) or fetched from API

### Adding New Symbols

Symbols are automatically discovered from the F&O instruments list. To manually add symbols:

```python
from database import TimescaleDBManager

db = TimescaleDBManager()
db.update_symbol_config('SYMBOL_NAME', 'NSE_INDEX|Symbol Name', refresh_interval=30)
```

## Database Schema

### option_chain_data (Hypertable)

Stores time-series option chain data:

- `timestamp`: Timestamp of data capture
- `symbol`: Symbol name (e.g., 'NIFTY')
- `instrument_key`: Instrument key
- `expiry_date`: Expiry date
- `strike_price`: Strike price
- `option_type`: 'CE' or 'PE'
- Market data: `ltp`, `volume`, `oi`, `prev_oi`, `chg_oi`, `close_price`, `change`
- Greeks: `iv`, `delta`, `gamma`, `theta`, `vega`
- `spot_price`: Spot price at time of capture

### symbol_config

Stores symbol configurations:

- `symbol`: Symbol name (primary key)
- `instrument_key`: Instrument key
- `is_active`: Whether symbol is actively monitored
- `refresh_interval_seconds`: Refresh interval for this symbol
- `last_updated`: Last update timestamp

## Monitoring

### Check Background Service Status

```bash
# Check if process is running
ps aux | grep background_service

# View recent logs
tail -n 100 background_service.log

# Check database connection
psql -U postgres -d optionchain -c "SELECT COUNT(*) FROM option_chain_data;"
```

### Database Queries

```sql
-- Get latest data timestamp for a symbol
SELECT MAX(timestamp) 
FROM option_chain_data 
WHERE symbol = 'NIFTY';

-- Get data count per symbol
SELECT symbol, COUNT(*) as count 
FROM option_chain_data 
GROUP BY symbol;

-- Get latest option chain for NIFTY
SELECT * 
FROM option_chain_data 
WHERE symbol = 'NIFTY' 
  AND timestamp = (SELECT MAX(timestamp) FROM option_chain_data WHERE symbol = 'NIFTY')
ORDER BY strike_price, option_type;
```

## Troubleshooting

### Database Connection Issues

1. Verify PostgreSQL/TimescaleDB is running:
   ```bash
   sudo systemctl status postgresql
   ```

2. Check database credentials in `config.py` or environment variables

3. Test connection:
   ```python
   from database import TimescaleDBManager
   db = TimescaleDBManager()
   ```

### Background Service Not Fetching Data

1. Check if market is open (9:15 AM - 3:30 PM IST, Mon-Fri)
2. Verify Upstox credentials in `.streamlit/secrets.toml`
3. Check logs: `tail -f background_service.log`
4. Verify symbols are configured: Check `symbol_config` table

### Streamlit App Not Loading Data

1. Check if database is available (look for "Production Mode" message)
2. Verify background service is running and has fetched data
3. Check database for latest data:
   ```sql
   SELECT MAX(timestamp) FROM option_chain_data;
   ```
4. If database unavailable, app will fallback to direct API calls

## Performance Optimization

### Database Tuning

TimescaleDB automatically optimizes for time-series data. For large datasets:

```sql
-- Add compression (for data older than 7 days)
SELECT add_compression_policy('option_chain_data', INTERVAL '7 days');

-- Add retention policy (delete data older than 90 days)
SELECT add_retention_policy('option_chain_data', INTERVAL '90 days');
```

### Background Service Tuning

- Adjust `refresh_interval` based on your needs (minimum: 10 seconds)
- Adjust `max_workers` in ThreadPoolExecutor based on CPU cores
- Monitor memory usage with many symbols

## Production Deployment

### Systemd Service (Linux)

Create `/etc/systemd/system/optionchain-background.service`:

```ini
[Unit]
Description=Option Chain Background Service
After=network.target postgresql.service

[Service]
Type=simple
User=your_user
WorkingDirectory=/path/to/OptionChainUsingUpstock
Environment="DB_HOST=localhost"
Environment="DB_NAME=optionchain"
Environment="DB_USER=postgres"
Environment="DB_PASSWORD=postgres"
ExecStart=/usr/bin/python3 /path/to/OptionChainUsingUpstock/background_service.py --interval 30
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl enable optionchain-background
sudo systemctl start optionchain-background
sudo systemctl status optionchain-background
```

### Docker Compose

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
    command: python background_service.py --interval 30
    environment:
      DB_HOST: timescaledb
      DB_NAME: optionchain
      DB_USER: postgres
      DB_PASSWORD: postgres
    depends_on:
      - timescaledb
    volumes:
      - ./.streamlit:/app/.streamlit

volumes:
  timescaledb_data:
```

## License

[Your License Here]

