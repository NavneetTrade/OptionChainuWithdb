import streamlit as st
import requests
import pandas as pd
import json
import pytz
import time as time_module
from datetime import datetime, time, timedelta
import urllib.parse
import math
import numpy as np
import matplotlib.pyplot as plt
from scipy.stats import norm
import os
import toml

# Import database module for production-grade storage
try:
    from database import TimescaleDBManager
    DB_AVAILABLE = True
except ImportError:
    DB_AVAILABLE = False
    st.warning("Database module not available. Running in direct API mode.")

# Optional auto-refresh
try:
    from streamlit_autorefresh import st_autorefresh
    AUTORFR = True
except ImportError:
    AUTORFR = False

# Import sentiment dashboard module
try:
    from sentiment_dashboard import display_sentiment_dashboard
    SENTIMENT_AVAILABLE = True
except ImportError:
    SENTIMENT_AVAILABLE = False
    st.warning("Sentiment dashboard module not available.")

# Initialize Streamlit page config
st.set_page_config(
    page_title="Option Chain Analysis",
    page_icon="📈",
    layout="wide"
)

# Add auto-refresh at the very top of the page - THIS WILL RELOAD THE WHOLE APP EVERY 30 SECONDS
# This is a simple Streamlit approach that doesn't require streamlit-autorefresh library
if 'auto_refresh_interval' not in st.session_state:
    st.session_state.auto_refresh_interval = 30  # seconds

# Use Streamlit's built-in rerun capability for auto-refresh
def auto_refresh_page():
    """Auto-refresh the page every N seconds"""
    import time
    # This function uses Streamlit's native refresh mechanism
    st.session_state.refresh_trigger = True

# Load secrets early to catch any issues
if not hasattr(st, 'secrets'):
    st.error("Streamlit secrets not initialized! Running in development mode?")
else:
    # Try to load secrets directly to validate
    try:
        secrets_path = os.path.join(os.path.dirname(__file__), '.streamlit', 'secrets.toml')
        if os.path.exists(secrets_path):
            with open(secrets_path) as f:
                secrets_content = toml.load(f)
                if 'upstox' not in secrets_content:
                    st.error("'upstox' section not found in secrets.toml")
                    st.error(f"Available sections: {list(secrets_content.keys())}")
        else:
            st.error(f"secrets.toml file not found at: {secrets_path}")
    except Exception as e:
        st.error(f"Error loading secrets.toml: {str(e)}")

# Set up Indian timezone
IST = pytz.timezone('Asia/Kolkata')
def get_ist_now():
    """Get current time in IST"""
    return datetime.now(IST)

def format_ist_time(dt):
    """Format datetime in IST with AM/PM"""
    if dt.tzinfo is None:
        dt = IST.localize(dt)
    elif dt.tzinfo != IST:
        dt = dt.astimezone(IST)
    return dt.strftime('%I:%M:%S %p')

def get_credentials():
    """Get pre-configured developer credentials"""
    if not hasattr(st, 'secrets'):
        st.error("st.secrets is not available. Make sure you're running this with streamlit run")
        return None

    if 'upstox' not in st.secrets:
        st.error("'upstox' section not found in secrets.toml")
        sections = list(st.secrets.keys()) if hasattr(st.secrets, 'keys') else []
        st.error(f"Available sections: {sections}")
        return None

    try:
        # Try to access the credentials directly
        credentials = {
            'access_token': st.secrets.upstox.access_token,
            'api_key': st.secrets.upstox.api_key,
            'api_secret': st.secrets.upstox.api_secret,
            'redirect_uri': st.secrets.upstox.redirect_uri
        }
        return credentials
    except Exception as e:
        # If dot notation fails, try dictionary access
        try:
            credentials = {
                'access_token': st.secrets['upstox']['access_token'],
                'api_key': st.secrets['upstox']['api_key'],
                'api_secret': st.secrets['upstox']['api_secret'],
                'redirect_uri': st.secrets['upstox']['redirect_uri']
            }
            return credentials
        except Exception as inner_e:
            st.error(f"Error accessing credentials: {str(inner_e)}")
            return None

# Import UpstoxAPI from standalone module
try:
    from upstox_api import UpstoxAPI
except ImportError:
    # Fallback to local definition if module not available
    # Upstox API endpoints
    BASE_URL = "https://api.upstox.com/v2"
    AUTH_URL = "https://api-v2.upstox.com/login/authorization/dialog"
    TOKEN_URL = "https://api-v2.upstox.com/login/authorization/token"

    class UpstoxAPI:
        def __init__(self):
            self.access_token = None
            self.refresh_token = None
        
        def get_auth_url(self, api_key, redirect_uri):
            """Generate authorization URL with proper encoding"""
            rurl = urllib.parse.quote(redirect_uri, safe="")
            uri = f'{AUTH_URL}?response_type=code&client_id={api_key}&redirect_uri={rurl}'
            return uri
        
        def get_access_token(self, auth_code, api_key, api_secret, redirect_uri):
            """Exchange authorization code for access token"""
            try:
                payload = {
                    'code': auth_code,
                    'client_id': api_key,
                    'client_secret': api_secret,
                    'redirect_uri': redirect_uri,
                    'grant_type': 'authorization_code'
                }
                
                headers = {
                    'Content-Type': 'application/x-www-form-urlencoded',
                    'Accept': 'application/json'
                }
                
                response = requests.post(TOKEN_URL, data=payload, headers=headers)
                if response.status_code == 200:
                    token_data = response.json()
                    self.access_token = token_data.get('access_token')
                    self.refresh_token = token_data.get('refresh_token')
                    return True, token_data
                else:
                    return False, response.json() if response.text else f"HTTP {response.status_code}"
            except Exception as e:
                return False, str(e)
        
        def refresh_access_token(self, api_key, api_secret, refresh_token):
            """Refresh access token using refresh token"""
            try:
                payload = {
                    'refresh_token': refresh_token,
                    'client_id': api_key,
                    'client_secret': api_secret,
                    'grant_type': 'refresh_token'
                }
                
                headers = {
                    'Content-Type': 'application/x-www-form-urlencoded',
                    'Accept': 'application/json'
                }
                
                response = requests.post(TOKEN_URL, data=payload, headers=headers)
                if response.status_code == 200:
                    token_data = response.json()
                    self.access_token = token_data.get('access_token')
                    new_refresh_token = token_data.get('refresh_token')
                    if new_refresh_token:
                        self.refresh_token = new_refresh_token
                    return True, token_data
                else:
                    return False, response.json() if response.text else f"HTTP {response.status_code}"
            except Exception as e:
                return False, str(e)
        
        def get_option_contracts(self, instrument_key, expiry_date=None):
            """Get option contracts for an underlying symbol"""
            if not self.access_token:
                return None, "Access token not available"
            
            try:
                headers = {
                    'Authorization': f'Bearer {self.access_token}',
                    'Accept': 'application/json'
                }
                
                url = f"{BASE_URL}/option/contract"
                params = {'instrument_key': instrument_key}
                
                if expiry_date:
                    params['expiry_date'] = expiry_date
                
                response = requests.get(url, headers=headers, params=params)
                
                if response.status_code == 200:
                    return response.json(), None
                else:
                    return None, response.json() if response.text else f"HTTP {response.status_code}"
            except Exception as e:
                return None, str(e)
        
        def get_pc_option_chain(self, instrument_key, expiry_date):
            """Get Put-Call option chain data using the correct endpoint"""
            if not self.access_token:
                return None, "Access token not available"
            
            try:
                headers = {
                    'Authorization': f'Bearer {self.access_token}',
                    'Accept': 'application/json'
                }
                
                url = f"{BASE_URL}/option/chain"
                params = {
                    'instrument_key': instrument_key,
                    'expiry_date': expiry_date
                }
                
                response = requests.get(url, headers=headers, params=params)
                
                if response.status_code == 200:
                    return response.json(), None
                else:
                    return None, response.json() if response.text else f"HTTP {response.status_code}"
            except Exception as e:
                return None, str(e)
        
        def get_option_greeks(self, instrument_keys):
            """Get option Greeks for specific instruments"""
            if not self.access_token:
                return None, "Access token not available"
            
            try:
                headers = {
                    'Authorization': f'Bearer {self.access_token}',
                    'Accept': 'application/json'
                }
                
                url = f"{BASE_URL}/option/greek"
                if isinstance(instrument_keys, str):
                    instrument_keys = [instrument_keys]
                
                params = {'instrument_key': ','.join(instrument_keys)}
                
                response = requests.get(url, headers=headers, params=params)
                
                if response.status_code == 200:
                    return response.json(), None
                else:
                    return None, response.json() if response.text else f"HTTP {response.status_code}"
            except Exception as e:
                return None, str(e)
        
        def get_market_data_feed(self, instrument_key, interval='1minute'):
            """Get market data feed"""
            if not self.access_token:
                return None, "Access token not available"
            
            try:
                headers = {
                    'Authorization': f'Bearer {self.access_token}',
                    'Accept': 'application/json'
                }
                
                url = f"{BASE_URL}/market-quote/ohlc"
                params = {
                    'instrument_key': instrument_key,
                    'interval': interval
                }
                
                response = requests.get(url, headers=headers, params=params)
                
                if response.status_code == 200:
                    return response.json(), None
                else:
                    return None, response.json() if response.text else f"HTTP {response.status_code}"
            except Exception as e:
                return None, str(e)
        
        def get_profile(self):
            """Get user profile to test token"""
            if not self.access_token:
                return None, "Access token not available"
            
            try:
                headers = {
                    'Authorization': f'Bearer {self.access_token}',
                    'Accept': 'application/json'
                }
                
                url = f"{BASE_URL}/user/profile"
                response = requests.get(url, headers=headers)
                
                if response.status_code == 200:
                    return response.json(), None
                else:
                    return None, response.json() if response.text else f"HTTP {response.status_code}"
            except Exception as e:
                return None, str(e)

def format_number(num: float) -> str:
    """Format large numbers for summary display"""
    if num >= 10000000:  # 1 crore
        return f"{num/10000000:.2f}Cr"
    elif num >= 100000:  # 1 lakh
        return f"{num/100000:.2f}L"
    elif num >= 1000:
        return f"{num/1000:.2f}K"
    else:
        return str(int(num)) if num == int(num) else f"{num:.2f}"

def get_position_signal(ltp: float, change: float, chg_oi: float) -> str:
    """Determine position type based on price change and change in OI"""
    if change == 0 and chg_oi == 0:
        return "No Change"
    
    price_up = change > 0
    price_down = change < 0
    oi_increase = chg_oi > 0
    oi_decrease = chg_oi < 0
    
    if price_up and oi_increase:
        return "Long Build"
    elif price_down and oi_decrease:
        return "Long Unwinding"
    elif price_down and oi_increase:
        return "Short Buildup"
    elif price_up and oi_decrease:
        return "Short Covering"
    elif oi_increase and change == 0:
        return "Fresh Positions"
    elif oi_decrease and change == 0:
        return "Position Unwinding"
    else:
        return "Mixed Activity"

def get_position_color(position: str) -> str:
    """Get color for position type"""
    colors = {
        "Long Build": "#4caf50",
        "Long Unwinding": "#ff5722", 
        "Short Buildup": "#f44336",
        "Short Covering": "#2196f3",
        "Fresh Positions": "#9c27b0",
        "Position Unwinding": "#ff9800",
        "Mixed Activity": "#795548",
        "No Change": "#6b7280"
    }
    return colors.get(position, "#6b7280")

def calculate_pcr(put_value: float, call_value: float) -> float:
    """Calculate Put-Call Ratio"""
    return put_value / call_value if call_value != 0 else 0

def get_pcr_signal(pcr_value: float, metric_type: str = "OI") -> str:
    """Get PCR signal based on value and metric type"""
    if metric_type == "OI":
        if pcr_value > 1.2:
            return "Bearish"
        elif pcr_value < 0.8:
            return "Bullish"
        else:
            return "Neutral"
    else:  # Volume
        if pcr_value > 1.3:
            return "Bearish"
        elif pcr_value < 0.7:
            return "Bullish"
        else:
            return "Neutral"

def calculate_comprehensive_sentiment_score(table_data, bucket_summary, pcr_data, spot_price) -> dict:
    """Comprehensive multi-factor sentiment analysis with weighted scoring"""
    
    scores = {
        "price_action": 0,
        "open_interest": 0, 
        "fresh_activity": 0,
        "position_distribution": 0
    }
    
    # 1. PRICE ACTION ANALYSIS (25% weight)
    price_score = 0
    atm_strike = table_data.loc[table_data["Strike"].sub(spot_price).abs().idxmin(), "Strike"]
    strikes_above_spot = len(table_data[table_data["Strike"] > spot_price])
    strikes_below_spot = len(table_data[table_data["Strike"] < spot_price])
    
    if strikes_above_spot > strikes_below_spot:
        price_score += 20
    elif strikes_below_spot > strikes_above_spot:
        price_score -= 20
    
    max_pain_strike = table_data.loc[table_data["CE_OI"].add(table_data["PE_OI"]).idxmax(), "Strike"]
    price_vs_max_pain = (spot_price - max_pain_strike) / max_pain_strike * 100
    
    if price_vs_max_pain > 2:
        price_score -= 30
    elif price_vs_max_pain < -2:
        price_score += 30
        
    scores["price_action"] = max(-100, min(100, price_score))
    
    # 2. OPEN INTEREST ANALYSIS (30% weight)
    oi_score = 0
    oi_pcr = pcr_data['OVERALL_PCR_OI']
    
    if oi_pcr < 0.6:
        oi_score += 40
    elif oi_pcr < 0.8:
        oi_score += 20
    elif oi_pcr > 1.4:
        oi_score -= 40
    elif oi_pcr > 1.2:
        oi_score -= 20
    
    scores["open_interest"] = max(-100, min(100, oi_score))
    
    # 3. FRESH ACTIVITY ANALYSIS (25% weight)
    activity_score = 0
    chgoi_pcr = pcr_data['OVERALL_PCR_CHGOI']
    
    if chgoi_pcr > 2.0:
        activity_score += 50
    elif chgoi_pcr > 1.5:
        activity_score += 30
    elif chgoi_pcr < 0.3:
        activity_score -= 50
    elif chgoi_pcr < 0.6:
        activity_score -= 30
    
    scores["fresh_activity"] = max(-100, min(100, activity_score))
    
    # 4. POSITION DISTRIBUTION ANALYSIS (20% weight)
    position_score = 0
    ce_positions = table_data['CE_Position'].value_counts()
    pe_positions = table_data['PE_Position'].value_counts()
    
    bullish_ce = ce_positions.get("Long Build", 0) + ce_positions.get("Short Covering", 0)
    bullish_pe = pe_positions.get("Long Unwinding", 0) + pe_positions.get("Short Buildup", 0)
    bearish_ce = ce_positions.get("Short Buildup", 0) + ce_positions.get("Long Unwinding", 0)
    bearish_pe = pe_positions.get("Long Build", 0) + pe_positions.get("Short Covering", 0)
    
    total_strikes = len(table_data)
    net_bullish_activity = (bullish_ce - bearish_ce) + (bullish_pe - bearish_pe)
    position_bias_pct = (net_bullish_activity / total_strikes) * 100
    position_score = max(-100, min(100, position_bias_pct * 10))
    
    scores["position_distribution"] = position_score
    
    # Calculate weighted final score
    weights = {
        "price_action": 0.25,
        "open_interest": 0.30,
        "fresh_activity": 0.25, 
        "position_distribution": 0.20
    }
    
    final_score = sum(scores[key] * weights[key] for key in scores.keys())
    
    # Determine sentiment category and confidence
    if final_score >= 60:
        sentiment = "STRONG BULLISH"
        confidence = "HIGH"
    elif final_score >= 30:
        sentiment = "BULLISH"
        confidence = "HIGH"
    elif final_score >= 15:
        sentiment = "BULLISH BIAS"
        confidence = "MEDIUM"
    elif final_score <= -60:
        sentiment = "STRONG BEARISH"
        confidence = "HIGH" 
    elif final_score <= -30:
        sentiment = "BEARISH"
        confidence = "HIGH"
    elif final_score <= -15:
        sentiment = "BEARISH BIAS"
        confidence = "MEDIUM"
    else:
        sentiment = "NEUTRAL"
        confidence = "MEDIUM"
    
    return {
        "sentiment": sentiment,
        "confidence": confidence,
        "final_score": final_score,
        "component_scores": scores
    }

def get_time_to_expiry(expiry_date):
    """Calculate time to expiry in years"""
    try:
        expiry = datetime.strptime(expiry_date, "%Y-%m-%d")
        now = datetime.now()
        days_to_expiry = (expiry - now).days
        return max(days_to_expiry / 365.0, 1/365)
    except:
        return 1/365

# IST timezone for market operations
IST = pytz.timezone('Asia/Kolkata')

def get_ist_now():
    """Get current datetime in IST"""
    return datetime.now(IST)

def is_market_open(now=None):
    """Check if NSE market is open (IST timezone)"""
    if now is None:
        now = get_ist_now()
    elif now.tzinfo is None:
        now = IST.localize(now)
    elif now.tzinfo != IST:
        now = now.astimezone(IST)
    
    # NSE is closed on weekends
    if now.weekday() >= 5:
        return False
    
    market_open = time(9, 15)
    market_close = time(15, 30)
    current_time = now.time()
    return market_open <= current_time <= market_close

def setup_page():
    """Set up page configuration and CSS styles"""
    st.set_page_config(page_title="Enhanced Upstox F&O Option Chain", layout="wide")
    
    # Add responsive CSS
    st.markdown("""
    <style>
        @media (max-width: 640px) {
            .element-container {
                width: 100% !important;
                padding: 0 !important;
            }
            .stDataFrame {
                width: 100% !important;
                font-size: 12px !important;
            }
            .stDataFrame > div {
                overflow-x: auto !important;
            }
            .css-1xarl3l {
                font-size: 16px !important;
            }
        }
        .stDataFrame > div {
            max-width: 100% !important;
        }
        .dataframe td {
            min-width: 70px !important;
            white-space: nowrap !important;
        }
    </style>
    """, unsafe_allow_html=True)

def main():
    # Set wide layout for the entire app
    st.set_page_config(
        page_title="Enhanced Upstox F&O Option Chain Dashboard",
        layout="wide",
        initial_sidebar_state="expanded"
    )
    
    setup_page()
    
    # AUTO-REFRESH IMPLEMENTATION
    if 'auto_refresh_enabled' not in st.session_state:
        st.session_state.auto_refresh_enabled = True
    if 'refresh_counter' not in st.session_state:
        st.session_state.refresh_counter = 0
    
    # Show auto-refresh status at the top
    refresh_col1, refresh_col2, refresh_col3 = st.columns([2, 1, 1])
    with refresh_col1:
        if st.session_state.auto_refresh_enabled:
            st.success("🔄 **AUTO-REFRESH ON** - Updates every 30 seconds")
        else:
            st.warning("⏸ Auto-refresh paused")
    
    with refresh_col2:
        if st.session_state.auto_refresh_enabled:
            if st.button("⏸ Pause", key="pause_btn"):
                st.session_state.auto_refresh_enabled = False
                st.rerun()
        else:
            if st.button("▶ Resume", key="resume_btn"):
                st.session_state.auto_refresh_enabled = True
                st.rerun()
    
    with refresh_col3:
        if st.button("🔄 Refresh Now", key="refresh_now"):
            st.session_state.refresh_counter += 1
            st.rerun()
    
    # Implement auto-refresh using st_autorefresh library
    if st.session_state.auto_refresh_enabled and AUTORFR:
        # This will trigger a rerun every 30 seconds
        st_autorefresh(interval=30000, limit=None, key="page_autorefresh")
    
    st.title("Enhanced Upstox F&O Option Chain Dashboard")
    
    # Show data source indicator
    if st.session_state.get('use_database', False):
        st.success("🗄️ **Database Mode** - Background service provides continuous updates")
    else:
        st.warning("🌐 **API Mode** - Data fetched directly from Upstox (database not available)")
    st.markdown("Advanced options data analysis with Greeks and sentiment tracking")
    
    # Initialize session state with all required variables
    if 'upstox_api' not in st.session_state:
        st.session_state.upstox_api = UpstoxAPI()
    if 'token_data' not in st.session_state:
        st.session_state.token_data = None
    if 'selected_symbol' not in st.session_state:
        st.session_state.selected_symbol = "NIFTY"
    if 'selected_expiry' not in st.session_state:
        st.session_state.selected_expiry = None
    if 'auto_refresh_enabled' not in st.session_state:
        st.session_state.auto_refresh_enabled = False
    if 'last_data_update' not in st.session_state:
        st.session_state.last_data_update = None
    if 'option_chain_data' not in st.session_state:
        st.session_state.option_chain_data = None
    if 'access_token' not in st.session_state:
        st.session_state.access_token = None
    if 'db_manager' not in st.session_state and DB_AVAILABLE:
        try:
            st.session_state.db_manager = TimescaleDBManager()
            st.session_state.use_database = True
            st.sidebar.success("✅ Connected to database")
        except Exception as e:
            st.session_state.use_database = False
            st.session_state.db_manager = None
            st.sidebar.error(f"❌ Database connection failed: {e}")
    elif not DB_AVAILABLE:
        st.session_state.use_database = False
        st.session_state.db_manager = None
        st.sidebar.warning("⚠️ Database module not available. Using API mode.")
        
    # Get pre-configured developer credentials
    try:
        # Check if .streamlit/secrets.toml exists
        secrets_path = os.path.join(os.path.dirname(__file__), '.streamlit', 'secrets.toml')
        if not os.path.exists(secrets_path):
            st.error("secrets.toml file not found!")
            st.info(f"Expected location: {secrets_path}")
            st.info("Please create the file with your Upstox credentials")
            return
            
        credentials = get_credentials()
        if not credentials:
            st.error("Failed to load credentials from secrets.toml")
            st.info("""
            Your secrets.toml should look like this:
            ```toml
            [upstox]
            access_token="your_token"
            api_key="your_api_key"
            api_secret="your_secret"
            redirect_uri="your_uri"
            ```
            Make sure there are no spaces around the = signs
            """)
            return
            
        # Verify all required fields are present
        required_fields = ['access_token', 'api_key', 'api_secret', 'redirect_uri']
        missing_fields = [field for field in required_fields if not credentials.get(field)]
        if missing_fields:
            st.error(f"Missing required fields in secrets.toml: {', '.join(missing_fields)}")
            return
            
    except Exception as e:
        st.error(f"Error accessing credentials: {str(e)}")
        st.info("Please verify that your secrets.toml file is properly formatted")
        return
    
    # Set the pre-configured access token
    st.session_state.upstox_api.access_token = credentials['access_token']
    
    # Sidebar for API configuration
    with st.sidebar:
        st.header("API Configuration")
        st.info("Using pre-configured developer credentials")
        
        # Set credentials from the pre-configured values
        api_key = credentials['api_key']
        api_secret = credentials['api_secret']
        redirect_uri = credentials['redirect_uri']
        
        # Analysis settings
        st.subheader("Analysis Settings")
        itm_count = st.radio("ITM Strikes", [1, 2, 3, 5], index=2, key="itm_count_radio")
        risk_free_rate = st.number_input("Risk-free Rate (%)", value=5.84, min_value=0.0, max_value=15.0, step=0.1) / 100
        
        # Auto-refresh settings
        st.markdown("---")
        st.subheader("Real-time Data Settings")
        
        # Auto-refresh checkbox - Fixed to prevent page reload
        auto_refresh_enabled = st.checkbox(
            "Enable Auto-Refresh", 
            value=st.session_state.auto_refresh_enabled,
            key="auto_refresh_checkbox",
            help="Automatically refresh option chain data every 30 seconds during market hours"
        )
        
        # Update session state only if changed
        if auto_refresh_enabled != st.session_state.auto_refresh_enabled:
            st.session_state.auto_refresh_enabled = auto_refresh_enabled
        
        refresh_interval = 30  # Default value
        if st.session_state.auto_refresh_enabled:
            refresh_interval = st.slider("Refresh Interval (seconds)", 10, 60, 30)
            
            if is_market_open():
                st.success(f"Auto-refresh enabled - Market is OPEN")
                st.info(f"Refreshing every {refresh_interval}s")
            else:
                st.info("Auto-refresh paused - Market is CLOSED")
                st.write("Market hours: 9:15 AM - 3:30 PM (Mon-Fri)")
    
    # Token management
    st.sidebar.subheader("Token Status")
    
    if st.session_state.upstox_api.access_token:
        st.sidebar.success("✓ Connected to Upstox")
        
        if st.sidebar.button("Test Connection"):
            profile_data, error = st.session_state.upstox_api.get_profile()
            if profile_data:
                st.sidebar.success("✓ Connection is valid")
            else:
                st.sidebar.error("⚠️ Connection error: " + str(error))
            st.rerun()
    else:
        st.sidebar.warning("No Access Token")
    
    # Authorization flow
    if api_key and not st.session_state.upstox_api.access_token:
        auth_url = st.session_state.upstox_api.get_auth_url(api_key, redirect_uri)
        
        st.sidebar.markdown("**Get Authorization Code:**")
        st.sidebar.markdown(f"[Click to Authorize]({auth_url})")
        
        with st.sidebar.expander("Instructions"):
            st.markdown(f"""
            **Step by Step:**
            1. Click the authorization link above
            2. Login to your Upstox account
            3. You'll be redirected to: `{redirect_uri}?code=XXXXX`
            4. Copy the entire redirect URL and paste below
            """)
        
        redirect_url_input = st.sidebar.text_area(
            "Paste Complete Redirect URL",
            placeholder=f"{redirect_uri}?code=ABC123XYZ",
            height=80
        )
        
        auth_code = None
        if redirect_url_input:
            try:
                from urllib.parse import urlparse, parse_qs
                parsed_url = urlparse(redirect_url_input.strip())
                query_params = parse_qs(parsed_url.query)
                
                if 'code' in query_params:
                    auth_code = query_params['code'][0]
                    st.sidebar.success(f"Code found: {auth_code[:15]}...")
                else:
                    st.sidebar.error("No 'code' parameter found")
            except Exception as e:
                st.sidebar.error(f"URL parsing error: {str(e)}")
        
        with st.sidebar.expander("Manual Code Entry"):
            manual_code = st.text_input("Authorization Code", placeholder="Paste code manually if URL parsing fails")
            if manual_code:
                auth_code = manual_code.strip()
        
        if auth_code and st.sidebar.button("Get Access Token"):
            with st.spinner("Getting access token..."):
                success, result = st.session_state.upstox_api.get_access_token(
                    auth_code, api_key, api_secret, redirect_uri
                )
                if success:
                    st.sidebar.success("Access token obtained!")
                    st.session_state.token_data = result
                else:
                    st.sidebar.error("Failed to get access token")
                    st.sidebar.json(result)
    
    # Refresh token section
    if st.session_state.upstox_api.refresh_token and api_key and api_secret:
        if st.sidebar.button("Refresh Access Token"):
            with st.spinner("Refreshing token..."):
                success, result = st.session_state.upstox_api.refresh_access_token(
                    api_key, api_secret, st.session_state.upstox_api.refresh_token
                )
                if success:
                    st.sidebar.success("Token refreshed!")
                    st.session_state.token_data = result
                else:
                    st.sidebar.error("Failed to refresh token")
                    st.sidebar.json(result)
    
    # Main content area - Create tabs for different views
    if st.session_state.upstox_api.access_token:
        # Create tabs
        tab1, tab2, tab3 = st.tabs(["📈 Option Chain Analysis", "📊 Sentiment Dashboard", "📉 ITM Analysis"])
        
        with tab1:
            main_content_container = st.container()
            with main_content_container:
                # Auto-refresh implementation - FIXED: Only trigger refresh, don't duplicate UI
                if (AUTORFR and 
                    st.session_state.auto_refresh_enabled and 
                    is_market_open() and 
                    'selected_symbol' in st.session_state and 
                    st.session_state.selected_expiry):
                    
                    count = st_autorefresh(interval=refresh_interval * 1000, limit=None, key="data_refresh")
                    
                    # Auto-fetch only triggers data refresh, UI remains the same
                    if count > 0:
                        fo_instruments = get_fo_instruments()
                        instrument_key = fo_instruments.get(st.session_state.selected_symbol)
                        if instrument_key:
                            auto_fetch_option_chain(instrument_key, st.session_state.selected_symbol, 
                                                  st.session_state.selected_expiry, itm_count, risk_free_rate)
                
                # Show data source status
                if st.session_state.use_database:
                    st.success("✅ Production Mode: Reading from TimescaleDB (Background service active)")
                else:
                    st.info("ℹ️ Direct API Mode: Fetching data directly from Upstox API")
                
                # F&O Instrument Selection
                st.header("Select F&O Instrument")
            
                col1, col2, col3 = st.columns(3)
                
                with col1:
                    # Get F&O instruments
                    fo_instruments = get_fo_instruments()
                    
                    # Find current index
                    try:
                        current_index = list(fo_instruments.keys()).index(st.session_state.selected_symbol)
                    except ValueError:
                        current_index = 0
                    
                    # Check if we need to switch symbol (from Sentiment Dashboard button)
                    if 'switch_to_option_chain' in st.session_state and st.session_state.switch_to_option_chain:
                        if 'selected_symbol' in st.session_state:
                            try:
                                current_index = list(fo_instruments.keys()).index(st.session_state.selected_symbol)
                            except ValueError:
                                current_index = 0
                            st.session_state.switch_to_option_chain = False
                        else:
                            current_index = 0
                    else:
                        try:
                            current_index = list(fo_instruments.keys()).index(st.session_state.selected_symbol)
                        except ValueError:
                            current_index = 0
                    
                    selected_symbol = st.selectbox(
                        "Select Symbol", 
                        list(fo_instruments.keys()), 
                        index=current_index,
                        key="symbol_selectbox"
                    )
                    if selected_symbol != st.session_state.selected_symbol:
                        st.session_state.selected_symbol = selected_symbol
                    
                    instrument_key = fo_instruments[selected_symbol]
                
                with col2:
                    # Fetch available expiries from database first, then API
                    expiry_dates = []
                    
                    # Try database first
                    if st.session_state.use_database and st.session_state.db_manager:
                        try:
                            with st.session_state.db_manager.get_connection() as conn:
                                with conn.cursor() as cur:
                                    cur.execute("""
                                        SELECT DISTINCT expiry_date 
                                        FROM option_chain_data 
                                        WHERE symbol = %s
                                        ORDER BY expiry_date ASC
                                    """, (selected_symbol,))
                                    db_expiries = [row[0].strftime('%Y-%m-%d') for row in cur.fetchall()]
                                    if db_expiries:
                                        expiry_dates = db_expiries
                        except:
                            pass
                    
                    # Fall back to API if no database data
                    if not expiry_dates:
                        contracts_data, error = st.session_state.upstox_api.get_option_contracts(instrument_key)
                        if contracts_data and 'data' in contracts_data:
                            expiry_dates = sorted({c['expiry'] for c in contracts_data['data'] if 'expiry' in c})
                    
                    if expiry_dates:
                        # Find current expiry index
                        current_expiry_index = 0
                        if st.session_state.selected_expiry in expiry_dates:
                            current_expiry_index = expiry_dates.index(st.session_state.selected_expiry)
                        
                        selected_expiry = st.selectbox(
                            "Select Expiry", 
                            expiry_dates, 
                            index=current_expiry_index,
                            key="expiry_selectbox"
                        )
                        st.session_state.selected_expiry = selected_expiry
                    else:
                        st.warning("No expiry dates found. Try another symbol.")
                        selected_expiry = None
                
                with col3:
                    st.write("**Selected:**")
                    st.write(f"Symbol: {selected_symbol}")
                    st.write(f"Key: {instrument_key}")
                    st.write(f"Expiry: {selected_expiry}")
                    
                # Manual fetch/load button (always available)
                if selected_expiry:
                    col_fetch1, col_fetch2 = st.columns([1, 1])
                    
                    with col_fetch1:
                        button_label = "Load from Database" if st.session_state.use_database else "Get Option Chain"
                        if st.button(button_label, type="primary", key="manual_fetch"):
                            fetch_and_display_option_chain(instrument_key, selected_symbol, selected_expiry, itm_count, risk_free_rate)
                    
                    with col_fetch2:
                        if st.session_state.last_data_update:
                            data_source = "Database" if st.session_state.use_database else "API"
                            st.info(f"Last updated: {st.session_state.last_data_update} IST ({data_source})")
                    
                    # Always auto-load from database on each page render
                    if st.session_state.use_database:
                        data, timestamp = load_option_chain_from_db(selected_symbol, selected_expiry)
                        if data:
                            st.session_state.option_chain_data = data
                            if timestamp:
                                st.session_state.last_data_update = timestamp
                
                # FIXED: Display data in the same container - no separate placeholder needed
                if st.session_state.option_chain_data:
                    display_option_chain_dashboard(
                        st.session_state.option_chain_data,
                        selected_symbol,
                        selected_expiry,
                        itm_count,
                        risk_free_rate
                    )
        
        with tab2:
            # Sentiment Dashboard Tab
            if st.session_state.use_database and st.session_state.db_manager:
                if SENTIMENT_AVAILABLE:
                    display_sentiment_dashboard(st.session_state.db_manager)
                else:
                    st.error("⚠️ Sentiment dashboard module not available")
                    st.info("Please ensure sentiment_dashboard.py exists in the same directory")
            else:
                st.warning("⚠️ Sentiment Dashboard requires database connection")
                st.info("""
                The Sentiment Dashboard shows all symbols with extreme sentiment scores:
                - **Strong Bullish**: Sentiment score > 20
                - **Strong Bearish**: Sentiment score < -20
                
                Please ensure:
                1. Database is connected (TimescaleDB)
                2. Background service is running
                3. Data has been collected for multiple symbols
                """)
        
        with tab3:
            # ITM Analysis Tab
            if st.session_state.use_database and st.session_state.db_manager:
                try:
                    st.header("📉 ITM Call & Put Analysis")
                    
                    # Symbol, Expiry, ITM Count, and Time Period selection
                    col1, col2, col3, col4 = st.columns([2, 2, 1, 1])
                    
                    with col1:
                        # Get F&O instruments
                        fo_instruments = get_fo_instruments()
                        
                        # Find current index
                        try:
                            itm_symbol_index = list(fo_instruments.keys()).index(st.session_state.selected_symbol)
                        except ValueError:
                            itm_symbol_index = 0
                        
                        itm_symbol = st.selectbox(
                            "Select Symbol for ITM Analysis", 
                            list(fo_instruments.keys()), 
                            index=itm_symbol_index,
                            key="itm_symbol_selectbox"
                        )
                    
                    with col2:
                        # Get available expiries from database (faster than API call)
                        try:
                            with st.session_state.db_manager.get_connection() as conn:
                                with conn.cursor() as cur:
                                    cur.execute("""
                                        SELECT DISTINCT expiry_date 
                                        FROM itm_bucket_summaries 
                                        WHERE symbol = %s
                                        ORDER BY expiry_date
                                    """, (itm_symbol,))
                                    expiry_dates = [row[0] for row in cur.fetchall()]
                        except Exception as e:
                            st.error(f"Error fetching expiries: {str(e)}")
                            expiry_dates = []
                        
                        if expiry_dates:
                            # Find current expiry index
                            try:
                                itm_expiry_index = expiry_dates.index(st.session_state.selected_expiry) if st.session_state.selected_expiry in expiry_dates else 0
                            except (ValueError, AttributeError):
                                itm_expiry_index = 0
                            
                            itm_expiry = st.selectbox(
                                "Select Expiry for ITM Analysis", 
                                expiry_dates, 
                                index=itm_expiry_index,
                                key="itm_expiry_selectbox"
                            )
                        else:
                            st.warning(f"No ITM data found for {itm_symbol}. Data is collected during market hours.")
                            itm_expiry = None
                    
                    with col3:
                        # ITM strike count selection (1-5)
                        itm_count = st.selectbox("ITM Strikes", options=[1, 2, 3, 4, 5], index=0, key="itm_count_select")
                    
                    with col4:
                        # Time period selection - default to 48 hours to show previous day's data when market closed
                        hours_options = [4, 8, 24, 48, 72]
                        hours = st.selectbox("Look Back (hrs)", options=hours_options, index=2, key="itm_hours")
                    
                    # Display ITM analysis if expiry is selected
                    if itm_expiry:
                        display_itm_analysis(itm_symbol, itm_expiry, st.session_state.db_manager, itm_count=itm_count, hours=hours)
                    else:
                        st.info("Please select a valid expiry to view ITM analysis.")
                        
                except Exception as e:
                    st.error(f"Error loading ITM analysis: {str(e)}")
                    import traceback
                    with st.expander("Debug Info"):
                        st.write(traceback.format_exc())
            else:
                st.warning("⚠️ ITM Analysis requires database connection")
                st.info("""
                The ITM Analysis tab shows:
                - **ITM Call & Put Open Interest (OI)** over time
                - **ITM Call & Put Volume** over time
                - **ITM Call & Put Change in OI** over time
                
                **Select ITM Strike Count (1-5):**
                - 1 Strike: Only closest ITM strike to ATM
                - 2 Strikes: Two closest ITM strikes to ATM
                - 3 Strikes: Three closest ITM strikes to ATM
                - etc.
                
                ITM (In-The-Money) options are calculated based on spot price:
                - **ITM Calls**: Strikes below the spot price
                - **ITM Puts**: Strikes above the spot price
                
                Please ensure:
                1. Database is connected (TimescaleDB)
                2. Background service is running and calculating ITM summaries
                3. Sufficient historical data is available (at least 1 hour)
                """)
    
    else:
        st.error("Developer access token not available or has expired.")
        st.info("""
            Please configure your developer credentials in .streamlit/secrets.toml with this format:
            ```toml
            [upstox]
            access_token = "your_permanent_access_token"
            api_key = "your_api_key"
            api_secret = "your_api_secret"
            redirect_uri = "your_redirect_uri"
            ```
            To get a permanent access token:
            1. Run the app locally
            2. Use the Upstox developer portal
            3. Generate a permanent access token
            4. Add it to your secrets.toml
        """)
        st.warning("Contact the developer if you need access to this application.")
        
        st.markdown("""
            ### Setup Guide:
            
            1. **Authorization Process:**
               - Click the authorization link in sidebar
               - Login to Upstox
               - Copy the complete redirect URL
               - Paste it to auto-extract the code
            
            2. **Token Management:**
               - Access tokens expire after some time
               - Use refresh token to get new access tokens
            
            3. **Enhanced Features:**
               - Real-time option chain with Greeks
               - Advanced sentiment analysis
               - Position tracking and PCR analysis
               - Auto-refresh during market hours
               - Volatility skew and gamma exposure analysis
            """)

def get_fo_instruments():
    """Get F&O instruments list"""
    try:
        import requests
        import gzip
        import json
        from io import BytesIO

        url = "https://assets.upstox.com/market-quote/instruments/exchange/NSE.json.gz"
        response = requests.get(url)
        
        with gzip.GzipFile(fileobj=BytesIO(response.content)) as gz:
            data = json.load(gz)

        df = pd.DataFrame(data)
        fno_df = df[(df['segment'] == "NSE_FO") | (df['segment'] == "NSE_INDEX")]
        fno_stocks = [x for x in fno_df['name'].unique()]

        fo_instruments = {row['asset_symbol']: row['asset_key'] 
                        for _, row in fno_df.iterrows() 
                        if row['name'] in fno_stocks}

        # Add indices
        fo_instruments.update({
            "NIFTY": "NSE_INDEX|Nifty 50",
            "BANKNIFTY": "NSE_INDEX|Nifty Bank",
            "FINNIFTY": "NSE_INDEX|Nifty Fin Service",
            "MIDCPNIFTY": "NSE_INDEX|NIFTY MID SELECT",
            "SENSEX": "BSE_INDEX|SENSEX"
        })
        
        return fo_instruments
        
    except Exception as e:
        st.error(f"Failed to load instruments: {str(e)}")
        return {
            "NIFTY": "NSE_INDEX|Nifty 50",
            "BANKNIFTY": "NSE_INDEX|Nifty Bank"
        }

def load_option_chain_from_db(symbol, expiry):
    """Load option chain data directly from TimescaleDB"""
    try:
        if not st.session_state.use_database or not st.session_state.db_manager:
            return None, None
        
        # Use the database manager directly instead of API
        db_manager = st.session_state.db_manager
        data = db_manager.get_latest_option_chain(symbol, expiry)
        
        if data and len(data) > 0:
            # Get timestamp from the database
            timestamp_dt = db_manager.get_latest_timestamp(symbol, expiry)
            if timestamp_dt:
                timestamp = timestamp_dt.astimezone(IST).strftime('%H:%M:%S')
            else:
                timestamp = datetime.now(IST).strftime('%H:%M:%S')
            
            return data, timestamp
        
        return None, None
    except Exception as e:
        st.warning(f"Error loading from database: {e}")
        return None, None

def auto_fetch_option_chain(instrument_key, symbol, expiry, itm_count, risk_free_rate):
    """Auto fetch option chain when conditions are met - ALWAYS uses database when available"""
    # ALWAYS try database first - background service continuously updates it
    if st.session_state.use_database:
        data, timestamp = load_option_chain_from_db(symbol, expiry)
        if data:
            st.session_state.option_chain_data = data
            if timestamp:
                st.session_state.last_data_update = timestamp
            return
    
    # Only use API if database is not available (not connected)
    # Don't fetch from API if database is connected but has no data - let background service handle it
    if not st.session_state.use_database and st.session_state.upstox_api.access_token:
        # Fetch data silently without creating new UI elements
        option_data, error = st.session_state.upstox_api.get_pc_option_chain(instrument_key, expiry)
        
        if option_data and error is None and 'data' in option_data:
            st.session_state.option_chain_data = option_data['data']
            st.session_state.last_data_update = datetime.now().strftime('%H:%M:%S')
            # Note: UI will be updated automatically through the existing display logic

def fetch_and_display_option_chain(instrument_key, symbol, expiry, itm_count, risk_free_rate):
    """Fetch and display option chain data - FIXED: No separate placeholder needed"""
    # Try to load from database first
    if st.session_state.use_database:
        with st.spinner(f"Loading option chain for {symbol} from database..."):
            data, timestamp = load_option_chain_from_db(symbol, expiry)
            if data:
                st.session_state.option_chain_data = data
                if timestamp:
                    st.session_state.last_data_update = timestamp
                st.success(f"Data loaded from database (updated at {st.session_state.last_data_update} IST)")
                return
            else:
                # Database is available but no data found - don't fetch from API
                # Let background service handle it to ensure both tabs use same data source
                st.warning(f"⚠️ No data in database for {symbol} yet.")
                st.info("💡 Background service is continuously fetching data. Please wait a moment and try again.")
                st.info("💡 This ensures both Option Chain Analysis and Sentiment Dashboard use the same data source.")
                return
    
    # Only use API if database is not available (not connected)
    if not st.session_state.use_database:
        with st.spinner(f"Fetching option chain for {symbol} from API..."):
            option_data, error = st.session_state.upstox_api.get_pc_option_chain(
                instrument_key, expiry
            )
            
            if option_data and error is None and 'data' in option_data:
                st.session_state.option_chain_data = option_data['data']
                current_time = get_ist_now()
                st.session_state.last_data_update = format_ist_time(current_time)
                st.success(f"Data fetched successfully at {st.session_state.last_data_update} IST")
                st.warning("⚠️ Using API data. Sentiment Dashboard uses database data, so values may differ.")
                # UI will automatically update through the existing display logic
            else:
                st.error(f"Failed to fetch option chain: {error}")

def display_option_chain_dashboard(data, symbol, expiry, itm_count, risk_free_rate):
    """Main dashboard display function - Fixed to prevent blank rows"""
    try:
        if not isinstance(data, list) or len(data) == 0:
            st.warning("No option chain data available")
            return
        
        # Extract spot price - try multiple methods
        spot_price = 0
        
        # Method 1: Try to get from first strike's underlying_spot_price
        if data and len(data) > 0:
            spot_price = data[0].get('underlying_spot_price', 0)
        
        # Method 2: If from database, try to get from database query
        if spot_price == 0 and st.session_state.use_database and st.session_state.db_manager:
            try:
                # Get spot price from database for this symbol and expiry
                with st.session_state.db_manager.get_connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute("""
                            SELECT spot_price 
                            FROM option_chain_data 
                            WHERE symbol = %s AND expiry_date = %s 
                            AND spot_price > 0
                            ORDER BY timestamp DESC 
                            LIMIT 1
                        """, (symbol, expiry))
                        result = cur.fetchone()
                        if result and result[0] and result[0] > 0:
                            spot_price = float(result[0])
            except Exception as e:
                pass  # Continue to next method
        
        # Method 3: Use middle strike as approximation
        if spot_price == 0 and data and len(data) > 0:
            strikes = []
            for strike_data in data:
                strike = strike_data.get('strike_price', 0)
                if strike > 0:
                    strikes.append(strike)
            
            if strikes:
                strikes.sort()
                spot_price = strikes[len(strikes) // 2]  # Use middle strike
        
        # Method 4: Use first valid strike as last resort
        if spot_price == 0 and data and len(data) > 0:
            for strike_data in data:
                strike = strike_data.get('strike_price', 0)
                if strike > 0:
                    spot_price = strike
                    break
        
        if spot_price == 0:
            st.error("Unable to get spot price from data. Please try refreshing or check if data is available.")
            with st.expander("Debug: Data Structure"):
                st.json(data[0] if data else "No data")
            return
        
        # Calculate time to expiry
        time_to_expiry = get_time_to_expiry(expiry)
        
        # Display spot price banner
        st.markdown(
            f"""
        <div style="background-color:#0A71E2;padding:12px;border-radius:12px;text-align:center;margin-bottom:12px">
          <div style="color:#fff;font-size:24px;font-weight:700;">{symbol} Spot: ₹{spot_price}</div>
          <div style="color:#D8E9FF;font-size:16px;">Expiry: {expiry} | Time to Expiry: {time_to_expiry*365:.0f} days</div>
        </div>
        """,
            unsafe_allow_html=True,
        )
        
        # Process option chain data
        processed_data = process_option_chain_data(data, spot_price)
        
        if not processed_data:
            st.warning("No processed data available")
            return
        
        # Convert to DataFrame and clean data
        table = pd.DataFrame(processed_data)
        
        # Remove any rows with NaN or invalid Strike prices
        table = table.dropna(subset=['Strike'])
        table = table[table['Strike'] > 0]
        
        # Sort by strike and reset index
        table = table.sort_values('Strike').reset_index(drop=True)
        
        # Remove duplicate strikes (keep first occurrence)
        table = table.drop_duplicates(subset=["Strike"], keep='first')
        
        if len(table) == 0:
            st.warning("No valid option chain data after cleaning")
            return
        
        # Find ATM strike and filter data
        atm_strike = table.loc[table["Strike"].sub(spot_price).abs().idxmin(), "Strike"]
        
        below_atm = table[table["Strike"] < atm_strike].tail(itm_count)
        above_atm = table[table["Strike"] > atm_strike].head(itm_count)
        atm_row = table[table["Strike"] == atm_strike]
        
        # Combine tables ensuring no empty DataFrames
        filtered_parts = []
        if not below_atm.empty:
            filtered_parts.append(below_atm)
        if not atm_row.empty:
            filtered_parts.append(atm_row)
        if not above_atm.empty:
            filtered_parts.append(above_atm)
        
        if not filtered_parts:
            st.warning("No data available for selected ITM count")
            return
            
        filtered_table = pd.concat(filtered_parts, axis=0, ignore_index=True)
        filtered_table = filtered_table.sort_values('Strike').reset_index(drop=True)
        
        # Add PCR calculations
        filtered_table["PCR_Strike_OI"] = filtered_table.apply(lambda row: calculate_pcr(row["PE_OI"], row["CE_OI"]), axis=1)
        filtered_table["PCR_Volume"] = filtered_table.apply(lambda row: calculate_pcr(row["PE_Volume"], row["CE_Volume"]), axis=1)
        filtered_table["PCR_ChgOI"] = filtered_table.apply(lambda row: calculate_pcr(row["PE_ChgOI"], row["CE_ChgOI"]), axis=1)
        
        # Calculate GEX data once and store it
        gex_data = []
        for _, row in filtered_table.iterrows():
            ce_gex = row['CE_Gamma'] * row['CE_OI'] * 100 * (spot_price ** 2) * 0.01
            pe_gex = -row['PE_Gamma'] * row['PE_OI'] * 100 * (spot_price ** 2) * 0.01
            net_gex = ce_gex + pe_gex
            
            gex_data.append({
                'Strike': row['Strike'],
                'CE_GEX': ce_gex,
                'PE_GEX': pe_gex,
                'Net_GEX': net_gex,
                'Distance': abs(row['Strike'] - spot_price)
            })
            
        # Store in session state for reuse
        st.session_state.current_gex_data = gex_data
        
        # Create visualizations and analysis
        create_option_chain_visualization(filtered_table, spot_price, symbol)
        
        bucket_summary = calculate_bucket_summaries(filtered_table, atm_strike, spot_price)
        pcr_data = calculate_comprehensive_pcr(bucket_summary)
        
        # Get gamma blast signal first
        gamma_blast_info = None
        if 'current_gex_data' in st.session_state:
            try:
                gex_df = pd.DataFrame(st.session_state.current_gex_data)
                market_context = {'regime': calculate_market_regime(None, gex_df, filtered_table)}
                blast_signal, blast_direction, reasons, entry_signal, _ = detect_gamma_blast(
                    filtered_table, spot_price, gex_df, None, market_context
                )
                gamma_blast_info = {
                    'signal': blast_signal,
                    'direction': blast_direction,
                    'reasons': reasons,
                    'entry_signal': entry_signal
                }
            except Exception as e:
                st.error(f"Error getting gamma blast signal: {str(e)}")
        
        display_bucket_summaries(bucket_summary, pcr_data, gamma_blast_info)
        
        sentiment_analysis = calculate_comprehensive_sentiment_score(filtered_table, bucket_summary, pcr_data, spot_price)
        
        # Store sentiment score in database if available (so Sentiment Dashboard matches)
        if st.session_state.use_database and st.session_state.db_manager:
            try:
                st.session_state.db_manager.insert_sentiment_score(
                    symbol=symbol,
                    expiry_date=expiry,
                    sentiment_score=sentiment_analysis['final_score'],
                    sentiment=sentiment_analysis['sentiment'],
                    confidence=sentiment_analysis['confidence'],
                    spot_price=spot_price,
                    pcr_oi=pcr_data.get('OVERALL_PCR_OI'),
                    pcr_chgoi=pcr_data.get('OVERALL_PCR_CHGOI'),
                    pcr_volume=pcr_data.get('OVERALL_PCR_VOLUME')
                )
            except Exception as e:
                # Silently fail - don't interrupt the UI
                pass
        
        display_sentiment_analysis(sentiment_analysis, symbol)
        
        display_option_chain_table(filtered_table, atm_strike, spot_price)
        display_quick_stats(filtered_table, atm_strike)
        
        # Advanced analysis sections
        with st.expander("Volatility Skew Analysis", expanded=False):
            calculate_volatility_skew_analysis(filtered_table, spot_price)
        
        with st.expander("Gamma Exposure Analysis", expanded=False):
            if 'current_gex_data' in st.session_state:
                gex_df = pd.DataFrame(st.session_state.current_gex_data)
                calculate_gamma_exposure_analysis(filtered_table, spot_price, gex_df, symbol)
            else:
                st.warning("GEX data not available. Please refresh the page.")
        
        with st.expander("Custom Volatility Index", expanded=False):
            implement_vix_like_index(filtered_table, spot_price, time_to_expiry)
        
        with st.expander("Support & Resistance Levels", expanded=False):
            display_support_resistance_levels(filtered_table, spot_price)
        
        with st.expander("Put-Call Parity Analysis", expanded=False):
            calculate_put_call_parity_analysis(filtered_table, atm_strike)
        
    except Exception as e:
        st.error(f"Error processing option chain data: {str(e)}")
        with st.expander("Raw Data for Debugging"):
            st.json(data)

def process_option_chain_data(data, spot_price):
    """Process raw option chain data into structured format - Handles both API and Database formats"""
    processed_data = []
    
    for strike_data in data:
        strike_price = strike_data.get('strike_price', 0)
        
        # Skip if strike price is 0 or invalid
        if strike_price <= 0:
            continue
        
        # Detect data format: flattened (old API) vs nested (database/new API)
        is_nested = 'call_options' in strike_data and 'put_options' in strike_data
        
        if is_nested:
            # Database/New API format: nested structure
            call_data = strike_data.get('call_options', {})
            put_data = strike_data.get('put_options', {})
            
            call_market = call_data.get('market_data', {})
            call_greeks = call_data.get('option_greeks', {})
            put_market = put_data.get('market_data', {})
            put_greeks = put_data.get('option_greeks', {})
            
            # Extract CE (Call) data from nested structure
            ce_ltp = float(call_market.get('ltp', 0) or 0)
            ce_volume = int(call_market.get('volume', 0) or 0)
            ce_oi = int(call_market.get('oi', 0) or 0)
            ce_prev_oi = int(call_market.get('prev_oi', 0) or 0)
            ce_chg_oi = ce_oi - ce_prev_oi
            ce_close = float(call_market.get('close_price', 0) or 0)
            ce_change = ce_ltp - ce_close if ce_close > 0 else 0
            ce_iv = float(call_greeks.get('iv', 0) or 0)
            ce_delta = float(call_greeks.get('delta', 0) or 0)
            ce_gamma = float(call_greeks.get('gamma', 0) or 0)
            ce_theta = float(call_greeks.get('theta', 0) or 0)
            ce_vega = float(call_greeks.get('vega', 0) or 0)
            
            # Extract PE (Put) data from nested structure
            pe_ltp = float(put_market.get('ltp', 0) or 0)
            pe_volume = int(put_market.get('volume', 0) or 0)
            pe_oi = int(put_market.get('oi', 0) or 0)
            pe_prev_oi = int(put_market.get('prev_oi', 0) or 0)
            pe_chg_oi = pe_oi - pe_prev_oi
            pe_close = float(put_market.get('close_price', 0) or 0)
            pe_change = pe_ltp - pe_close if pe_close > 0 else 0
            pe_iv = float(put_greeks.get('iv', 0) or 0)
            pe_delta = float(put_greeks.get('delta', 0) or 0)
            pe_gamma = float(put_greeks.get('gamma', 0) or 0)
            pe_theta = float(put_greeks.get('theta', 0) or 0)
            pe_vega = float(put_greeks.get('vega', 0) or 0)
        else:
            # Old API format: flattened structure
            ce_ltp = strike_data.get('CE_LTP', 0) or 0
            ce_volume = strike_data.get('CE_Volume', 0) or 0
            ce_oi = strike_data.get('CE_OI', 0) or 0
            ce_chg_oi = strike_data.get('CE_ChgOI', 0) or 0
            ce_iv = strike_data.get('CE_IV', 0) or 0
            ce_delta = strike_data.get('CE_Delta', 0) or 0
            ce_gamma = strike_data.get('CE_Gamma', 0) or 0
            ce_theta = strike_data.get('CE_Theta', 0) or 0
            ce_vega = strike_data.get('CE_Vega', 0) or 0
            ce_change = strike_data.get('CE_Change', 0) or 0
            
            pe_ltp = strike_data.get('PE_LTP', 0) or 0
            pe_volume = strike_data.get('PE_Volume', 0) or 0
            pe_oi = strike_data.get('PE_OI', 0) or 0
            pe_chg_oi = strike_data.get('PE_ChgOI', 0) or 0
            pe_iv = strike_data.get('PE_IV', 0) or 0
            pe_delta = strike_data.get('PE_Delta', 0) or 0
            pe_gamma = strike_data.get('PE_Gamma', 0) or 0
            pe_theta = strike_data.get('PE_Theta', 0) or 0
            pe_vega = strike_data.get('PE_Vega', 0) or 0
            pe_change = strike_data.get('PE_Change', 0) or 0
        
        # Calculate position signals
        ce_position = get_position_signal(ce_ltp, ce_change, ce_chg_oi)
        pe_position = get_position_signal(pe_ltp, pe_change, pe_chg_oi)
        
        # Only add row if we have valid strike price
        processed_data.append({
            "Strike": strike_price,
            "CE_OI": ce_oi,
            "CE_LTP": ce_ltp,
            "CE_Change": ce_change,
            "CE_Volume": ce_volume,
            "CE_ChgOI": ce_chg_oi,
            "CE_IV": ce_iv,
            "CE_Delta": ce_delta,
            "CE_Gamma": ce_gamma,
            "CE_Theta": ce_theta,
            "CE_Vega": ce_vega,
            "CE_Position": ce_position,
            "PE_OI": pe_oi,
            "PE_LTP": pe_ltp,
            "PE_Change": pe_change,
            "PE_Volume": pe_volume,
            "PE_ChgOI": pe_chg_oi,
            "PE_IV": pe_iv,
            "PE_Delta": pe_delta,
            "PE_Gamma": pe_gamma,
            "PE_Theta": pe_theta,
            "PE_Vega": pe_vega,
            "PE_Position": pe_position,
        })
    
    return processed_data

# All the visualization and analysis functions from the original code
def create_option_chain_visualization(table, spot_price, symbol):
    """Create visualization for option chain data"""
    st.header("OI, ChgOI & Volume Distribution")
    
    # Set better default style
    plt.style.use('default')  # Reset to default style
    plt.rcParams.update({
        'figure.figsize': [16, 8],  # Adjusted for better fit in wide layout
        'figure.dpi': 100,
        'axes.grid': True,
        'grid.alpha': 0.3,
        'axes.labelsize': 12,
        'xtick.labelsize': 10,
        'ytick.labelsize': 10,
        'figure.autolayout': True  # Enable automatic layout adjustments
    })
    
    # Create figure with better spacing
    fig, ax1 = plt.subplots()
    
    indices = np.arange(len(table))
    bar_width = 0.2
    
    # Plot OI and ChgOI
    ax1.bar(indices - 0.2, table["CE_OI"], bar_width, color="#1f77b4", label="CE OI", alpha=0.7)
    ax1.bar(indices, table["PE_OI"], bar_width, color="#2ca02c", label="PE OI", alpha=0.7)
    ax1.bar(indices + 0.2, table["CE_ChgOI"], bar_width, color="#aec7e8", label="CE ChgOI", alpha=0.7)
    ax1.bar(indices + 0.4, table["PE_ChgOI"], bar_width, color="#98df8a", label="PE ChgOI", alpha=0.7)
    
    ax1.set_ylabel("OI / ChgOI")
    ax1.set_xticks(indices)
    ax1.set_xticklabels(table["Strike"], rotation=45)
    
    # Right axis for Volume
    ax2 = ax1.twinx()
    ax2.plot(indices, table["CE_Volume"], marker="o", color="#ff7f0e", label="CE Volume", linewidth=2)
    ax2.plot(indices, table["PE_Volume"], marker="o", color="#d62728", label="PE Volume", linewidth=2)
    ax2.set_ylabel("Volume")
    
    # Spot line
    spot_position = table.index[table["Strike"].sub(spot_price).abs().idxmin()]
    ax1.axvline(spot_position, color="red", linestyle="--", linewidth=2, label=f"Spot ₹{spot_price}")
    
    # Merge legends
    lines, labels = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines + lines2, labels + labels2, bbox_to_anchor=(1.05, 1), loc='upper left')
    
    ax1.set_title(f"{symbol} Option Chain Distribution")
    ax1.grid(True, alpha=0.3)
    plt.tight_layout()
    
    # Use full width container for the plot
    with st.container():
        # Add CSS to ensure full width
        st.markdown("""
            <style>
            .element-container {
                width: 100% !important;
                max-width: 100% !important;
            }
            .stPlotlyChart, .stplot {
                width: 100% !important;
                max-width: 100% !important;
            }
            </style>
        """, unsafe_allow_html=True)
        
        # Display plot in full width
        st.pyplot(fig, use_container_width=True)
    
    plt.close()

def calculate_bucket_summaries(table, atm_strike, spot_price):
    """Calculate ITM/OTM bucket summaries"""
    
    # Separate ITM and OTM
    ce_itm = table[table["Strike"] < atm_strike]  # CE ITM (below spot)
    ce_otm = table[table["Strike"] > atm_strike]  # CE OTM (above spot)
    pe_itm = table[table["Strike"] > atm_strike]  # PE ITM (above spot)
    pe_otm = table[table["Strike"] < atm_strike]  # PE OTM (below spot)
    
    def aggregate_bucket(df, side):
        if df.empty:
            return {"OI": 0, "ChgOI": 0, "Volume": 0, "IV": 0, "Delta": 0, "Gamma": 0, "Theta": 0, "Vega": 0}
        
        total_oi = df[f"{side}_OI"].sum()
        if total_oi == 0:
            return {"OI": 0, "ChgOI": 0, "Volume": 0, "IV": 0, "Delta": 0, "Gamma": 0, "Theta": 0, "Vega": 0}
        
        # Weight Greeks by OI
        weighted_delta = (df[f"{side}_Delta"] * df[f"{side}_OI"]).sum() / total_oi
        weighted_gamma = (df[f"{side}_Gamma"] * df[f"{side}_OI"]).sum() / total_oi
        weighted_theta = (df[f"{side}_Theta"] * df[f"{side}_OI"]).sum() / total_oi
        weighted_vega = (df[f"{side}_Vega"] * df[f"{side}_OI"]).sum() / total_oi
        
        return {
            "OI": total_oi,
            "ChgOI": df[f"{side}_ChgOI"].sum(),
            "Volume": df[f"{side}_Volume"].sum(),
            "IV": df[f"{side}_IV"].mean(),
            "Delta": weighted_delta,
            "Gamma": weighted_gamma,
            "Theta": weighted_theta,
            "Vega": weighted_vega,
        }
    
    return {
        "CE_ITM": aggregate_bucket(ce_itm, "CE"),
        "CE_OTM": aggregate_bucket(ce_otm, "CE"),
        "PE_ITM": aggregate_bucket(pe_itm, "PE"),
        "PE_OTM": aggregate_bucket(pe_otm, "PE"),
    }

def calculate_comprehensive_pcr(bucket_summary):
    """Calculate comprehensive PCR data"""
    return {
        "ITM_PCR_OI": calculate_pcr(bucket_summary["PE_ITM"]["OI"], bucket_summary["CE_ITM"]["OI"]),
        "OTM_PCR_OI": calculate_pcr(bucket_summary["PE_OTM"]["OI"], bucket_summary["CE_OTM"]["OI"]),
        "OVERALL_PCR_OI": calculate_pcr(
            bucket_summary["PE_ITM"]["OI"] + bucket_summary["PE_OTM"]["OI"],
            bucket_summary["CE_ITM"]["OI"] + bucket_summary["CE_OTM"]["OI"]
        ),
        "ITM_PCR_CHGOI": calculate_pcr(bucket_summary["PE_ITM"]["ChgOI"], bucket_summary["CE_ITM"]["ChgOI"]),
        "OTM_PCR_CHGOI": calculate_pcr(bucket_summary["PE_OTM"]["ChgOI"], bucket_summary["CE_OTM"]["ChgOI"]),
        "OVERALL_PCR_CHGOI": calculate_pcr(
            bucket_summary["PE_ITM"]["ChgOI"] + bucket_summary["PE_OTM"]["ChgOI"],
            bucket_summary["CE_ITM"]["ChgOI"] + bucket_summary["CE_OTM"]["ChgOI"]
        ),
        "ITM_PCR_VOLUME": calculate_pcr(bucket_summary["PE_ITM"]["Volume"], bucket_summary["CE_ITM"]["Volume"]),
        "OTM_PCR_VOLUME": calculate_pcr(bucket_summary["PE_OTM"]["Volume"], bucket_summary["CE_OTM"]["Volume"]),
        "OVERALL_PCR_VOLUME": calculate_pcr(
            bucket_summary["PE_ITM"]["Volume"] + bucket_summary["PE_OTM"]["Volume"],
            bucket_summary["CE_ITM"]["Volume"] + bucket_summary["CE_OTM"]["Volume"]
        ),
    }

# Utility functions for color coding
def get_change_color(value):
    """Return color based on value change"""
    if value > 0:
        return "#4caf50"  # Green
    elif value < 0:
        return "#f44336"  # Red
    else:
        return "#757575"  # Gray

def get_pcr_color(pcr_value):
    """Return color based on PCR value"""
    if pcr_value > 1.2:
        return "#f44336"  # Red - Bearish
    elif pcr_value < 0.8:
        return "#4caf50"  # Green - Bullish
    else:
        return "#ff9800"  # Orange - Neutral

def display_bucket_summaries(bucket_summary, pcr_data, gamma_blast_info=None):
    """Display bucket summaries with enhanced color coding and gamma blast signals"""
    st.subheader("Bucket Summaries with Greeks Analysis")
    
    left, middle, right = st.columns([1, 1, 1])
    
    def get_pcr_signal(pcr_value, type):
        if type == 'OI':
            if pcr_value > 1.2: return "Bearish"
            elif pcr_value < 0.8: return "Bullish"
            else: return "Neutral"
        return ""  # Default return for other types
    
    def display_bucket_stats(data, category, oi_color, chgoi_color):
        return f"""
        <div style="background: linear-gradient(90deg, {oi_color}15, transparent); padding: 10px; border-radius: 8px; border-left: 4px solid {oi_color}; margin-bottom: 10px;">
            <div style="color: {oi_color}; font-weight: bold;">OI: {format_number(data['OI'])}</div>
            <div style="color: {chgoi_color}; font-weight: bold;">ChgOI: {'+' if data['ChgOI'] >= 0 else ''}{format_number(data['ChgOI'])}</div>
            <div>Volume: {format_number(data['Volume'])}</div>
            <div style="font-size: 0.9em;">IV: {data['IV']:.2f}%</div>
            <div style="font-size: 0.9em;">Delta: {data['Delta']:.4f}</div>
            <div style="font-size: 0.8em; color: #666;">
                Gamma: {data['Gamma']:.4f} | Theta: {data['Theta']:.2f} | Vega: {data['Vega']:.4f}
            </div>
        </div>
        """
        
    # Display Gamma Blast Signal if available
    if gamma_blast_info and 'signal' in gamma_blast_info:
        signal_colors = {
            "Gamma Blast ENTRY SIGNAL - Upside": "#059669",
            "Gamma Blast ENTRY SIGNAL - Downside": "#dc2626",
            "Gamma Blast ENTRY SIGNAL - Bidirectional": "#7c3aed"
        }
        color = signal_colors.get(gamma_blast_info['signal'], "#6b7280")
        
        st.markdown(f"""
        <div style="background: linear-gradient(90deg, {color}15, transparent); 
             padding: 10px; border-radius: 8px; border-left: 4px solid {color}; 
             margin-bottom: 10px;">
            <div style="color: {color}; font-weight: bold;">
                {gamma_blast_info['signal']}
            </div>
            <div style="font-size: 0.9em;">
                Direction: {gamma_blast_info.get('direction', 'NEUTRAL')}
            </div>
        </div>
        """, unsafe_allow_html=True)

    def display_pcr_metric(label, value, signal=""):
        pcr_color = get_pcr_color(value)
        return f"""
        <div style="background: linear-gradient(90deg, {pcr_color}15, transparent); padding: 8px; border-radius: 6px; border-left: 3px solid {pcr_color}; margin-bottom: 8px;">
            <div style="font-weight: bold; margin-bottom: 4px;">{label}</div>
            <div style="color: {pcr_color}; font-weight: bold; font-size: 1.1em;">
                {value:.3f} {f'({signal})' if signal else ''}
            </div>
        </div>
        """
    
    with left:
        st.markdown("### Calls (CE)")
        
        st.markdown("**ITM (below spot)**")
        ce_itm_oi_color = get_change_color(bucket_summary['CE_ITM']['OI'])
        ce_itm_chgoi_color = get_change_color(bucket_summary['CE_ITM']['ChgOI'])
        st.markdown(display_bucket_stats(bucket_summary['CE_ITM'], "ITM", ce_itm_oi_color, ce_itm_chgoi_color), unsafe_allow_html=True)
        
        st.markdown("**OTM (above spot)**")
        ce_otm_oi_color = get_change_color(bucket_summary['CE_OTM']['OI'])
        ce_otm_chgoi_color = get_change_color(bucket_summary['CE_OTM']['ChgOI'])
        st.markdown(display_bucket_stats(bucket_summary['CE_OTM'], "OTM", ce_otm_oi_color, ce_otm_chgoi_color), unsafe_allow_html=True)
    
    with middle:
        st.markdown("### Puts (PE)")
        
        st.markdown("**ITM (above spot)**")
        pe_itm_oi_color = get_change_color(bucket_summary['PE_ITM']['OI'])
        pe_itm_chgoi_color = get_change_color(bucket_summary['PE_ITM']['ChgOI'])
        st.markdown(display_bucket_stats(bucket_summary['PE_ITM'], "ITM", pe_itm_oi_color, pe_itm_chgoi_color), unsafe_allow_html=True)
        
        st.markdown("**OTM (below spot)**")
        pe_otm_oi_color = get_change_color(bucket_summary['PE_OTM']['OI'])
        pe_otm_chgoi_color = get_change_color(bucket_summary['PE_OTM']['ChgOI'])
        st.markdown(display_bucket_stats(bucket_summary['PE_OTM'], "OTM", pe_otm_oi_color, pe_otm_chgoi_color), unsafe_allow_html=True)
    
    with right:
        st.markdown("### PCR Analysis")
        
        st.markdown("**Open Interest PCR**")
        st.markdown(display_pcr_metric(
            "Overall", 
            pcr_data['OVERALL_PCR_OI'],
            get_pcr_signal(pcr_data['OVERALL_PCR_OI'], 'OI')
        ), unsafe_allow_html=True)
        
        col1, col2 = st.columns(2)
        with col1:
            st.markdown(display_pcr_metric("ITM", pcr_data['ITM_PCR_OI']), unsafe_allow_html=True)
        with col2:
            st.markdown(display_pcr_metric("OTM", pcr_data['OTM_PCR_OI']), unsafe_allow_html=True)
        
        st.markdown("**Change in OI PCR**")
        st.markdown(display_pcr_metric("Overall", pcr_data['OVERALL_PCR_CHGOI']), unsafe_allow_html=True)
        
        col1, col2 = st.columns(2)
        with col1:
            st.markdown(display_pcr_metric("ITM", pcr_data['ITM_PCR_CHGOI']), unsafe_allow_html=True)
        with col2:
            st.markdown(display_pcr_metric("OTM", pcr_data['OTM_PCR_CHGOI']), unsafe_allow_html=True)
        
        st.markdown("**Volume PCR**")
        st.markdown(display_pcr_metric("Overall", pcr_data['OVERALL_PCR_VOLUME']), unsafe_allow_html=True)

def display_sentiment_analysis(sentiment_analysis, symbol):
    """Display comprehensive sentiment analysis"""
    st.markdown("---")
    st.subheader("Market Sentiment Analysis")
    
    # Sentiment colors
    sentiment_colors = {
        "STRONG BULLISH": "#4caf50",
        "BULLISH": "#8bc34a", 
        "BULLISH BIAS": "#cddc39",
        "NEUTRAL": "#6b7280",
        "BEARISH BIAS": "#ff9800",
        "BEARISH": "#ff5722",
        "STRONG BEARISH": "#f44336"
    }
    
    sentiment_color = sentiment_colors.get(sentiment_analysis["sentiment"], "#6b7280")
    
    # Main sentiment display
    st.markdown(f"""
    <div style="background: linear-gradient(135deg, {sentiment_color}15 0%, {sentiment_color}05 100%);
                border: 2px solid {sentiment_color};
                border-radius: 15px;
                padding: 20px;
                margin-bottom: 20px;">
        <div style="display: flex; align-items: center; justify-content: space-between;">
            <div>
                <h2 style="color: {sentiment_color}; margin: 0;">
                    {sentiment_analysis["sentiment"]}
                </h2>
                <p style="margin: 5px 0; color: {sentiment_color}; font-weight: 600;">
                    Confidence: {sentiment_analysis["confidence"]}
                </p>
            </div>
            <div style="text-align: center; padding: 15px; border-radius: 10px; 
                        background: #f0f0f0; border: 2px solid {sentiment_color};">
                <h3 style="color: {sentiment_color}; margin: 0;">
                    {sentiment_analysis["final_score"]:+.1f}
                </h3>
                <small style="color: #666; font-weight: 600;">Sentiment Score</small>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    # Component breakdown
    st.markdown("### Score Breakdown")
    for component, score in sentiment_analysis["component_scores"].items():
        component_name = component.replace('_', ' ').title()
        
        bar_color = "#4caf50" if score > 0 else "#f44336"
        bar_width = abs(score)
        
        st.markdown(f"""
        <div style="margin: 10px 0; padding: 10px; border-radius: 8px; background-color: #f8f9fa;">
            <div style="display: flex; justify-content: space-between; margin-bottom: 5px;">
                <strong>{component_name}</strong>
                <span style="font-weight: 600;">{score:+.1f}</span>
            </div>
            <div style="background-color: #e0e0e0; height: 6px; border-radius: 3px;">
                <div style="background-color: {bar_color}; height: 6px; border-radius: 3px; 
                           width: {bar_width}%; float: {'right' if score < 0 else 'left'};"></div>
            </div>
        </div>
        """, unsafe_allow_html=True)

def format_option_chain_number(x):
    """Format numbers in option chain table with K/M suffix"""
    if not isinstance(x, (int, float)):
        return x
    
    abs_x = abs(x)
    if abs_x >= 1_000_000:
        return f"{x/1_000_000:.2f}M"
    if abs_x >= 1_000:
        return f"{x/1_000:.2f}K"
    return f"{x:.2f}"

def highlight_option_position(val):
    """Return style for option position cells"""
    style_map = {
        'Long Build': ('c8e6c9', '1b5e20'),      # Light green
        'Short Buildup': ('ffcdd2', 'b71c1c'),   # Light red
        'Short Covering': ('bbdefb', '0d47a1'),   # Light blue
        'Long Unwinding': ('ffe0b2', 'e65100'),   # Light orange
    }
    
    if val in style_map:
        bg_color, text_color = style_map[val]
        return f'background-color: #{bg_color}; color: #{text_color}'
    return ''

def display_option_chain_table(table, atm_strike, spot_price):
    """Display option chain table with formatting - Fixed to prevent blank rows"""
    st.subheader("Option Chain Table")
    
    # Create a copy and ensure clean data
    display_df = table.copy()
    
    # Remove any remaining NaN or invalid rows
    display_df = display_df.dropna(subset=['Strike'])
    display_df = display_df[display_df['Strike'] > 0]
    
    if len(display_df) == 0:
        st.warning("No valid data to display in option chain table")
        return
    
    # Convert Strike to integer
    display_df['Strike'] = display_df['Strike'].astype(int)
    
    # Define available columns
    basic_columns = [
        # Call options (CE)
        'CE_OI', 'CE_LTP', 'CE_Change', 'CE_Volume', 'CE_ChgOI', 'CE_Position',
        # Strike price
        'Strike',
        # Put options (PE)
        'PE_Position', 'PE_ChgOI', 'PE_Volume', 'PE_Change', 'PE_LTP', 'PE_OI'
    ]
    
    greek_columns = [
        'CE_Delta', 'CE_Gamma', 'CE_Theta', 'CE_Vega',
        'PE_Delta', 'PE_Gamma', 'PE_Theta', 'PE_Vega'
    ]
    
    iv_columns = ['CE_IV', 'PE_IV']
    
    # Add column selection options in sidebar
    st.sidebar.markdown("### Column Selection")
    
    # IV Selection
    show_iv = st.sidebar.checkbox("Show IV", value=False)
    
    # Greeks Selection
    st.sidebar.markdown("#### Greek Columns")
    show_delta = st.sidebar.checkbox("Show Delta", value=False)
    show_gamma = st.sidebar.checkbox("Show Gamma", value=False)
    show_theta = st.sidebar.checkbox("Show Theta", value=False)
    show_vega = st.sidebar.checkbox("Show Vega", value=False)
    
    # Build column list based on selections
    columns = basic_columns.copy()
    ce_pos_idx = columns.index('CE_Position')
    pe_pos_idx = columns.index('PE_Position')
    
    # Add selected Greek columns
    greek_mapping = [
        (show_delta, ('CE_Delta', 'PE_Delta')),
        (show_gamma, ('CE_Gamma', 'PE_Gamma')),
        (show_theta, ('CE_Theta', 'PE_Theta')),
        (show_vega, ('CE_Vega', 'PE_Vega'))
    ]
    
    for show_greek, (ce_col, pe_col) in greek_mapping:
        if show_greek:
            columns.insert(ce_pos_idx + 1, ce_col)
            columns.insert(pe_pos_idx + 1, pe_col)
            ce_pos_idx += 1
            pe_pos_idx += 1
    
    if show_iv:
        # Insert IV columns after LTP columns
        ce_ltp_idx = columns.index('CE_LTP')
        pe_ltp_idx = columns.index('PE_LTP')
        columns.insert(ce_ltp_idx + 1, 'CE_IV')
        columns.insert(pe_ltp_idx + 1, 'PE_IV')
    
    # Select and reorder columns - ensure all columns exist
    available_columns = [col for col in columns if col in display_df.columns]
    display_df = display_df[available_columns]
    
    # Define numeric column groups
    oi_volume_cols = ['CE_OI', 'PE_OI', 'CE_Volume', 'PE_Volume']
    price_cols = ['CE_LTP', 'PE_LTP']
    change_cols = ['CE_Change', 'PE_Change']
    chgoi_cols = ['CE_ChgOI', 'PE_ChgOI']
    
    # Build Greek columns list based on selections
    greek_cols = []
    if show_delta:
        greek_cols.extend(['CE_Delta', 'PE_Delta'])
    if show_gamma:
        greek_cols.extend(['CE_Gamma', 'PE_Gamma'])
    if show_theta:
        greek_cols.extend(['CE_Theta', 'PE_Theta'])
    if show_vega:
        greek_cols.extend(['CE_Vega', 'PE_Vega'])
    
    iv_cols = ['CE_IV', 'PE_IV'] if show_iv else []
    
    def format_number(x):
        """Format regular numbers with K/M suffix"""
        if not isinstance(x, (int, float)) or pd.isna(x):
            return "0"
        if abs(x) >= 1_000_000:
            return f"{x/1_000_000:.2f}M"
        if abs(x) >= 1_000:
            return f"{x/1_000:.2f}K"
        return f"{x:.2f}"
    
    def format_chgoi(x):
        """Format Change in OI numbers with K/M suffix"""
        if not isinstance(x, (int, float)) or pd.isna(x):
            return "0"
        formatted = format_number(abs(x))
        return f"+{formatted}" if x > 0 else f"-{formatted}"
    
    def format_greek_value(x):
        """Format Greek values with high precision"""
        if not isinstance(x, (int, float)) or pd.isna(x):
            return "0.0000"
        return f"{x:.4f}"
    
    def format_iv_value(x):
        """Format IV values as percentage"""
        if not isinstance(x, (int, float)) or pd.isna(x):
            return "0.00"
        return f"{x:.2f}"
    
    # Format numeric columns based on type
    for col in display_df.columns:
        if col in oi_volume_cols or col in price_cols:
            display_df[col] = display_df[col].apply(format_number)
        elif col in change_cols:
            display_df[col] = display_df[col].apply(lambda x: f"+{x:.2f}" if pd.notna(x) and x > 0 else f"{x:.2f}" if pd.notna(x) else "0.00")
        elif col in chgoi_cols:
            display_df[col] = display_df[col].apply(format_chgoi)
        elif col in greek_cols:
            display_df[col] = display_df[col].apply(format_greek_value)
        elif col in iv_cols:
            display_df[col] = display_df[col].apply(format_iv_value)
    
    # Define table styles
    table_styles = [{
        'selector': 'th',
        'props': [
            ('font-size', '12px'),
            ('text-align', 'center'),
            ('background-color', '#f5f5f5'),
            ('color', '#333'),
            ('font-weight', 'bold'),
            ('padding', '5px'),
            ('border', '1px solid #e0e0e0')
        ]
    }, {
        'selector': 'td',
        'props': [('border', '1px solid #e0e0e0')]
    }]

    # Cell properties
    cell_props = {
        'font-size': '12px',
        'text-align': 'right',
        'padding': '5px',
        'border': '1px solid #e0e0e0'
    }
    
    def highlight_atm(row):
        """Highlight ATM row"""
        if row['Strike'] == atm_strike:
            return ['background-color: #fff9c4'] * len(row)  # Light yellow
        return [''] * len(row)
    
    # Style the dataframe
    styled_df = (display_df.style
        # Color code changes
        .applymap(
            lambda x: ('color: #4caf50' if isinstance(x, str) and x.startswith('+') else 
                      'color: #f44336' if isinstance(x, str) and x.startswith('-') else ''),
            subset=[col for col in change_cols if col in display_df.columns]
        )
        # Highlight positions
        .applymap(highlight_option_position, subset=[col for col in ['CE_Position', 'PE_Position'] if col in display_df.columns])
        # Highlight ATM strike
        .apply(highlight_atm, axis=1)
        # Alternate row colors for non-ATM rows
        .apply(
            lambda x: [
                'background-color: #e3f2fd' if x.name % 2 == 0 and x['Strike'] != atm_strike 
                else '' for i in x
            ], 
            axis=1
        )
        # Apply cell properties
        .set_properties(**cell_props)
        # Apply table styles
        .set_table_styles(table_styles)
    )
    
    # Get the clean DataFrame and create fresh styling
    display_df = display_df[display_df['Strike'].notna()]  # Remove rows with NaN Strike
    display_df = display_df.loc[~(display_df == '').all(axis=1)]  # Remove completely empty rows
    
    # Create fresh styling for the cleaned DataFrame
    styled_df = (display_df.style
        # Color code changes
        .applymap(
            lambda x: ('color: #4caf50' if isinstance(x, str) and x.startswith('+') else 
                      'color: #f44336' if isinstance(x, str) and x.startswith('-') else ''),
            subset=[col for col in change_cols if col in display_df.columns]
        )
        # Highlight positions
        .applymap(highlight_option_position, subset=[col for col in ['CE_Position', 'PE_Position'] if col in display_df.columns])
        # Highlight ATM strike
        .apply(highlight_atm, axis=1)
        # Alternate row colors for non-ATM rows
        .apply(
            lambda x: [
                'background-color: #e3f2fd' if x.name % 2 == 0 and x['Strike'] != atm_strike 
                else '' for i in x
            ], 
            axis=1
        )
        # Apply cell properties
        .set_properties(**cell_props)
        # Apply table styles
        .set_table_styles(table_styles)
    )
    
    # Display the table with fixed height to avoid empty space
    actual_height = min(600, len(display_df) * 35 + 50)  # 35px per row + 50px buffer
    st.dataframe(styled_df, use_container_width=True, height=actual_height)

def display_quick_stats(table, atm_strike):
    """Display quick statistics"""
    st.markdown("---")
    st.subheader("Quick Stats")
    
    col1, col2, col3, col4, col5 = st.columns(5)
    
    with col1:
        st.metric("Total CE OI", format_number(table["CE_OI"].sum()))
        
    with col2:
        st.metric("Total PE OI", format_number(table["PE_OI"].sum()))
        
    with col3:
        st.metric("Total CE Volume", format_number(table["CE_Volume"].sum()))
        
    with col4:
        st.metric("Total PE Volume", format_number(table["PE_Volume"].sum()))
        
    with col5:
        st.metric("ATM Strike", f"₹{atm_strike:,.0f}")

def calculate_volatility_skew_analysis(table, spot_price):
    """Fixed Volatility Skew Analysis"""
    st.subheader("Volatility Skew Analysis")
    
    # Find ATM strike
    atm_strike = table.loc[table["Strike"].sub(spot_price).abs().idxmin(), "Strike"]
    atm_iv = table.loc[table["Strike"] == atm_strike, ["CE_IV", "PE_IV"]].mean().mean()
    
    # Calculate skew metrics
    skew_data = []
    
    for _, row in table.iterrows():
        strike = row['Strike']
        ce_iv = row['CE_IV']
        pe_iv = row['PE_IV']
        
        # Calculate moneyness
        moneyness = spot_price / strike
        
        # Calculate skew relative to ATM
        ce_skew = ce_iv - atm_iv
        pe_skew = pe_iv - atm_iv
        
        # Classify by moneyness
        if moneyness > 1.05:
            category = "Deep ITM"
        elif moneyness > 1.02:
            category = "ITM"
        elif 0.98 <= moneyness <= 1.02:
            category = "ATM"
        elif moneyness > 0.95:
            category = "OTM"
        else:
            category = "Deep OTM"
        
        skew_data.append({
            'Strike': strike,
            'Moneyness': moneyness,
            'CE_IV': ce_iv,
            'PE_IV': pe_iv,
            'CE_Skew': ce_skew,
            'PE_Skew': pe_skew,
            'Category': category
        })
    
    skew_df = pd.DataFrame(skew_data)
    
    # Calculate skew metrics
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        # Risk Reversal
        otm_put_iv = skew_df[skew_df['Moneyness'] < 1]['PE_IV'].mean()
        otm_call_iv = skew_df[skew_df['Moneyness'] > 1]['CE_IV'].mean()
        risk_reversal = otm_put_iv - otm_call_iv
        st.metric("Risk Reversal", f"{risk_reversal:+.2f}%")
    
    with col2:
        # Butterfly
        otm_avg_iv = skew_df[skew_df['Category'] == 'OTM'][['CE_IV', 'PE_IV']].mean().mean()
        butterfly = atm_iv - otm_avg_iv
        st.metric("Butterfly", f"{butterfly:+.2f}%")
    
    with col3:
        # CE Skew slope
        if len(skew_df) > 1:
            ce_skew_slope = np.corrcoef(skew_df['Moneyness'], skew_df['CE_IV'])[0, 1]
            st.metric("CE Skew Slope", f"{ce_skew_slope:.3f}")
        else:
            st.metric("CE Skew Slope", "N/A")
    
    with col4:
        # PE Skew slope
        if len(skew_df) > 1:
            pe_skew_slope = np.corrcoef(skew_df['Moneyness'], skew_df['PE_IV'])[0, 1]
            st.metric("PE Skew Slope", f"{pe_skew_slope:.3f}")
        else:
            st.metric("PE Skew Slope", "N/A")
    
    # Visualization
    if len(skew_df) > 1:
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 6))
        
        # IV Smile/Skew
        ax1.plot(skew_df['Strike'], skew_df['CE_IV'], 'g-o', label='Call IV', linewidth=2, markersize=4)
        ax1.plot(skew_df['Strike'], skew_df['PE_IV'], 'r-o', label='Put IV', linewidth=2, markersize=4)
        ax1.axvline(spot_price, color='blue', linestyle='--', alpha=0.7, label=f'Spot: ₹{spot_price}')
        ax1.axvline(atm_strike, color='orange', linestyle='--', alpha=0.7, label=f'ATM: ₹{atm_strike}')
        ax1.set_xlabel('Strike Price')
        ax1.set_ylabel('Implied Volatility (%)')
        ax1.set_title('Volatility Smile')
        ax1.legend()
        ax1.grid(True, alpha=0.3)
        
        # Moneyness vs IV
        ax2.scatter(skew_df['Moneyness'], skew_df['CE_IV'], alpha=0.7, color='green', label='Call IV', s=60)
        ax2.scatter(skew_df['Moneyness'], skew_df['PE_IV'], alpha=0.7, color='red', label='Put IV', s=60)
        ax2.axvline(x=1.0, color='blue', linestyle='--', alpha=0.7, label='ATM')
        ax2.set_xlabel('Moneyness (S/K)')
        ax2.set_ylabel('Implied Volatility (%)')
        ax2.set_title('IV vs Moneyness')
        ax2.legend()
        ax2.grid(True, alpha=0.3)
        
        plt.tight_layout()
        st.pyplot(fig)
        plt.close()
        
        # Skew interpretation
        st.markdown("### Skew Analysis")
        
        if risk_reversal > 2:
            st.info("Strong Put Skew: Market expects downside volatility")
        elif risk_reversal < -2:
            st.info("Call Skew: Market expects upside volatility")
        else:
            st.info("Balanced Skew: No strong directional bias")

def display_gamma_blast_analysis(table, spot_price, gex_df):
    """Display gamma blast analysis with enhanced visualization"""
    try:
        # Calculate market context
        market_context = {
            'regime': calculate_market_regime(None, gex_df, table)
        }
        
        # Call the dynamic function with market context
        blast_signal, blast_direction, reasons, entry_signal, is_post_1_30_pm = detect_gamma_blast(
            table, spot_price, gex_df, None, market_context
        )
    except Exception as e:
        st.error(f"Error in gamma blast detection: {str(e)}")
        return "No Blast", None, [], False, False
    
    # Rest of your existing display code remains the same...
    st.subheader("🎯 Gamma Blast Detection System")
    
    # Your existing visualization code continues here...
    signal_colors = {
        "No Blast": "#6b7280",
        "Gamma Blast Watch": "#f59e0b", 
        "Gamma Blast Setup - Upside": "#10b981",
        "Gamma Blast Setup - Downside": "#ef4444",
        "Gamma Blast Setup - Bidirectional": "#8b5cf6",
        "Gamma Compression": "#06b6d4",
        "Gamma Blast ENTRY SIGNAL - Upside": "#059669",
        "Gamma Blast ENTRY SIGNAL - Downside": "#dc2626",
        "Gamma Blast ENTRY SIGNAL - Bidirectional": "#7c3aed"
    }
    
    signal_color = signal_colors.get(blast_signal, "#6b7280")
    
    # Display main signal
    st.markdown(f"""
    <div style="background: linear-gradient(135deg, {signal_color}15 0%, {signal_color}05 100%);
                border: 2px solid {signal_color};
                border-radius: 12px;
                padding: 20px;
                margin-bottom: 15px;">
        <h3 style="color: {signal_color}; margin: 0; text-align: center;">
            {blast_signal}
        </h3>
        {f'<p style="text-align: center; margin: 5px 0; font-weight: 600;">Direction: {blast_direction}</p>' if blast_direction else ''}
    </div>
    """, unsafe_allow_html=True)
    
    # Display reasons
    if reasons:
        st.markdown("**Analysis Factors:**")
        for reason in reasons:
            st.markdown(f"• {reason}")
    
    return blast_signal, blast_direction, reasons, entry_signal, is_post_1_30_pm


# Update the main gamma exposure analysis function
def calculate_gamma_exposure_analysis(table, spot_price, gex_df=None, symbol=None):
    """Calculate or display Gamma Exposure and GEX levels with enhanced blast detection"""
    st.subheader("Gamma Exposure Analysis")
    
    # Calculate GEX if not provided
    if gex_df is None:
        gex_data = []
        for _, row in table.iterrows():
            strike = row['Strike']
            ce_gex = row['CE_Gamma'] * row['CE_OI'] * 100 * (spot_price ** 2) * 0.01
            pe_gex = -row['PE_Gamma'] * row['PE_OI'] * 100 * (spot_price ** 2) * 0.01  # Negative for puts
            net_gex = ce_gex + pe_gex
            gex_data.append({
                'Strike': strike,
                'CE_GEX': ce_gex,
                'PE_GEX': pe_gex,
                'Net_GEX': net_gex,
                'Distance': abs(strike - spot_price)
            })
        gex_df = pd.DataFrame(gex_data)
    
    # Calculate total positive and negative GEX
    total_positive_gex = gex_df[gex_df['Net_GEX'] > 0]['Net_GEX'].sum()
    total_negative_gex = abs(gex_df[gex_df['Net_GEX'] < 0]['Net_GEX'].sum())
    
    # Find zero gamma level
    zero_gamma_strike = None
    if len(gex_df) > 0:
        min_gex_idx = gex_df['Net_GEX'].abs().idxmin()
        zero_gamma_strike = gex_df.loc[min_gex_idx, 'Strike']
    
    # Display basic metrics in a 3-column layout
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric("Total Positive GEX", format_number(total_positive_gex))
    
    with col2:
        st.metric("Total Negative GEX", format_number(total_negative_gex))
    
    with col3:
        net_market_gex = total_positive_gex - total_negative_gex
        st.metric("Net Market GEX", format_number(net_market_gex))
        
    # Display zero gamma level
    if zero_gamma_strike:
        st.metric("Zero Gamma Level", f"₹{zero_gamma_strike:,.2f}")
    
    # GEX Chart
    if len(gex_df) > 0:
        fig, ax = plt.subplots(figsize=(14, 8))
        
        colors = ['red' if gex < 0 else 'green' for gex in gex_df['Net_GEX']]
        
        ax.bar(gex_df['Strike'], gex_df['Net_GEX'], color=colors, alpha=0.7, width=25)
        ax.axhline(y=0, color='black', linestyle='-', alpha=0.5)
        ax.axvline(x=spot_price, color='blue', linestyle='--', linewidth=2, label=f'Spot: ₹{spot_price}')
        
        if zero_gamma_strike:
            ax.axvline(x=zero_gamma_strike, color='orange', linestyle='--', linewidth=2, 
                      label=f'Zero Gamma: ₹{zero_gamma_strike}')
        
        ax.set_xlabel('Strike Price')
        ax.set_ylabel('Gamma Exposure (₹ Millions)')
        ax.set_title('Gamma Exposure by Strike')
        ax.legend()
        ax.grid(True, alpha=0.3)
        
        plt.xticks(rotation=45)
        plt.tight_layout()
        st.pyplot(fig)
        plt.close()
        
        # Market implications
        st.markdown("### Gamma Exposure Implications")
        
        if net_market_gex > 0:
            st.success("Positive Net GEX: Market makers will sell into rallies and buy dips (stabilizing)")
        else:
            st.warning("Negative Net GEX: Market makers will buy rallies and sell dips (destabilizing)")
    
    try:
        # Enhanced Gamma Blast Detection with error handling
        blast_signal, blast_direction, reasons, entry_signal, is_post_1_30_pm = display_gamma_blast_analysis(table, spot_price, gex_df)
    except Exception as e:
        st.error(f"Could not complete gamma blast analysis: {str(e)}")
    
    # Display leading indicators with real-time data
    try:
        display_gamma_leading_indicators(gex_df, spot_price, table, symbol)
    except Exception as e:
        st.info("Leading indicators: Real-time calculation in progress...")
    
    return gex_df


def display_gamma_leading_indicators(gex_df=None, spot_price=None, table=None, symbol=None):
    """Display gamma leading indicators from real-time data or database"""
    from database import TimescaleDBManager
    import pandas as pd
    from datetime import datetime
    import pytz
    
    try:
        db = TimescaleDBManager()
        ist = pytz.timezone('Asia/Kolkata')
        
        # Try to get current real-time data first
        use_realtime = False
        if gex_df is not None and len(gex_df) > 0 and spot_price is not None:
            use_realtime = True
        
        if use_realtime:
            # Use real-time data from current market
            # Get latest indicators from database (if available) - force fresh query
            with db.get_connection() as conn:
                with conn.cursor() as cur:
                    # Get the most recent entry for this symbol
                    cur.execute("""
                    SELECT gamma_blast_probability, confidence_level, predicted_direction, time_to_blast_minutes,
                           iv_velocity, iv_percentile, implied_move,
                           oi_acceleration, oi_velocity,
                           gamma_concentration, gamma_gradient, atm_gamma,
                           delta_ladder_imbalance, delta_skew, volatility_regime,
                           timestamp
                    FROM gamma_exposure_history 
                    WHERE symbol = %s
                    ORDER BY timestamp DESC 
                    LIMIT 1
                    """, (symbol,))
                    db_result = cur.fetchone()
            
            # Calculate real-time GEX metrics
            atm_strike = spot_price
            zero_gamma_strike = None
            if len(gex_df) > 0:
                min_gex_idx = gex_df['Net_GEX'].abs().idxmin()
                zero_gamma_strike = gex_df.loc[min_gex_idx, 'Strike']
            else:
                zero_gamma_strike = spot_price
            
            net_gex = gex_df['Net_GEX'].sum() if 'Net_GEX' in gex_df.columns else 0
            
            # Use database indicators if available, otherwise show realtime GEX only
            if db_result:
                prob, confidence, direction, time_to_blast, \
                iv_vel, iv_pct, impl_move, \
                oi_accel, oi_vel, \
                gamma_conc, gamma_grad, atm_gamma, \
                delta_imb, delta_skew, vol_regime, last_update_time = db_result
                
                # Show last update time for transparency
                time_diff = datetime.now(ist) - last_update_time.astimezone(ist)
                update_seconds = int(time_diff.total_seconds())
            else:
                # Fall back to calculated values
                prob, confidence, direction, time_to_blast = 0.5, "MEDIUM", "NEUTRAL", 15
                iv_vel, iv_pct, impl_move = 0, 0.5, 0
                oi_accel, oi_vel = 0, 0
                gamma_conc, gamma_grad, atm_gamma = 0, 0, 0
                delta_imb, delta_skew, vol_regime = 0, 0, "NORMAL"
                update_seconds = 0
            
            is_realtime = True
        else:
            # Fallback to database historical data for this symbol
            with db.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                    SELECT symbol, expiry_date, timestamp, 
                           gamma_blast_probability, confidence_level, predicted_direction, time_to_blast_minutes,
                           iv_velocity, iv_percentile, implied_move,
                           oi_acceleration, oi_velocity,
                           gamma_concentration, gamma_gradient, atm_gamma,
                           delta_ladder_imbalance, delta_skew, volatility_regime,
                           atm_strike, zero_gamma_level, net_gex
                    FROM gamma_exposure_history 
                    WHERE symbol = %s
                    ORDER BY timestamp DESC 
                    LIMIT 1
                    """, (symbol,))
                    result = cur.fetchone()
            
            if not result:
                st.info("⏳ Leading indicators calculating... (will update every 5 minutes)")
                return
            
            atm_strike, zero_gamma_strike, net_gex = result[-3], result[-2], result[-1]
            prob, confidence, direction, time_to_blast = result[3:7]
            iv_vel, iv_pct, impl_move = result[7:10]
            oi_accel, oi_vel = result[10:12]
            gamma_conc, gamma_grad, atm_gamma = result[12:15]
            delta_imb, delta_skew, vol_regime = result[15:18]
            is_realtime = False
        
        st.markdown("---")
        
        # Show last update time for transparency  
        update_info_col1, update_info_col2 = st.columns([3, 1])
        with update_info_col1:
            if is_realtime and 'update_seconds' in locals():
                if update_seconds < 60:
                    st.caption(f"📡 Last Updated: {update_seconds}s ago")
                else:
                    st.caption(f"📡 Last Updated: {update_seconds // 60}m {update_seconds % 60}s ago")
            else:
                st.caption("📡 Using cached data")
        
        with update_info_col2:
            if st.button("🔄 Force Refresh", key="force_refresh_gamma"):
                st.rerun()
        
        st.subheader("🎯 Gamma Blast Probability Forecast" + (" [REAL-TIME]" if is_realtime else " [Last Updated]"))
        
        # Main probability gauge
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            prob_pct = float(prob) * 100
            
            # Color based on probability
            if prob > 0.85:
                color = "🔴"
            elif prob > 0.7:
                color = "🟠"
            elif prob > 0.5:
                color = "🟡"
            else:
                color = "🟢"
            
            st.metric(
                f"{color} Blast Probability",
                f"{prob_pct:.1f}%",
                delta=None
            )
        
        with col2:
            confidence_icon = {
                'VERY_HIGH': '🔥',
                'HIGH': '⚠️',
                'MEDIUM': '⏳',
                'LOW': '😴'
            }.get(str(confidence), '?')
            st.metric("Confidence Level", f"{confidence_icon} {confidence}")
        
        with col3:
            direction_icon = {
                'UPSIDE': '📈',
                'DOWNSIDE': '📉',
                'BIDIRECTIONAL': '↕️',
                'NEUTRAL': '➡️'
            }.get(str(direction), '?')
            st.metric("Predicted Direction", f"{direction_icon} {direction}")
        
        with col4:
            st.metric("Time to Blast", f"{int(time_to_blast)}m", delta=None)
        
        # Display detailed metrics
        st.markdown("### 📊 Detailed Indicator Breakdown")
        
        # Check if symbol is an index (for correct time units)
        is_index = symbol in ['NIFTY', 'BANKNIFTY', 'FINNIFTY', 'SENSEX', 'MIDCPNIFTY'] if symbol else False
        time_unit = 'sec' if is_index else 'min'
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("#### IV Momentum")
            st.write(f"**IV Velocity:** {float(iv_vel):.4f}% per {time_unit}")
            st.write(f"**IV Percentile:** {float(iv_pct):.2%} (Range position)")
            st.write(f"**Implied Move:** ₹{float(impl_move):.2f}")
        
        with col2:
            st.markdown("#### OI Dynamics")
            st.write(f"**OI Acceleration:** {float(oi_accel):,.2f}")
            st.write(f"**OI Velocity:** {float(oi_vel):,.2f} per {time_unit}")
            
            # UNWINDING INTENSITY: ALWAYS RECALCULATE from actual OI changes
            # Don't rely on stored velocity (might be 0 due to duplicate detection)
            try:
                with db.get_connection() as conn:
                    with conn.cursor() as cur:
                        # Fetch last 10 records to find ones with actual OI changes
                        cur.execute("""
                            SELECT atm_oi, timestamp
                            FROM gamma_exposure_history
                            WHERE symbol = %s
                            ORDER BY timestamp DESC
                            LIMIT 10
                        """, (symbol,))
                        all_oi_data = cur.fetchall()
                
                # Filter for records where OI actually changed
                unique_records = []
                prev_oi = None
                for record in all_oi_data:
                    curr_oi = float(record[0]) if record[0] else 0
                    # Include if first record OR OI changed from previous
                    if prev_oi is None or curr_oi != prev_oi:
                        unique_records.append((curr_oi, record[1]))
                        prev_oi = curr_oi
                        if len(unique_records) >= 2:
                            break
                
                if len(unique_records) >= 2:
                    # Most recent OI and timestamp
                    current_oi, current_time = unique_records[0]
                    # Previous different OI and timestamp
                    prev_oi, prev_time = unique_records[1]
                    
                    # Calculate velocity from actual changes
                    if current_oi > 0 and current_oi != prev_oi:
                        time_diff_seconds = (current_time - prev_time).total_seconds()
                        
                        # Calculate per-second or per-minute based on symbol type
                        if time_diff_seconds > 0:
                            if is_index:
                                # Per second for indices
                                oi_velocity_calc = (current_oi - prev_oi) / time_diff_seconds
                            else:
                                # Per minute for stocks
                                oi_velocity_calc = (current_oi - prev_oi) / (time_diff_seconds / 60)
                            
                            # Unwinding = negative velocity (OI decreasing) at ATM strike
                            # Calculate as % of ATM OI unwinding per time unit
                            if oi_velocity_calc < 0:
                                unwinding = min(100, abs(oi_velocity_calc / current_oi) * 100)
                            else:
                                unwinding = 0
                        else:
                            unwinding = 0
                    else:
                        unwinding = 0
                else:
                    # Not enough unique records - no unwinding calculation possible
                    unwinding = 0
            except Exception as e:
                # Error - set to 0
                unwinding = 0
            
            st.write(f"**Unwinding Intensity:** {unwinding:.2f}%")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("#### Gamma Metrics")
            st.write(f"**Gamma Concentration at ATM:** {float(gamma_conc):.2%}")
            st.write(f"**Gamma Gradient:** {float(gamma_grad):.8f}")
            st.write(f"**ATM Gamma:** {float(atm_gamma):.8f}")
        
        with col2:
            st.markdown("#### Delta Analysis")
            st.write(f"**Delta Imbalance:** {float(delta_imb):.4f}")
            st.write(f"**Delta Skew:** {float(delta_skew):.4f}")
            st.write(f"**Regime:** {str(vol_regime).upper()}")
        
        st.markdown("---")
        
        # Display latest GEX snapshot - MATCHES REAL-TIME DATA
        st.markdown("### 💰 Current GEX Snapshot")
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric("ATM Strike", f"₹{float(atm_strike):,.2f}")
        with col2:
            st.metric("Zero Gamma Level", f"₹{float(zero_gamma_strike):,.2f}")
        with col3:
            try:
                net_gex_val = float(net_gex)
            except:
                net_gex_val = 0
            st.metric("Net GEX", f"₹{net_gex_val/1e6:.2f}M", 
                     delta="📉 Negative (Unstable)" if net_gex_val < 0 else "📈 Positive (Stable)")
        
        if is_realtime:
            st.caption(f"📍 Data Source: Real-time Market Data (Live)")
        else:
            st.caption(f"📍 Data Source: Last calculated at {result[2].strftime('%H:%M:%S')} IST")
        
    except Exception as e:
        import traceback
        st.error(f"Error loading leading indicators: {str(e)}")
        st.code(traceback.format_exc())

# 2. ADD this helper function if not already present:
def calculate_market_regime(historical_data=None, gex_df=None, table=None):
    """Determine current market volatility regime"""
    import numpy as np
    
    if historical_data and 'vix' in historical_data:
        vix = historical_data['vix']
        if vix > 25:
            return 'high_vol'
        elif vix < 15:
            return 'low_vol'
        else:
            return 'normal'
    
    if table is not None:
        iv_values = []
        for col in ['CE_IV', 'PE_IV']:
            vals = table[col].dropna()
            vals = vals[vals > 0]
            iv_values.extend(vals.tolist())
        
        if iv_values:
            avg_iv = np.mean(iv_values)
            if avg_iv > 25:
                return 'high_vol'
            elif avg_iv < 15:
                return 'low_vol'
            else:
                return 'normal'
    
    return 'normal'

def detect_gamma_blast(table, spot_price, gex_df, historical_data=None, market_context=None):
    """
    Dynamic Gamma Blast Detection with adaptive thresholds
    """
    signal = "No Blast"
    direction = None
    reasons = []
    entry_signal = False

    # Get current IST time
    from datetime import datetime, time as dt_time
    import pytz
    import numpy as np
    ist = pytz.timezone('Asia/Kolkata')
    current_time_ist = datetime.now(ist)
    
    # Create time objects for comparison
    current_time = dt_time(current_time_ist.hour, current_time_ist.minute)
    market_open = dt_time(9, 15)
    market_close = dt_time(15, 30)
    entry_threshold = dt_time(13, 30)  # 1:30 PM
    
    # Convert times to minutes since midnight for calculations
    current_minutes = current_time.hour * 60 + current_time.minute
    open_minutes = market_open.hour * 60 + market_open.minute
    close_minutes = market_close.hour * 60 + market_close.minute
    
    # Calculate time factor
    time_factor = min((current_minutes - open_minutes) / (close_minutes - open_minutes), 1.0)
    is_entry_time = current_time >= entry_threshold
    
    # 1. Find ATM strike with maximum OI (dynamic ATM definition)
    table_copy = table.copy()
    table_copy['Total_OI'] = table_copy['CE_OI'] + table_copy['PE_OI']
    table_copy['distance_to_spot'] = abs(table_copy['Strike'] - spot_price)
    
    # Dynamic ATM range based on current volatility
    if historical_data and 'vix' in historical_data:
        current_vix = historical_data['vix']
        atm_range_pct = max(0.005, min(0.02, current_vix / 100 * 0.1))
    else:
        iv_values = table_copy[['CE_IV', 'PE_IV']].values.flatten()
        iv_values = iv_values[iv_values > 0]
        avg_iv = np.mean(iv_values) if len(iv_values) > 0 else 20
        atm_range_pct = max(0.005, min(0.02, avg_iv / 100 * 0.05))
    
    atm_candidates = table_copy[table_copy['distance_to_spot'] <= spot_price * atm_range_pct]
    
    if atm_candidates.empty:
        return signal, direction, reasons, entry_signal, is_entry_time

    max_oi_idx = atm_candidates['Total_OI'].idxmax()
    atm_strike = atm_candidates.loc[max_oi_idx, 'Strike']
    atm_row = atm_candidates.loc[max_oi_idx]
    
    spot_atm_distance_pct = abs(spot_price - atm_strike) / spot_price * 100
    proximity_threshold = atm_range_pct * 50
    is_near_max_oi_atm = spot_atm_distance_pct < proximity_threshold
    
    if not is_near_max_oi_atm:
        return signal, direction, reasons, entry_signal, is_entry_time

    reasons.append(f"Spot ({spot_price}) near max OI ATM ({atm_strike}) - Distance: {spot_atm_distance_pct:.2f}%")

    # 2. Extract OI metrics
    ce_oi = atm_row['CE_OI']
    pe_oi = atm_row['PE_OI']
    total_atm_oi = atm_row['Total_OI']
    ce_chg_oi = atm_row['CE_ChgOI'] 
    pe_chg_oi = atm_row['PE_ChgOI']
    
    # 3. Dynamic GEX analysis
    gex_at_atm = gex_df[gex_df['Strike'] == atm_strike]
    if gex_at_atm.empty:
        return signal, direction, reasons, entry_signal, is_entry_time
    
    net_gex_atm = gex_at_atm['Net_GEX'].iloc[0]
    
    # Statistical GEX thresholds (dynamic percentiles)
    gex_values = gex_df['Net_GEX'].dropna()
    gex_25th = gex_values.quantile(0.25)
    gex_10th = gex_values.quantile(0.10) 
    gex_5th = gex_values.quantile(0.05)
    
    # Market regime adjustment
    if market_context and 'regime' in market_context:
        regime = market_context['regime']
        if regime == 'high_vol':
            gex_negative_threshold = gex_25th
            gex_sharp_threshold = gex_10th
        elif regime == 'low_vol':
            gex_negative_threshold = gex_10th
            gex_sharp_threshold = gex_5th
        else:  # normal regime
            gex_negative_threshold = (gex_25th + gex_10th) / 2
            gex_sharp_threshold = (gex_10th + gex_5th) / 2
    else:
        gex_negative_threshold = gex_25th
        gex_sharp_threshold = gex_10th
    
    # Time-based sensitivity adjustment
    late_day_multiplier = 1 + (time_factor * 0.3)
    gex_negative_threshold *= late_day_multiplier
    gex_sharp_threshold *= late_day_multiplier
    
    # GEX conditions
    gex_negative = net_gex_atm < gex_negative_threshold
    gex_sharply_negative = net_gex_atm < gex_sharp_threshold
    
    if gex_negative:
        reasons.append(f"GEX negative: {net_gex_atm/1000000:.1f}M (threshold: {gex_negative_threshold/1000000:.1f}M)")
    if gex_sharply_negative:
        reasons.append(f"GEX sharply negative: {net_gex_atm/1000000:.1f}M (threshold: {gex_sharp_threshold/1000000:.1f}M)")
    
    # 4. Dynamic IV analysis
    ce_iv = atm_row['CE_IV']
    pe_iv = atm_row['PE_IV']
    atm_iv = (ce_iv + pe_iv) / 2
    
    # Calculate IV percentiles across all strikes
    all_iv_values = []
    for col in ['CE_IV', 'PE_IV']:
        iv_vals = table_copy[col].dropna()
        iv_vals = iv_vals[iv_vals > 0]
        all_iv_values.extend(iv_vals.tolist())
    
    if all_iv_values:
        iv_25th = np.percentile(all_iv_values, 25)
        iv_50th = np.percentile(all_iv_values, 50)
        iv_75th = np.percentile(all_iv_values, 75)
        
        iv_low_threshold = iv_25th
        
        nearby_strikes = table_copy[
            (table_copy['Strike'] != atm_strike) &
            (table_copy['distance_to_spot'] <= spot_price * (atm_range_pct * 2))
        ]
        
        if not nearby_strikes.empty:
            nearby_iv_values = []
            for col in ['CE_IV', 'PE_IV']:
                vals = nearby_strikes[col].dropna()
                vals = vals[vals > 0]
                nearby_iv_values.extend(vals.tolist())
            
            if nearby_iv_values:
                avg_nearby_iv = np.mean(nearby_iv_values)
                iv_skew = atm_iv - avg_nearby_iv
                skew_threshold = -(iv_75th - iv_50th) / 2
            else:
                iv_skew = 0
                skew_threshold = -1.0
        else:
            iv_skew = 0
            skew_threshold = -1.0
    else:
        iv_low_threshold = 18
        iv_skew = 0
        skew_threshold = -1.0
    
    # IV conditions
    iv_collapsing = iv_skew < skew_threshold
    atm_iv_low = atm_iv < iv_low_threshold
    
    if iv_collapsing:
        reasons.append(f"ATM IV collapsing: {iv_skew:.1f}% (threshold: {skew_threshold:.1f}%)")
    if atm_iv_low:
        reasons.append(f"ATM IV low: {atm_iv:.1f}% (threshold: {iv_low_threshold:.1f}%)")
    
    # 5. Dynamic OI unwinding detection
    ce_oi_changes = table_copy['CE_ChgOI'].dropna()
    pe_oi_changes = table_copy['PE_ChgOI'].dropna()
    
    if len(ce_oi_changes) > 0:
        ce_unwind_threshold = ce_oi_changes.quantile(0.25)
    else:
        ce_unwind_threshold = -ce_oi * 0.03
        
    if len(pe_oi_changes) > 0:
        pe_unwind_threshold = pe_oi_changes.quantile(0.25)
    else:
        pe_unwind_threshold = -pe_oi * 0.03
    
    total_unwind_pct = max(0.03, min(0.10, time_factor * 0.07))
    
    ce_unwinding = ce_chg_oi < ce_unwind_threshold
    pe_unwinding = pe_chg_oi < pe_unwind_threshold
    total_unwinding = (abs(ce_chg_oi) + abs(pe_chg_oi)) > total_atm_oi * total_unwind_pct
    
    unwinding_detected = ce_unwinding or pe_unwinding or total_unwinding
    
    if ce_unwinding:
        reasons.append(f"CE OI unwinding: {ce_chg_oi:,.0f} (threshold: {ce_unwind_threshold:.0f})")
    if pe_unwinding:
        reasons.append(f"PE OI unwinding: {pe_chg_oi:,.0f} (threshold: {pe_unwind_threshold:.0f})")
    
    # 6. DYNAMIC BLAST SIGNAL DETERMINATION
    gex_score = 0
    if gex_negative: gex_score += 1
    if gex_sharply_negative: gex_score += 2
    
    iv_score = 0
    if iv_collapsing: iv_score += 2
    if atm_iv_low: iv_score += 1
    
    oi_score = 0
    if unwinding_detected: oi_score += 2
    if ce_unwinding and pe_unwinding: oi_score += 1
    
    base_threshold = 3
    if market_context and market_context.get('regime') == 'high_vol':
        base_threshold = 2
    elif time_factor > 0.7:
        base_threshold = 2
    
    total_score = gex_score + iv_score + oi_score
    
    if total_score >= base_threshold + 2:
        ce_unwinding_strength = abs(ce_chg_oi) / max(ce_oi, 1) if ce_oi > 0 else 0
        pe_unwinding_strength = abs(pe_chg_oi) / max(pe_oi, 1) if pe_oi > 0 else 0
        
        directional_threshold = 1.3 + (time_factor * 0.4)
        
        if ce_unwinding_strength > pe_unwinding_strength * directional_threshold:
            direction = "DOWNSIDE_BREAKOUT"
            signal = "Gamma Blast Setup - Downside"
        elif pe_unwinding_strength > ce_unwinding_strength * directional_threshold:
            direction = "UPSIDE_BREAKOUT"
            signal = "Gamma Blast Setup - Upside"
        else:
            direction = "BIDIRECTIONAL"
            signal = "Gamma Blast Setup - Bidirectional"

        
        if is_entry_time:
            entry_signal = True
            signal = signal.replace("Setup", "ENTRY SIGNAL")
            # Format time in 12-hour format with AM/PM
            entry_time_str = entry_threshold.strftime("%I:%M %p")
            reasons.append(f"POST {entry_time_str} - ENTRY CONDITIONS MET")
        else:
            # Format time in 12-hour format with AM/PM
            entry_time_str = entry_threshold.strftime("%I:%M %p")
            reasons.append(f"POST {entry_time_str} - ENTRY CONDITIONS MET")
    elif total_score >= base_threshold:
        signal = "Gamma Blast Watch"
        direction = "MONITOR"
        reasons.append(f"Partial conditions met (Score: {total_score}/{base_threshold+2}) - monitor closely")
    
    elif total_score >= base_threshold - 1:
        signal = "Gamma Compression"
        direction = "SETUP"
        reasons.append(f"Early setup conditions (Score: {total_score}/{base_threshold+2}) - watch for strengthening")

    return signal, direction, reasons, entry_signal, is_entry_time


def implement_vix_like_index(table, spot_price, time_to_expiry):
    """Calculate VIX-like implied volatility index"""
    st.subheader("Custom Volatility Index (VIX-like)")
    
    iv_weights = []
    total_weight = 0
    
    for _, row in table.iterrows():
        strike = row['Strike']
        ce_iv = row['CE_IV']
        pe_iv = row['PE_IV']
        ce_oi = row['CE_OI']
        pe_oi = row['PE_OI']
        
        distance = abs(strike - spot_price) / spot_price
        if distance <= 0.2:
            if ce_oi + pe_oi > 0:
                weighted_iv = (ce_iv * ce_oi + pe_iv * pe_oi) / (ce_oi + pe_oi)
                weight = ce_oi + pe_oi
                
                iv_weights.append({
                    'strike': strike,
                    'iv': weighted_iv,
                    'weight': weight,
                    'distance': distance
                })
                total_weight += weight
    
    if total_weight > 0:
        vix_like_value = sum(item['iv'] * item['weight'] for item in iv_weights) / total_weight
        
        if time_to_expiry < 1:
            vix_like_value = vix_like_value * np.sqrt(365 * time_to_expiry)
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric("Custom VIX", f"{vix_like_value:.2f}")
        
        with col2:
            vix_percentile = "High" if vix_like_value > 25 else "Normal" if vix_like_value > 15 else "Low"
            st.metric("Volatility Regime", vix_percentile)
        
        with col3:
            fear_level = "Extreme Fear" if vix_like_value > 35 else "Fear" if vix_like_value > 25 else "Normal" if vix_like_value > 15 else "Complacency"
            st.metric("Market Sentiment", fear_level)
        
        return vix_like_value
    else:
        st.warning("Insufficient data for VIX calculation")
    
    return None

def display_support_resistance_levels(table, spot_price):
    """Identify support and resistance levels using OI, Volume and GEX data"""
    st.subheader("Support & Resistance Levels (OI + Volume + GEX Weighted)")
    
    # Get GEX data from session state if available
    table_copy = table.copy()
    gex_df = None
    if 'current_gex_data' in st.session_state:
        gex_df = pd.DataFrame(st.session_state.current_gex_data)
        # Merge GEX data with table
        table_copy = table_copy.merge(gex_df[['Strike', 'CE_GEX', 'PE_GEX', 'Net_GEX']], 
                                    on='Strike', how='left')
    
    # Compute base strength using OI and Volume
    table_copy['CE_Strength'] = table_copy['CE_OI'] * np.log1p(table_copy['CE_Volume'])
    table_copy['PE_Strength'] = table_copy['PE_OI'] * np.log1p(table_copy['PE_Volume'])
    
    # Add GEX component if available
    if gex_df is not None:
        # Scale GEX to be comparable with OI*Volume strength
        gex_scale = (table_copy['CE_Strength'].mean() + table_copy['PE_Strength'].mean()) / (abs(gex_df['Net_GEX']).mean() + 1e-10)
        
        # Add scaled GEX to strength - positive GEX adds to CE_Strength (resistance)
        # negative GEX adds to PE_Strength (support)
        table_copy['CE_Strength'] += np.where(table_copy['Net_GEX'] > 0, 
                                            abs(table_copy['Net_GEX']) * gex_scale, 0)
        table_copy['PE_Strength'] += np.where(table_copy['Net_GEX'] < 0, 
                                            abs(table_copy['Net_GEX']) * gex_scale, 0)
    
    # Calculate total strengths for normalization
    total_ce_strength = table_copy['CE_Strength'].sum()
    total_pe_strength = table_copy['PE_Strength'].sum()
    
    # Identify significant levels
    significant_levels = []
    
    # Calculate relative strength at each strike
    table_copy['CE_Relative_Strength'] = table_copy['CE_Strength'] / total_ce_strength if total_ce_strength > 0 else 0
    table_copy['PE_Relative_Strength'] = table_copy['PE_Strength'] / total_pe_strength if total_pe_strength > 0 else 0
    
    # Add distance from spot for weighting
    table_copy['Distance'] = abs(table_copy['Strike'] - spot_price)
    max_distance = table_copy['Distance'].max()
    table_copy['Distance_Weight'] = 1 - (table_copy['Distance'] / max_distance)
    
    # Calculate strength thresholds
    ce_threshold = table_copy['CE_Relative_Strength'].mean() + table_copy['CE_Relative_Strength'].std()
    pe_threshold = table_copy['PE_Relative_Strength'].mean() + table_copy['PE_Relative_Strength'].std()
    
    for _, row in table_copy.iterrows():
        strike = row['Strike']
        distance_weight = row['Distance_Weight']
        
        # Calculate weighted relative strengths
        ce_weighted_strength = row['CE_Relative_Strength'] * distance_weight
        pe_weighted_strength = row['PE_Relative_Strength'] * distance_weight
        
        # Add GEX influence if available
        if gex_df is not None and 'Net_GEX' in row:
            gex_influence = abs(row['Net_GEX']) * gex_scale * distance_weight
            if row['Net_GEX'] > 0:
                ce_weighted_strength += gex_influence
            else:
                pe_weighted_strength += gex_influence
        
        # Determine level type and strength
        # Check for resistance levels (strong call activity above spot)
        if strike > spot_price and ce_weighted_strength > ce_threshold:
            level_type = "Resistance"
            strength_pct = ce_weighted_strength * 100
            strength = "Strong" if strength_pct > 1.5 * ce_threshold * 100 else "Moderate"
            # Add resistance level
            significant_levels.append({
                'Level': strike,
                'Type': level_type,
                'Strength': strength,
                'Distance%': abs(strike - spot_price) / spot_price * 100,
                'OI_Volume_Weight': row['CE_Strength'],
                'GEX_Impact': row.get('Net_GEX', 0) if gex_df is not None else 0,
                'Total_Weight': ce_weighted_strength
            })
            
        # Check for support levels (strong put activity below spot)
        if strike < spot_price and pe_weighted_strength > pe_threshold:
            level_type = "Support"
            strength_pct = pe_weighted_strength * 100
            strength = "Strong" if strength_pct > 1.5 * pe_threshold * 100 else "Moderate"
            # Add support level
            significant_levels.append({
                'Level': strike,
                'Type': level_type,
                'Strength': strength,
                'Distance%': abs(strike - spot_price) / spot_price * 100,
                'OI_Volume_Weight': row['PE_Strength'],
                'GEX_Impact': row.get('Net_GEX', 0) if gex_df is not None else 0,
                'Total_Weight': pe_weighted_strength
            })
    
    if significant_levels:
        levels_df = pd.DataFrame(significant_levels)
        # Remove duplicate levels and keep the one with the highest weight
        levels_df = levels_df.sort_values('Total_Weight', ascending=False)
        levels_df = levels_df.drop_duplicates(subset=['Level', 'Type'], keep='first')
        levels_df = levels_df.sort_values(['Type', 'Total_Weight'], ascending=[True, False])
        
        col1, col2 = st.columns(2)
        
        # Display support levels
        with col1:
            support_levels = levels_df[levels_df['Type'] == 'Support'].head(3)
            st.markdown("**Key Support Levels**")
            if not support_levels.empty:
                for _, level in support_levels.iterrows():
                    gex_info = f" | GEX: {format_number(level['GEX_Impact'])}" if gex_df is not None else ""
                    st.write(f"• ₹{level['Level']:,.0f} ({level['Strength']}) - {level['Distance%']:.1f}% below spot{gex_info}")
            else:
                st.write("No significant support levels found")
        
        # Display resistance levels
        with col2:
            resistance_levels = levels_df[levels_df['Type'] == 'Resistance'].head(3)
            st.markdown("**Key Resistance Levels**")
            if not resistance_levels.empty:
                for _, level in resistance_levels.iterrows():
                    gex_info = f" | GEX: {format_number(level['GEX_Impact'])}" if gex_df is not None else ""
                    st.write(f"• ₹{level['Level']:,.0f} ({level['Strength']}) - {level['Distance%']:.1f}% above spot{gex_info}")
            else:
                st.write("No significant resistance levels found")
    else:
        st.info("No significant support/resistance levels identified")

def calculate_put_call_parity_analysis(table, atm_strike):
    """Put-Call Parity Analysis for OTM equidistant pairs"""
    st.subheader("Put-Call Parity Analysis (OTM Equidistant Pairs)")
    
    parity_pairs = []
    otm_calls = table[table["Strike"] > atm_strike].copy()
    otm_puts = table[table["Strike"] < atm_strike].copy()

    for _, call_row in otm_calls.iterrows():
        call_strike = call_row['Strike']
        call_distance = call_strike - atm_strike
        target_put_strike = atm_strike - call_distance

        put_row = otm_puts[otm_puts['Strike'] == target_put_strike]
        if not put_row.empty:
            put_row = put_row.iloc[0]

            ce_ltp = call_row['CE_LTP']
            pe_ltp = put_row['PE_LTP']
            ce_iv = call_row['CE_IV']
            pe_iv = put_row['PE_IV']

            actual_diff = ce_ltp - pe_ltp
            deviation_pct = (actual_diff / pe_ltp) * 100 if pe_ltp > 0 else None

            mispricing = "Overvalued" if actual_diff > 0 else "Undervalued" if actual_diff < 0 else "Fair"

            parity_pairs.append({
                'Distance': int(call_distance),
                'Call_Strike': int(call_strike),
                'Put_Strike': int(target_put_strike),
                'Call_Price': f"{ce_ltp:,.2f}",
                'Put_Price': f"{pe_ltp:,.2f}",
                'Call_IV': f"{ce_iv:.1f}%",
                'Put_IV': f"{pe_iv:.1f}%",
                'Deviation': f"{deviation_pct:.2f}%" if deviation_pct else "N/A",
                'Mispricing': mispricing
            })

    if parity_pairs:
        parity_df = pd.DataFrame(parity_pairs)
        
        def highlight_mispricing(val):
            if val == "Overvalued":
                return 'background-color: #ffcdd2; color: #b71c1c'
            elif val == "Undervalued":
                return 'background-color: #c8e6c9; color: #1b5e20'
            else:
                return 'background-color: #fff9c4; color: #f57f17'

        styled = parity_df.style.applymap(highlight_mispricing, subset=['Mispricing'])
        st.dataframe(styled, use_container_width=True)
    else:
        st.warning("No equidistant OTM pairs found for parity analysis.")

# Move the bucket summary display code inside the main function
def display_bucket_summary(bucket_summary, left_col, middle_col):
    def format_bucket_stats(bucket_data, oi_color, chgoi_color):
        return f"""
        <div style="background: linear-gradient(90deg, {oi_color}15, transparent); padding: 10px; border-radius: 8px; border-left: 4px solid {oi_color};">
            <div style="color: {oi_color}; font-weight: bold;">OI: {format_number(bucket_data['OI'])}</div>
            <div style="color: {chgoi_color}; font-weight: bold;">ChgOI: {'+' if bucket_data['ChgOI'] >= 0 else ''}{format_number(bucket_data['ChgOI'])}</div>
            <div>Volume: {format_number(bucket_data['Volume'])}</div>
            <div style="font-size: 0.9em;">IV: {bucket_data['IV']:.2f}%</div>
            <div style="font-size: 0.9em;">Delta: {bucket_data['Delta']:.4f}</div>
        </div>
        """

    with left_col:
        st.markdown("### Calls (CE)")
        
        # ITM Calls
        st.markdown("**ITM (below spot)**")
        ce_itm_oi_color = get_change_color(bucket_summary['CE_ITM']['OI'])
        ce_itm_chgoi_color = get_change_color(bucket_summary['CE_ITM']['ChgOI'])
        st.markdown(format_bucket_stats(bucket_summary['CE_ITM'], ce_itm_oi_color, ce_itm_chgoi_color), unsafe_allow_html=True)
        st.markdown("<br>", unsafe_allow_html=True)
        
        # OTM Calls
        st.markdown("**OTM (above spot)**")
        ce_otm_oi_color = get_change_color(bucket_summary['CE_OTM']['OI'])
        ce_otm_chgoi_color = get_change_color(bucket_summary['CE_OTM']['ChgOI'])
        st.markdown(format_bucket_stats(bucket_summary['CE_OTM'], ce_otm_oi_color, ce_otm_chgoi_color), unsafe_allow_html=True)
    
    with middle_col:
        st.markdown("### Puts (PE)")
        
        # ITM Puts
        st.markdown("**ITM (above spot)**")
        pe_itm_oi_color = get_change_color(bucket_summary['PE_ITM']['OI'])
        pe_itm_chgoi_color = get_change_color(bucket_summary['PE_ITM']['ChgOI'])
        st.markdown(format_bucket_stats(bucket_summary['PE_ITM'], pe_itm_oi_color, pe_itm_chgoi_color), unsafe_allow_html=True)
        st.markdown("<br>", unsafe_allow_html=True)
        
        # OTM Puts
        st.markdown("**OTM (below spot)**")
        pe_otm_oi_color = get_change_color(bucket_summary['PE_OTM']['OI'])
        pe_otm_chgoi_color = get_change_color(bucket_summary['PE_OTM']['ChgOI'])
        st.markdown(format_bucket_stats(bucket_summary['PE_OTM'], pe_otm_oi_color, pe_otm_chgoi_color), unsafe_allow_html=True)

# Format and display bucket summary for option chain data
def get_bucket_stats_html(data, oi_color, chgoi_color):
    return f"""<div style='background: linear-gradient(90deg, {oi_color}15, transparent); padding: 10px; border-radius: 8px; border-left: 4px solid {oi_color};'>
        <div style='color: {oi_color}; font-weight: bold;'>OI: {format_number(data["OI"])}</div>
        <div style='color: {chgoi_color}; font-weight: bold;'>ChgOI: {'+' if data["ChgOI"] >= 0 else ''}{format_number(data["ChgOI"])}</div>
        <div>Volume: {format_number(data["Volume"])}</div>
        <div style='font-size: 0.9em;'>IV: {data["IV"]:.2f}%</div>
        <div style='font-size: 0.9em;'>Delta: {data["Delta"]:.4f}</div>
    </div>"""

def display_bucket_summary(bucket_summary, left_col, middle_col):
    with left_col:
        st.markdown("### Calls (CE)")
        
        st.markdown("**ITM (below spot)**")
        ce_itm_oi_color = get_change_color(bucket_summary['CE_ITM']['OI'])
        ce_itm_chgoi_color = get_change_color(bucket_summary['CE_ITM']['ChgOI'])
        st.markdown(get_bucket_stats_html(bucket_summary['CE_ITM'], ce_itm_oi_color, ce_itm_chgoi_color), unsafe_allow_html=True)
        st.markdown("<br>", unsafe_allow_html=True)
        
        st.markdown("**OTM (above spot)**")
        ce_otm_oi_color = get_change_color(bucket_summary['CE_OTM']['OI'])
        ce_otm_chgoi_color = get_change_color(bucket_summary['CE_OTM']['ChgOI'])
        st.markdown(get_bucket_stats_html(bucket_summary['CE_OTM'], ce_otm_oi_color, ce_otm_chgoi_color), unsafe_allow_html=True)
    
    with middle_col:
        st.markdown("### Puts (PE)")
        
        st.markdown("**ITM (above spot)**")
        pe_itm_oi_color = get_change_color(bucket_summary['PE_ITM']['OI'])
        pe_itm_chgoi_color = get_change_color(bucket_summary['PE_ITM']['ChgOI'])
        st.markdown(get_bucket_stats_html(bucket_summary['PE_ITM'], pe_itm_oi_color, pe_itm_chgoi_color), unsafe_allow_html=True)
        st.markdown("<br>", unsafe_allow_html=True)
        
        st.markdown("**OTM (below spot)**")
        pe_otm_oi_color = get_change_color(bucket_summary['PE_OTM']['OI'])
        pe_otm_chgoi_color = get_change_color(bucket_summary['PE_OTM']['ChgOI'])
        st.markdown(get_bucket_stats_html(bucket_summary['PE_OTM'], pe_otm_oi_color, pe_otm_chgoi_color), unsafe_allow_html=True)

# ITM Analysis Functions

def display_itm_analysis(symbol, expiry_date, db_manager, itm_count=1, hours=24):
    """Display ITM Call and Put analysis with graphs using pre-stored bucket summaries"""
    
    st.subheader(f"ITM Call & Put Analysis - {symbol} | {expiry_date} | ITM Count: {itm_count}")
    
    # Fetch stored ITM bucket summaries
    with st.spinner(f"Fetching ITM bucket data for {symbol}..."):
        itm_data = db_manager.get_itm_bucket_summaries(symbol, expiry_date, itm_count, hours=hours)
    
    if itm_data is None or len(itm_data) == 0:
        st.warning(f"⚠️ No ITM bucket data available for {symbol} with {itm_count} strikes in last {hours} hours")
        st.info(f"""
        **Why no data?**
        - Market may be closed (9:15 AM - 3:30 PM IST)
        - ITM bucket summaries are stored by background service during market hours
        - Try increasing "Look Back (hrs)" to 48 or 72 hours to see previous day's data
        
        **Next steps:**
        - Increase the time range slider above
        - Ensure background service is running during market hours
        - Refresh the page after market opens
        """)
        return
    
    # Check if data is from today or previous session
    import pytz
    IST = pytz.timezone('Asia/Kolkata')
    latest_timestamp = itm_data['timestamp'].max().astimezone(IST)
    current_date = datetime.now(IST).date()
    data_date = latest_timestamp.date()
    
    if data_date < current_date:
        st.info(f"📅 Showing data from previous session: {data_date.strftime('%b %d, %Y')} (Latest: {latest_timestamp.strftime('%I:%M %p')})")
    
    st.success(f"✅ Loaded {len(itm_data)} data points for ITM count {itm_count}")
    
    # Create tabs for different analyses
    tab_oi, tab_vol, tab_chgoi = st.tabs([
        "📊 Open Interest (OI)", 
        "📈 Volume", 
        "🔄 Change in OI"
    ])
    
    with tab_oi:
        st.markdown(f"### ITM ({itm_count} strikes) Call & Put Open Interest Over Time")
        plot_itm_oi_chart(itm_data, symbol, itm_count)
    
    with tab_vol:
        st.markdown(f"### ITM ({itm_count} strikes) Call & Put Volume Over Time")
        plot_itm_volume_chart(itm_data, symbol, itm_count)
    
    with tab_chgoi:
        st.markdown(f"### ITM ({itm_count} strikes) Call & Put Change in OI Over Time")
        plot_itm_chgoi_chart(itm_data, symbol, itm_count)
    
    # Statistics section
    st.markdown("---")
    st.subheader("ITM Statistics")
    
    col1, col2, col3 = st.columns(3)
    
    # Get latest values
    latest = itm_data.iloc[-1] if len(itm_data) > 0 else None
    
    if latest is not None:
        with col1:
            st.markdown("#### Call OI")
            st.metric("Current", format_number(latest['ce_oi']))
            if len(itm_data) > 1:
                prev = itm_data.iloc[-2]['ce_oi']
                change = latest['ce_oi'] - prev
                st.metric("Change from Last Update", format_number(change), delta=f"+{format_number(change)}" if change > 0 else format_number(change))
        
        with col2:
            st.markdown("#### Put OI")
            st.metric("Current", format_number(latest['pe_oi']))
            if len(itm_data) > 1:
                prev = itm_data.iloc[-2]['pe_oi']
                change = latest['pe_oi'] - prev
                st.metric("Change from Last Update", format_number(change), delta=f"+{format_number(change)}" if change > 0 else format_number(change))
        
        with col3:
            st.markdown("#### PCR (OI Ratio)")
            pcr = latest['pcr_oi'] if not pd.isna(latest['pcr_oi']) else 0
            st.metric("Put/Call Ratio", f"{pcr:.3f}")
            
            if pcr > 1.2:
                st.caption("🔴 Bearish")
            elif pcr < 0.8:
                st.caption("🟢 Bullish")
            else:
                st.caption("🟡 Neutral")
    
    # Summary stats
    st.markdown("#### Summary Stats")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric("Avg CE OI", format_number(itm_data['ce_oi'].mean()))
        st.metric("Max CE OI", format_number(itm_data['ce_oi'].max()))
        st.metric("Min CE OI", format_number(itm_data['ce_oi'].min()))
    
    with col2:
        st.metric("Avg PE OI", format_number(itm_data['pe_oi'].mean()))
        st.metric("Max PE OI", format_number(itm_data['pe_oi'].max()))
        st.metric("Min PE OI", format_number(itm_data['pe_oi'].min()))
    
    with col3:
        st.metric("Avg PCR OI", f"{itm_data['pcr_oi'].mean():.3f}")
        st.metric("Avg CE Vol", format_number(itm_data['ce_volume'].mean()))
        st.metric("Avg PE Vol", format_number(itm_data['pe_volume'].mean()))

def plot_itm_oi_chart(itm_data, symbol, itm_count):
    """Plot ITM Open Interest Chart"""
    import pytz
    IST = pytz.timezone('Asia/Kolkata')
    
    try:
        # Convert timestamps to IST
        itm_data_ist = itm_data.copy()
        itm_data_ist['timestamp'] = itm_data_ist['timestamp'].apply(lambda x: x.astimezone(IST) if x.tzinfo else IST.localize(x))
        
        fig, ax = plt.subplots(figsize=(14, 6))
        
        # Use numeric x-axis for proper IST display
        x_numeric = np.arange(len(itm_data_ist['timestamp']))
        
        # Plot OI
        ax.plot(x_numeric, itm_data_ist['ce_oi'], 
                marker='o', label=f'Call OI (CE) - {itm_count} ITM', linewidth=2, color='#1f77b4', markersize=5)
        ax.plot(x_numeric, itm_data_ist['pe_oi'], 
                marker='s', label=f'Put OI (PE) - {itm_count} ITM', linewidth=2, color='#ff7f0e', markersize=5)
        
        # Fill between for better visualization
        ax.fill_between(x_numeric, itm_data_ist['ce_oi'], alpha=0.2, color='#1f77b4')
        ax.fill_between(x_numeric, itm_data_ist['pe_oi'], alpha=0.2, color='#ff7f0e')
        
        ax.set_xlabel('Time (IST)', fontsize=12, fontweight='bold')
        ax.set_ylabel('Open Interest', fontsize=12, fontweight='bold')
        ax.set_title(f'{symbol} - ITM ({itm_count} Strikes) Call & Put Open Interest', fontsize=14, fontweight='bold')
        ax.legend(loc='best', fontsize=11)
        ax.grid(True, alpha=0.3)
        
        # Format y-axis to show large numbers properly
        ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: format_number(x)))
        
        # Set x-axis labels with IST times
        ax.set_xticks(x_numeric)
        ax.set_xticklabels([ts.strftime('%H:%M') for ts in itm_data_ist['timestamp']], rotation=45, ha='right')
        
        plt.tight_layout()
        st.pyplot(fig)
        plt.close()
        
    except Exception as e:
        st.error(f"Error creating OI chart: {str(e)}")
        import traceback
        st.code(traceback.format_exc())

def plot_itm_volume_chart(itm_data, symbol, itm_count):
    """Plot ITM Volume Chart"""
    import pytz
    IST = pytz.timezone('Asia/Kolkata')
    
    try:
        # Convert timestamps to IST
        itm_data_ist = itm_data.copy()
        itm_data_ist['timestamp'] = itm_data_ist['timestamp'].apply(lambda x: x.astimezone(IST) if x.tzinfo else IST.localize(x))
        
        fig, ax = plt.subplots(figsize=(14, 6))
        
        # Use numeric x-axis for proper IST display
        x_numeric = np.arange(len(itm_data_ist['timestamp']))
        
        # Plot Volume
        ax.plot(x_numeric, itm_data_ist['ce_volume'], 
                marker='o', label=f'Call Volume (CE) - {itm_count} ITM', linewidth=2, color='#2ca02c', markersize=5)
        ax.plot(x_numeric, itm_data_ist['pe_volume'], 
                marker='s', label=f'Put Volume (PE) - {itm_count} ITM', linewidth=2, color='#d62728', markersize=5)
        
        # Fill between for better visualization
        ax.fill_between(x_numeric, itm_data_ist['ce_volume'], alpha=0.2, color='#2ca02c')
        ax.fill_between(x_numeric, itm_data_ist['pe_volume'], alpha=0.2, color='#d62728')
        
        ax.set_xlabel('Time (IST)', fontsize=12, fontweight='bold')
        ax.set_ylabel('Volume', fontsize=12, fontweight='bold')
        ax.set_title(f'{symbol} - ITM ({itm_count} Strikes) Call & Put Volume', fontsize=14, fontweight='bold')
        ax.legend(loc='best', fontsize=11)
        ax.grid(True, alpha=0.3)
        
        # Format y-axis to show large numbers properly
        ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: format_number(x)))
        
        # Set x-axis labels with IST times
        ax.set_xticks(x_numeric)
        ax.set_xticklabels([ts.strftime('%H:%M') for ts in itm_data_ist['timestamp']], rotation=45, ha='right')
        
        plt.tight_layout()
        st.pyplot(fig)
        plt.close()
        
    except Exception as e:
        st.error(f"Error creating Volume chart: {str(e)}")
        import traceback
        st.code(traceback.format_exc())

def plot_itm_chgoi_chart(itm_data, symbol, itm_count):
    """Plot ITM Change in OI Chart"""
    import pytz
    IST = pytz.timezone('Asia/Kolkata')
    
    try:
        # Convert timestamps to IST
        itm_data_ist = itm_data.copy()
        itm_data_ist['timestamp'] = itm_data_ist['timestamp'].apply(lambda x: x.astimezone(IST) if x.tzinfo else IST.localize(x))
        
        fig, ax = plt.subplots(figsize=(14, 6))
        
        # Plot Change in OI as bars
        x_numeric = np.arange(len(itm_data_ist['timestamp']))
        
        # Create bar chart for change in OI
        bars1 = ax.bar(x_numeric - 0.2, itm_data_ist['ce_chgoi'], width=0.4, 
                       label=f'Call ChgOI (CE) - {itm_count} ITM', color='#1f77b4', alpha=0.7)
        bars2 = ax.bar(x_numeric + 0.2, itm_data_ist['pe_chgoi'], width=0.4, 
                       label=f'Put ChgOI (PE) - {itm_count} ITM', color='#ff7f0e', alpha=0.7)
        
        # Add zero line
        ax.axhline(y=0, color='black', linestyle='-', linewidth=0.8)
        
        ax.set_xlabel('Time (IST)', fontsize=12, fontweight='bold')
        ax.set_ylabel('Change in Open Interest', fontsize=12, fontweight='bold')
        ax.set_title(f'{symbol} - ITM ({itm_count} Strikes) Call & Put Change in OI', fontsize=14, fontweight='bold')
        
        # Set x-axis labels
        ax.set_xticks(x_numeric)
        ax.set_xticklabels([ts.strftime('%H:%M') for ts in itm_data_ist['timestamp']], rotation=45, ha='right')
        
        ax.legend(loc='best', fontsize=11)
        ax.grid(True, alpha=0.3, axis='y')
        
        # Format y-axis to show large numbers properly
        ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: format_number(x)))
        
        plt.tight_layout()
        st.pyplot(fig)
        plt.close()
        
    except Exception as e:
        st.error(f"Error creating Change in OI chart: {str(e)}")
        import traceback
        st.code(traceback.format_exc())


# ============================================================================
# LEADING INDICATORS FUNCTIONS - Gamma Exposure Optimization
# ============================================================================

def calculate_iv_momentum(current_iv: float, iv_history_5min: list, iv_history_1hour: list) -> dict:
    """
    Calculate IV momentum and acceleration (LEADING INDICATOR)
    Predicts if IV is about to spike or collapse
    """
    import numpy as np
    
    # Calculate first derivative (velocity) - change per minute
    if len(iv_history_5min) >= 2:
        iv_velocity = (current_iv - iv_history_5min[-1]) / 3  # per 3 minutes (background refresh interval)
    else:
        iv_velocity = 0
    
    # Calculate second derivative (acceleration)
    if len(iv_history_5min) >= 3:
        prev_velocity = (iv_history_5min[-1] - iv_history_5min[-2]) / 3
        iv_acceleration = iv_velocity - prev_velocity
    else:
        iv_acceleration = 0
    
    # Trend detection: Is IV moving consistently in one direction?
    if len(iv_history_1hour) >= 5:
        recent_changes = np.diff(iv_history_1hour[-5:])
        consistent_direction = np.all(recent_changes > 0) or np.all(recent_changes < 0)
    else:
        consistent_direction = False
    
    return {
        'velocity': iv_velocity,
        'acceleration': iv_acceleration,
        'trend': 'rising' if iv_velocity > 0 else 'falling',
        'is_accelerating': iv_acceleration > 0.05,
        'consistent_trend': consistent_direction,
        'explosion_score': min(abs(iv_acceleration) * 10, 1.0)
    }


def calculate_oi_dynamics(current_oi_change: float, oi_change_history: list, 
                         time_interval_minutes: int = 3) -> dict:
    """
    Calculate OI change velocity and acceleration (LEADING INDICATOR)
    Detects if OI unwinding is ACCELERATING (gamma blast precursor)
    """
    import numpy as np
    
    # OI velocity: How fast is it unwinding?
    oi_velocity = current_oi_change / max(time_interval_minutes, 1)
    
    # OI acceleration: Is unwinding getting faster?
    if len(oi_change_history) >= 2:
        prev_velocity = oi_change_history[-1] / max(time_interval_minutes, 1)
        oi_acceleration = oi_velocity - prev_velocity
    else:
        oi_acceleration = 0
    
    # Unwinding consistency (0-1 score)
    if len(oi_change_history) >= 3:
        recent_unwinds = [x for x in oi_change_history[-3:] if x < 0]
        consistency = len(recent_unwinds) / 3
    else:
        consistency = 0
    
    return {
        'velocity': oi_velocity,
        'acceleration': oi_acceleration,
        'is_accelerating': oi_acceleration < -0.5,  # More negative = faster unwinding
        'consistency': consistency,
        'unwinding_intensity': min(abs(oi_acceleration) * 0.1, 1.0)
    }


def calculate_gamma_concentration_trend(current_gex_profile: pd.DataFrame, 
                                       spot_price: float, gex_history: list) -> dict:
    """
    Calculate gamma concentration trend (LEADING INDICATOR)
    Detects when gamma is concentrating at ATM (blast setup)
    """
    import numpy as np
    
    if current_gex_profile.empty:
        return {
            'concentration': 0,
            'concentration_trend': 0,
            'is_concentrating': False,
            'blast_setup_score': 0
        }
    
    strikes = current_gex_profile['Strike'].values
    gamma_values = current_gex_profile['Net_GEX'].abs().values
    
    # Find ATM and nearby gamma
    atm_idx = np.argmin(np.abs(strikes - spot_price))
    atm_gamma = gamma_values[atm_idx] if atm_idx < len(gamma_values) else 0
    
    # Concentration = % of total gamma at ATM
    total_gamma = gamma_values.sum()
    concentration = atm_gamma / total_gamma if total_gamma > 0 else 0
    
    # Trend: Is concentration increasing?
    if len(gex_history) >= 2:
        prev_concentration = gex_history[-1].get('concentration', 0)
        concentration_trend = concentration - prev_concentration
    else:
        concentration_trend = 0
    
    return {
        'concentration': concentration,
        'concentration_trend': concentration_trend,
        'is_concentrating': concentration_trend > 0.02,
        'blast_setup_score': min(concentration * abs(concentration_trend) * 100, 1.0)
    }


def calculate_iv_percentile_rank(current_iv: float, iv_1day_range: dict, 
                                 iv_30day_range: dict, days_to_expiry: float) -> dict:
    """
    Calculate IV percentile rank (LEADING INDICATOR)
    Shows where IV is in its typical range
    """
    import numpy as np
    
    # Normalize to 0-1 range
    iv_1d_min = iv_1day_range.get('min', current_iv)
    iv_1d_max = iv_1day_range.get('max', current_iv)
    iv_30d_min = iv_30day_range.get('min', current_iv)
    iv_30d_max = iv_30day_range.get('max', current_iv)
    
    iv_percentile_1d = (current_iv - iv_1d_min) / (iv_1d_max - iv_1d_min + 0.01) if iv_1d_max > iv_1d_min else 0.5
    iv_percentile_1m = (current_iv - iv_30d_min) / (iv_30d_max - iv_30d_min + 0.01) if iv_30d_max > iv_30d_min else 0.5
    
    # Calculate implied move
    if days_to_expiry > 0:
        implied_move = current_iv * np.sqrt(days_to_expiry / 365) * 100  # As percentage
    else:
        implied_move = 0
    
    return {
        'percentile_1day': np.clip(iv_percentile_1d, 0, 1),
        'percentile_30day': np.clip(iv_percentile_1m, 0, 1),
        'mean_reversion_score': abs(0.5 - iv_percentile_1m),
        'implied_move': implied_move
    }


def calculate_delta_imbalance_trend(table: pd.DataFrame, spot_price: float, 
                                    atm_idx: int, delta_history: list) -> dict:
    """
    Calculate delta ladder imbalance trend (LEADING INDICATOR)
    Detects when delta ladder is getting unbalanced (directional move coming)
    """
    import numpy as np
    
    if table.empty or atm_idx >= len(table):
        return {
            'imbalance': 0,
            'imbalance_trend': 0,
            'is_increasing': False,
            'predicted_direction': 'NEUTRAL',
            'directional_conviction': 0
        }
    
    # Get call and put deltas
    call_deltas = table['CE_Delta'].fillna(0).values[:atm_idx]
    put_deltas = table['PE_Delta'].fillna(0).values[atm_idx:]
    
    # Calculate delta ladder sums
    call_delta_sum = np.sum(call_deltas) if len(call_deltas) > 0 else 0
    put_delta_sum = np.sum(put_deltas) if len(put_deltas) > 0 else 0
    
    # Imbalance ratio
    total_delta = abs(call_delta_sum) + abs(put_delta_sum)
    imbalance = (call_delta_sum - put_delta_sum) / (total_delta + 1e-10)
    
    # Trend
    if len(delta_history) >= 2:
        prev_imbalance = delta_history[-1].get('imbalance', 0)
        imbalance_trend = imbalance - prev_imbalance
        is_increasing_imbalance = abs(imbalance_trend) > 0.05
    else:
        imbalance_trend = 0
        is_increasing_imbalance = False
    
    # Direction prediction
    if imbalance > 0.3 and is_increasing_imbalance:
        predicted_direction = 'DOWNSIDE'
    elif imbalance < -0.3 and is_increasing_imbalance:
        predicted_direction = 'UPSIDE'
    else:
        predicted_direction = 'NEUTRAL'
    
    return {
        'imbalance': imbalance,
        'imbalance_trend': imbalance_trend,
        'is_increasing': is_increasing_imbalance,
        'predicted_direction': predicted_direction,
        'directional_conviction': min(abs(imbalance) + abs(imbalance_trend) * 2, 1.0)
    }


def calculate_gamma_blast_probability(iv_momentum: dict, oi_dynamics: dict,
                                     gamma_concentration: dict, delta_imbalance: dict,
                                     market_regime: str, time_to_expiry_minutes: int) -> dict:
    """
    Calculate gamma blast probability forecast (LEADING INDICATOR)
    Predicts WHEN gamma blast will occur and with what confidence
    """
    import numpy as np
    
    score = 0
    max_score = 0
    
    # Factor 1: IV Acceleration (30% weight)
    if iv_momentum.get('is_accelerating', False):
        score += 0.3 * min(abs(iv_momentum.get('acceleration', 0)) * 10, 1.0)
    max_score += 0.3
    
    # Factor 2: OI Unwinding Acceleration (30% weight)
    if oi_dynamics.get('is_accelerating', False):
        score += 0.3 * min(oi_dynamics.get('unwinding_intensity', 0) * 2, 1.0)
    max_score += 0.3
    
    # Factor 3: Gamma Concentration Increase (20% weight)
    if gamma_concentration.get('is_concentrating', False):
        score += 0.2 * gamma_concentration.get('concentration', 0)
    max_score += 0.2
    
    # Factor 4: Delta Imbalance Trend (20% weight)
    if delta_imbalance.get('is_increasing', False):
        score += 0.2 * delta_imbalance.get('directional_conviction', 0)
    max_score += 0.2
    
    # Normalize to 0-1
    probability = score / max_score if max_score > 0 else 0
    
    # Estimate time to gamma blast based on acceleration intensity
    oi_accel = oi_dynamics.get('acceleration', 0)
    if probability > 0.7:
        if oi_accel < -2:
            time_to_blast = 5
        elif oi_accel < -0.5:
            time_to_blast = 15
        else:
            time_to_blast = 30
    else:
        time_to_blast = min(60 + (1 - probability) * 60, time_to_expiry_minutes)
    
    # Confidence level
    if probability > 0.85:
        confidence = 'VERY_HIGH'
    elif probability > 0.7:
        confidence = 'HIGH'
    elif probability > 0.5:
        confidence = 'MEDIUM'
    else:
        confidence = 'LOW'
    
    return {
        'probability': min(probability, 1.0),
        'confidence': confidence,
        'time_to_blast_minutes': int(time_to_blast),
        'directional_bias': delta_imbalance.get('predicted_direction', 'NEUTRAL'),
        'trigger_metrics': {
            'iv_momentum': iv_momentum.get('acceleration', 0),
            'oi_unwinding_speed': oi_dynamics.get('acceleration', 0),
            'gamma_concentration_trend': gamma_concentration.get('concentration_trend', 0),
            'delta_imbalance_trend': delta_imbalance.get('imbalance_trend', 0)
        }
    }


# Only run the app when this file is run directly
if __name__ == "__main__":
    main()
       
