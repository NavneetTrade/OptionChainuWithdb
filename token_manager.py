"""
Token Manager - Automatic token loading and refresh
Works with token_refresh_service.py for seamless authentication
Now includes automatic token refresh when expired
"""

import os
import json
import logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

class TokenManager:
    """Manages Upstox tokens with automatic loading from file"""
    
    def __init__(self, token_file: str = None, secrets_file: str = None):
        """
        Initialize token manager
        
        Args:
            token_file: Path to token JSON file (default: from env or data/upstox_tokens.json)
            secrets_file: Path to secrets.toml file (optional, for fallback)
        """
        if token_file is None:
            token_file = os.getenv('TOKEN_FILE', 'data/upstox_tokens.json')
        
        self.token_file = Path(token_file)
        self.token_file.parent.mkdir(parents=True, exist_ok=True)
        
        # Also check secrets.toml as fallback
        if secrets_file is None:
            secrets_file = os.path.join(os.path.dirname(__file__), '.streamlit', 'secrets.toml')
        self.secrets_file = Path(secrets_file) if secrets_file else None
        
        self._access_token = None
        self._refresh_token = None
        self._expires_at = None
        self._last_load = None
        self._token_source = None  # Track where token was loaded from: 'file' or 'secrets'
    
    def load_tokens(self, max_age_seconds: int = 60) -> Tuple[Optional[str], Optional[str]]:
        """
        Load tokens from file with caching
        
        Args:
            max_age_seconds: Maximum age of cached tokens before reloading (default 60s)
            
        Returns:
            Tuple of (access_token, refresh_token)
        """
        # Use cached tokens if recent
        if (self._last_load and 
            (datetime.now() - self._last_load).total_seconds() < max_age_seconds and
            self._access_token):
            return self._access_token, self._refresh_token
        
        # Load from file
        try:
            # Try token file first
            if self.token_file.exists():
                with open(self.token_file, 'r') as f:
                    data = json.load(f)
                
                self._access_token = data.get('access_token')
                self._refresh_token = data.get('refresh_token')
                self._expires_at = data.get('expires_at')
                self._last_load = datetime.now()
                self._token_source = 'file'
                
                # Check if expired
                if self._is_expired():
                    logger.warning("⚠️ Access token expired. Will attempt auto-refresh if credentials available.")
                
                return self._access_token, self._refresh_token
            
            # Fallback to secrets.toml if token file doesn't exist
            elif self.secrets_file and self.secrets_file.exists():
                try:
                    import toml
                    with open(self.secrets_file, 'r') as f:
                        secrets = toml.load(f)
                    
                    if 'upstox' in secrets:
                        self._access_token = secrets['upstox'].get('access_token')
                        self._refresh_token = secrets['upstox'].get('refresh_token')
                        
                        # Extract expiration from JWT token if available
                        expires_at_str = secrets['upstox'].get('expires_at')
                        if not expires_at_str and self._access_token:
                            # Try to extract expiration from JWT token
                            try:
                                import base64
                                # json is already imported at top of file
                                parts = self._access_token.split('.')
                                if len(parts) >= 2:
                                    payload = parts[1]
                                    # Add padding if needed
                                    payload += '=' * (4 - len(payload) % 4)
                                    decoded = base64.urlsafe_b64decode(payload)
                                    token_data = json.loads(decoded)
                                    exp_timestamp = token_data.get('exp')
                                    if exp_timestamp:
                                        exp_time = datetime.fromtimestamp(exp_timestamp)
                                        expires_at_str = exp_time.isoformat()
                                        logger.debug(f"Extracted expiration from JWT: {expires_at_str}")
                            except Exception as e:
                                logger.debug(f"Could not extract expiration from JWT: {e}")
                        
                        if expires_at_str:
                            self._expires_at = expires_at_str
                        else:
                            # No expiry info - assume expired for safety
                            self._expires_at = None
                        self._last_load = datetime.now()
                        self._token_source = 'secrets'
                        
                        logger.info("Loaded tokens from secrets.toml (fallback)")
                        return self._access_token, self._refresh_token
                except ImportError:
                    logger.warning("toml module not available, cannot read secrets.toml")
                except Exception as e:
                    logger.warning(f"Error reading secrets.toml: {e}")
            
            logger.warning(f"Token file not found: {self.token_file}")
            if self.secrets_file:
                logger.warning(f"Secrets file also not found: {self.secrets_file}")
            logger.warning("Run initial_login.py to create tokens or update secrets.toml")
            return None, None
            
        except Exception as e:
            logger.error(f"Error loading tokens: {e}")
            return None, None
    
    def get_access_token(self, auto_refresh: bool = True, api_key: str = None, api_secret: str = None) -> Optional[str]:
        """
        Get current access token (loads from file if needed)
        Automatically refreshes if expired (if auto_refresh=True and credentials provided)
        
        Args:
            auto_refresh: If True, automatically refresh token if expired
            api_key: Upstox API key (required for auto-refresh)
            api_secret: Upstox API secret (required for auto-refresh)
            
        Returns:
            Access token string or None if unavailable
        """
        access_token, refresh_token = self.load_tokens()
        
        # Check if token is expired and auto-refresh if enabled
        if auto_refresh and self._is_expired():
            logger.warning("⚠️ Access token expired or expiring soon")
            
            # Try to use extended_token if available (Upstox API provides this for read-only operations)
            if self._token_source == 'secrets':
                try:
                    from auto_token_refresh import UpstoxTokenRefresher
                    refresher = UpstoxTokenRefresher()
                    if refresher.use_extended_token_if_available():
                        logger.info("✅ Switched to extended_token for read-only operations")
                        # Reload tokens
                        access_token, _ = self.load_tokens(max_age_seconds=0)
                        return access_token
                except Exception as e:
                    logger.debug(f"Could not use extended_token: {e}")
            
            # Try traditional refresh_token approach (if available)
            if not refresh_token:
                # Try to get from token file if we loaded from secrets
                if self._token_source == 'secrets':
                    try:
                        token_file_data = json.load(open(self.token_file)) if self.token_file.exists() else {}
                        refresh_token = token_file_data.get('refresh_token')
                        if refresh_token:
                            logger.info("📦 Found refresh_token in token file, using it for auto-refresh")
                            # Update secrets with refresh_token for future use
                            self._save_refresh_token_to_secrets(refresh_token)
                    except:
                        pass
            
            if refresh_token and api_key and api_secret:
                logger.info("🔄 Access token expired. Attempting automatic refresh using refresh_token...")
                if self._refresh_token(api_key, api_secret, refresh_token):
                    # Reload tokens after refresh
                    access_token, _ = self.load_tokens(max_age_seconds=0)  # Force reload
                    logger.info("✅ Token automatically refreshed successfully")
                    logger.info(f"   New access_token: {access_token[:20] if access_token else 'None'}...")
                else:
                    logger.error("❌ Failed to automatically refresh token using refresh_token")
                    logger.error("   Note: Upstox API may not support refresh_token. You may need to re-authenticate.")
            else:
                logger.warning("⚠️ Token expired but cannot auto-refresh:")
                if not refresh_token:
                    logger.warning("   - No refresh_token available")
                    logger.warning("   - Upstox API tokens expire at 3:30 AM daily")
                    logger.warning("   - You may need to re-authenticate to get a new token")
                    logger.warning("   - Or use extended_token if available for read-only operations")
                if not api_key or not api_secret:
                    logger.warning("   - Missing api_key or api_secret")
        
        return access_token
    
    def _save_refresh_token_to_secrets(self, refresh_token: str):
        """Automatically save refresh_token to secrets.toml if it was loaded from there"""
        if self._token_source == 'secrets' and self.secrets_file and self.secrets_file.exists():
            try:
                import toml
                with open(self.secrets_file, 'r') as f:
                    secrets = toml.load(f)
                
                if 'upstox' not in secrets:
                    secrets['upstox'] = {}
                
                secrets['upstox']['refresh_token'] = refresh_token
                
                with open(self.secrets_file, 'w') as f:
                    toml.dump(secrets, f)
                
                logger.info("✅ Automatically saved refresh_token to secrets.toml")
                self._refresh_token = refresh_token  # Update cache
            except Exception as e:
                logger.debug(f"Could not save refresh_token to secrets.toml: {e}")
    
    def _refresh_token(self, api_key: str, api_secret: str, refresh_token: str) -> bool:
        """
        Refresh access token using refresh token
        
        Args:
            api_key: Upstox API key
            api_secret: Upstox API secret
            refresh_token: Current refresh token
            
        Returns:
            True if refresh successful, False otherwise
        """
        try:
            from upstox_api import UpstoxAPI
            
            api = UpstoxAPI()
            success, result = api.refresh_access_token(api_key, api_secret, refresh_token)
            
            if success:
                new_access_token = result.get('access_token')
                new_refresh_token = result.get('refresh_token', refresh_token)
                expires_in = result.get('expires_in', 86400)  # Default 24 hours
                
                # Save new tokens (update secrets.toml if loaded from there)
                self.save_tokens(new_access_token, new_refresh_token, expires_in, update_secrets=True)
                logger.info(f"✅ Token refreshed and saved to {self._token_source}")
                return True
            else:
                logger.error(f"Token refresh failed: {result}")
                return False
                
        except Exception as e:
            logger.error(f"Error during token refresh: {e}")
            return False
    
    def get_refresh_token(self) -> Optional[str]:
        """Get current refresh token"""
        _, refresh_token = self.load_tokens()
        return refresh_token
    
    def _is_expired(self, buffer_minutes: int = 5) -> bool:
        """
        Check if token is expired or will expire soon
        
        Args:
            buffer_minutes: Refresh if token expires within this many minutes (default 5)
            
        Returns:
            True if expired or expiring soon, False otherwise
        """
        if not self._expires_at:
            return True  # If no expiry info, assume expired for safety
        
        try:
            expiry = datetime.fromisoformat(self._expires_at)
            # Refresh if expired or expiring within buffer time
            return datetime.now() >= (expiry - timedelta(minutes=buffer_minutes))
        except:
            return True  # If can't parse, assume expired for safety
    
    def save_tokens(self, access_token: str, refresh_token: str, expires_in: int = 86400, update_secrets: bool = True):
        """
        Save tokens to file or secrets.toml (depending on where they were loaded from)
        
        Args:
            access_token: New access token
            refresh_token: New refresh token
            expires_in: Token validity in seconds (default 24 hours)
            update_secrets: If True, update secrets.toml if token was loaded from there
        """
        try:
            expires_at = (datetime.now() + timedelta(seconds=expires_in)).isoformat()
            
            # Update cache first
            self._access_token = access_token
            self._refresh_token = refresh_token
            self._expires_at = expires_at
            self._last_load = datetime.now()
            
            # Save to the same source where token was loaded from
            if update_secrets and self._token_source == 'secrets' and self.secrets_file and self.secrets_file.exists():
                # Save to secrets.toml
                try:
                    import toml
                    with open(self.secrets_file, 'r') as f:
                        secrets = toml.load(f)
                    
                    if 'upstox' not in secrets:
                        secrets['upstox'] = {}
                    
                    secrets['upstox']['access_token'] = access_token
                    if refresh_token:  # Only update refresh_token if provided (may not exist in Upstox API)
                        secrets['upstox']['refresh_token'] = refresh_token
                    secrets['upstox']['expires_at'] = expires_at
                    # Note: extended_token is handled separately if available
                    
                    with open(self.secrets_file, 'w') as f:
                        toml.dump(secrets, f)
                    
                    logger.info(f"✅ Tokens saved to secrets.toml successfully")
                    logger.info(f"   Updated access_token and expires_at")
                    if refresh_token:
                        logger.info(f"   Updated refresh_token")
                    return True
                except ImportError:
                    logger.warning("toml module not available, cannot save to secrets.toml")
                    # Fall through to save to JSON file
                except Exception as e:
                    logger.warning(f"Error saving to secrets.toml: {e}, falling back to JSON file")
                    # Fall through to save to JSON file
            
            # Save to JSON file (default or fallback)
            data = {
                'access_token': access_token,
                'refresh_token': refresh_token,
                'expires_at': expires_at,
                'updated_at': datetime.now().isoformat()
            }
            
            with open(self.token_file, 'w') as f:
                json.dump(data, f, indent=2)
            
            logger.info(f"✅ Tokens saved to {self.token_file} successfully")
            return True
            
        except Exception as e:
            logger.error(f"Error saving tokens: {e}")
            return False

# Global token manager instance
_token_manager = None

def get_token_manager() -> TokenManager:
    """Get global token manager instance"""
    global _token_manager
    if _token_manager is None:
        _token_manager = TokenManager()
    return _token_manager

def get_access_token(auto_refresh: bool = True, api_key: str = None, api_secret: str = None) -> Optional[str]:
    """
    Quick helper to get current access token with optional auto-refresh
    
    Args:
        auto_refresh: If True, automatically refresh token if expired
        api_key: Upstox API key (required for auto-refresh)
        api_secret: Upstox API secret (required for auto-refresh)
        
    Returns:
        Access token string or None if unavailable
    """
    return get_token_manager().get_access_token(auto_refresh=auto_refresh, api_key=api_key, api_secret=api_secret)
