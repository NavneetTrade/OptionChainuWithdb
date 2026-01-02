"""
Standalone Upstox API Client
Can be used by both Streamlit app and background service
"""

import requests
import urllib.parse
from typing import Tuple, Optional, Dict, Any


# Upstox API endpoints
BASE_URL = "https://api.upstox.com/v2"
AUTH_URL = "https://api-v2.upstox.com/login/authorization/dialog"
TOKEN_URL = "https://api-v2.upstox.com/login/authorization/token"


class UpstoxAPI:
    """Upstox API client for fetching option chain data"""
    
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
                error_msg = response.json() if response.text else f"HTTP {response.status_code}"
                return None, error_msg
        except Exception as e:
            return None, str(e)
    
    def get_option_greeks(self, instrument_keys):
        """Get option Greeks for given instrument keys"""
        if not self.access_token:
            return None, "Access token not available"
        
        try:
            headers = {
                'Authorization': f'Bearer {self.access_token}',
                'Accept': 'application/json'
            }
            
            url = f"{BASE_URL}/option/greeks"
            params = {'instrument_keys': ','.join(instrument_keys)}
            
            response = requests.get(url, headers=headers, params=params)
            
            if response.status_code == 200:
                return response.json(), None
            else:
                return None, response.json() if response.text else f"HTTP {response.status_code}"
        except Exception as e:
            return None, str(e)
    
    def get_market_data_feed(self, instrument_key, interval='1minute'):
        """Get market data feed for an instrument"""
        if not self.access_token:
            return None, "Access token not available"
        
        try:
            headers = {
                'Authorization': f'Bearer {self.access_token}',
                'Accept': 'application/json'
            }
            
            url = f"{BASE_URL}/market-quote/quotes"
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
        """Get user profile information"""
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


