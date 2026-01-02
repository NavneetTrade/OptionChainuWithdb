"""
Token Manager - Automatic token loading and refresh
Works with token_refresh_service.py for seamless authentication
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
    
    def __init__(self, token_file: str = None):
        """
        Initialize token manager
        
        Args:
            token_file: Path to token JSON file (default: from env or data/upstox_tokens.json)
        """
        if token_file is None:
            token_file = os.getenv('TOKEN_FILE', 'data/upstox_tokens.json')
        
        self.token_file = Path(token_file)
        self.token_file.parent.mkdir(parents=True, exist_ok=True)
        
        self._access_token = None
        self._refresh_token = None
        self._expires_at = None
        self._last_load = None
    
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
            if not self.token_file.exists():
                logger.warning(f"Token file not found: {self.token_file}")
                logger.warning("Run initial_login.py to create tokens")
                return None, None
            
            with open(self.token_file, 'r') as f:
                data = json.load(f)
            
            self._access_token = data.get('access_token')
            self._refresh_token = data.get('refresh_token')
            self._expires_at = data.get('expires_at')
            self._last_load = datetime.now()
            
            # Check if expired
            if self._is_expired():
                logger.warning("⚠️ Access token expired. Token refresh service should update it soon.")
                logger.warning("If tokens keep expiring, check: sudo systemctl status option-chain-token-refresh")
            
            return self._access_token, self._refresh_token
            
        except Exception as e:
            logger.error(f"Error loading tokens: {e}")
            return None, None
    
    def get_access_token(self) -> Optional[str]:
        """Get current access token (loads from file if needed)"""
        access_token, _ = self.load_tokens()
        return access_token
    
    def get_refresh_token(self) -> Optional[str]:
        """Get current refresh token"""
        _, refresh_token = self.load_tokens()
        return refresh_token
    
    def _is_expired(self) -> bool:
        """Check if token is expired"""
        if not self._expires_at:
            return False
        try:
            expiry = datetime.fromisoformat(self._expires_at)
            return datetime.now() >= expiry
        except:
            return False
    
    def save_tokens(self, access_token: str, refresh_token: str, expires_in: int = 86400):
        """
        Save tokens to file (usually done by token_refresh_service)
        
        Args:
            access_token: New access token
            refresh_token: New refresh token
            expires_in: Token validity in seconds (default 24 hours)
        """
        try:
            expires_at = (datetime.now() + timedelta(seconds=expires_in)).isoformat()
            data = {
                'access_token': access_token,
                'refresh_token': refresh_token,
                'expires_at': expires_at,
                'updated_at': datetime.now().isoformat()
            }
            
            with open(self.token_file, 'w') as f:
                json.dump(data, f, indent=2)
            
            # Update cache
            self._access_token = access_token
            self._refresh_token = refresh_token
            self._expires_at = expires_at
            self._last_load = datetime.now()
            
            logger.info("✅ Tokens saved successfully")
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

def get_access_token() -> Optional[str]:
    """Quick helper to get current access token"""
    return get_token_manager().get_access_token()
