# Option Chain Analysis System

A production-grade option chain analysis system with real-time data fetching, TimescaleDB storage, and comprehensive sentiment analysis.

## Features

- **Real-time Data Fetching**: Background service continuously fetches option chain data from Upstox API
- **TimescaleDB Storage**: Efficient time-series data storage for historical analysis
- **Market Hours Aware**: Only fetches data during market hours (9:15 AM - 3:30 PM IST)
- **Sentiment Analysis**: Comprehensive multi-factor sentiment scoring
- **ITM Filtering**: Configurable ITM strike filtering for focused analysis
- **Streamlit UI**: Interactive dashboard with two tabs:
  - Option Chain Analysis: Detailed option chain view with sentiment
  - Sentiment Dashboard: Extreme signals (bullish/bearish) with ITM filtering

## Architecture

```
Background Service → Upstox API → TimescaleDB
                              ↓
                    Option Chain Analysis (UI)
                              ↓
                    Sentiment Dashboard (UI)
```

## Prerequisites

- Python 3.8+
- PostgreSQL 14+ with TimescaleDB extension
- Upstox API credentials

## Installation

1. Clone the repository:
```bash
git clone <repository-url>
cd OptionChainUsingUpstock
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Set up TimescaleDB (see `SETUP_GUIDE.md` for detailed instructions)

4. Configure Upstox credentials:
   - Create `.streamlit/secrets.toml` file
   - Add your Upstox API credentials:
```toml
[upstox]
access_token = "your_access_token"
api_key = "your_api_key"
api_secret = "your_api_secret"
redirect_uri = "your_redirect_uri"
```

5. Set environment variables:
```bash
export DB_HOST=localhost
export DB_PORT=5432
export DB_NAME=optionchain
export DB_USER=your_username
export DB_PASSWORD=your_password
```

## Usage

### Start All Services

```bash
./start_all.sh
```

This will:
- Check and start PostgreSQL/TimescaleDB
- Start background service
- Start Streamlit UI

### Manual Start

1. Start background service:
```bash
python3 background_service.py --interval 60
```

2. Start Streamlit UI:
```bash
streamlit run optionchain.py
```

### Stop All Services

```bash
./stop_all.sh
```

## Configuration

- **Refresh Interval**: Default 60 seconds (configurable via `--interval` flag)
- **ITM Strikes**: Selectable in UI (1, 2, 3, or 5 strikes)
- **Market Hours**: 9:15 AM - 3:30 PM IST (Monday-Friday)

## Project Structure

```
OptionChainUsingUpstock/
├── background_service.py      # Background data fetching service
├── optionchain.py            # Main Streamlit UI
├── sentiment_dashboard.py    # Sentiment dashboard module
├── database.py               # TimescaleDB operations
├── upstox_api.py            # Upstox API client
├── websocket_manager.py     # WebSocket manager (disabled)
├── start_all.sh             # Start all services
├── stop_all.sh              # Stop all services
└── requirements.txt          # Python dependencies
```

## Documentation

- `SETUP_GUIDE.md`: Detailed setup instructions
- `README_PRODUCTION.md`: Production deployment guide
- `QUICK_START.md`: Quick start guide

## License

[Add your license here]

## Contributing

[Add contribution guidelines here]

