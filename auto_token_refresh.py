"""
Automatic Token Refresh for Upstox API
Based on: https://upstox.com/developer/api-documentation/get-token/

Since Upstox API doesn't provide refresh_token, we use extended_token
or re-authenticate when access_token expires.
"""

import requests
import logging
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
import toml
from pathlib import Path

logger = logging.getLogger(__name__)

class UpstoxTokenRefresher:
    """Automatically refresh Upstox access tokens"""
    
    TOKEN_URL = "https://api.upstox.com/v2/login/authorization/token"
    
    def __init__(self, secrets_file: str = ".streamlit/secrets.toml"):
        self.secrets_file = Path(secrets_file)
        self.secrets = self._load_secrets()
    
    def _load_secrets(self) -> dict:
        """Load secrets from toml file"""
        try:
            with open(self.secrets_file) as f:
                return toml.load(f)
        except Exception as e:
            logger.error(f"Error loading secrets: {e}")
            return {}
    
    def _save_secrets(self, secrets: dict):
        """Save secrets to toml file"""
        try:
            with open(self.secrets_file, 'w') as f:
                toml.dump(secrets, f)
            logger.info("✅ Secrets updated successfully")
            return True
        except Exception as e:
            logger.error(f"Error saving secrets: {e}")
            return False
    
    def get_token_from_auth_code(self, auth_code: str) -> Optional[Dict[str, Any]]:
        """
        Get access token using authorization code
        Based on: https://upstox.com/developer/api-documentation/get-token/
        
        Args:
            auth_code: Authorization code from OAuth flow
            
        Returns:
            Token response with access_token and extended_token, or None if failed
        """
        if 'upstox' not in self.secrets:
            logger.error("Upstox credentials not found in secrets.toml")
            return None
        
        upstox_config = self.secrets['upstox']
        
        url = self.TOKEN_URL
        headers = {
            'accept': 'application/json',
            'Content-Type': 'application/x-www-form-urlencoded',
        }
        
        data = {
            'code': auth_code,
            'client_id': upstox_config.get('api_key'),
            'client_secret': upstox_config.get('api_secret'),
            'redirect_uri': upstox_config.get('redirect_uri'),
            'grant_type': 'authorization_code',
        }
        
        try:
            response = requests.post(url, headers=headers, data=data)
            
            if response.status_code == 200:
                token_data = response.json()
                
                # Extract tokens
                access_token = token_data.get('access_token')
                extended_token = token_data.get('extended_token')
                
                # Calculate expiration (tokens expire at 3:30 AM next day)
                now = datetime.now()
                # If before 3:30 AM today, expire at 3:30 AM today, else 3:30 AM tomorrow
                if now.hour < 3 or (now.hour == 3 and now.minute < 30):
                    expires_at = now.replace(hour=3, minute=30, second=0, microsecond=0)
                else:
                    expires_at = (now + timedelta(days=1)).replace(hour=3, minute=30, second=0, microsecond=0)
                
                # Update secrets
                upstox_config['access_token'] = access_token
                if extended_token:
                    upstox_config['extended_token'] = extended_token
                upstox_config['expires_at'] = expires_at.isoformat()
                upstox_config['token_updated_at'] = datetime.now().isoformat()
                
                self._save_secrets(self.secrets)
                
                logger.info("✅ Token obtained successfully")
                logger.info(f"   Access token expires at: {expires_at}")
                if extended_token:
                    logger.info("   Extended token available for read-only operations")
                
                return token_data
            else:
                error_data = response.json() if response.text else {}
                logger.error(f"❌ Token request failed: {response.status_code}")
                logger.error(f"   Error: {error_data}")
                return None
                
        except Exception as e:
            logger.error(f"Error getting token: {e}")
            return None
    
    def use_extended_token_if_available(self) -> bool:
        """
        Switch to extended_token if available and access_token is expired
        Extended token is for read-only operations and has longer validity
        
        Returns:
            True if switched to extended_token, False otherwise
        """
        if 'upstox' not in self.secrets:
            return False
        
        upstox_config = self.secrets['upstox']
        extended_token = upstox_config.get('extended_token')
        access_token = upstox_config.get('access_token')
        
        if extended_token and access_token:
            # Check if access_token is expired
            expires_at_str = upstox_config.get('expires_at')
            if expires_at_str:
                try:
                    expires_at = datetime.fromisoformat(expires_at_str)
                    if datetime.now() >= expires_at:
                        # Access token expired, try using extended_token
                        logger.info("🔄 Access token expired, switching to extended_token")
                        upstox_config['access_token'] = extended_token
                        # Extended token might have different expiration, but we'll use it
                        self._save_secrets(self.secrets)
                        return True
                except:
                    pass
        
        return False
    
    def check_token_expiration(self) -> bool:
        """Check if current access token is expired"""
        if 'upstox' not in self.secrets:
            return True
        
        upstox_config = self.secrets['upstox']
        expires_at_str = upstox_config.get('expires_at')
        
        if not expires_at_str:
            # Try to extract from JWT token
            access_token = upstox_config.get('access_token')
            if access_token:
                try:
                    import base64
                    import json
                    parts = access_token.split('.')
                    if len(parts) >= 2:
                        payload = parts[1]
                        payload += '=' * (4 - len(payload) % 4)
                        decoded = base64.urlsafe_b64decode(payload)
                        token_data = json.loads(decoded)
                        exp_timestamp = token_data.get('exp')
                        if exp_timestamp:
                            exp_time = datetime.fromtimestamp(exp_timestamp)
                            expires_at_str = exp_time.isoformat()
                            upstox_config['expires_at'] = expires_at_str
                            self._save_secrets(self.secrets)
                except:
                    pass
        
        if expires_at_str:
            try:
                expires_at = datetime.fromisoformat(expires_at_str)
                is_expired = datetime.now() >= expires_at
                if is_expired:
                    logger.warning(f"⚠️ Access token expired at {expires_at}")
                return is_expired
            except:
                pass
        
        return True  # Assume expired if can't determine
    
    def get_auth_url(self) -> str:
        """
        Generate authorization URL for OAuth flow
        User needs to visit this URL to get authorization code
        """
        if 'upstox' not in self.secrets:
            return ""
        
        upstox_config = self.secrets['upstox']
        api_key = upstox_config.get('api_key')
        redirect_uri = upstox_config.get('redirect_uri')
        
        if not api_key or not redirect_uri:
            return ""
        
        # Upstox OAuth URL format
        import urllib.parse
        params = {
            'response_type': 'code',
            'client_id': api_key,
            'redirect_uri': redirect_uri,
        }
        
        auth_url = f"https://account.upstox.com/developer/apps?{urllib.parse.urlencode(params)}"
        return auth_url
