# Active Files in System

## Core Application Files
- `background_service.py` - Background data collection service
- `dashboard_app.py` - Modern Flask dashboard with WebSocket
- `database.py` - TimescaleDB interface layer
- `upstox_api.py` - Upstox API client
- `optionchain.py` - Streamlit app (legacy, use dashboard instead)
- `config.py` - Configuration settings
- `websocket_manager.py` - WebSocket manager (optional)

## Utility Scripts
- `start_system.sh` - Start all services
- `stop_system.sh` - Stop all services
- `clear_database.py` - Clear database tables

## Configuration
- `.streamlit/secrets.toml` - API credentials
- `requirements.txt` - Python dependencies (Streamlit)
- `requirements_dashboard.txt` - Python dependencies (Dashboard)

## Templates
- `templates/dashboard.html` - Modern dashboard UI

## Documentation
- `README.md` - Main documentation
- `SYSTEM_FIXED.md` - Details on fixes and improvements

## Logs (Created at runtime)
- `logs/background_service.log` - Background service logs
- `logs/dashboard.log` - Dashboard logs
- `background_service.log` - Fallback log location
