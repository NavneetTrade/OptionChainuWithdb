#!/usr/bin/env python3
"""
Helper script to get new Upstox access token using authorization code
Based on: https://upstox.com/developer/api-documentation/get-token/

Usage:
    python get_new_token.py <authorization_code>
    
Or run interactively:
    python get_new_token.py
"""

import sys
import os
from pathlib import Path
from auto_token_refresh import UpstoxTokenRefresher

def main():
    print("=" * 70)
    print("🔐 Upstox Token Getter (API v2)")
    print("Based on: https://upstox.com/developer/api-documentation/get-token/")
    print("=" * 70)
    print()
    
    # Initialize refresher
    refresher = UpstoxTokenRefresher()
    
    # Get authorization code
    if len(sys.argv) > 1:
        auth_code = sys.argv[1]
    else:
        print("📋 To get an authorization code:")
        print("   1. Visit: https://account.upstox.com/developer/apps")
        print("   2. Complete OAuth flow")
        print("   3. Copy the authorization code from the redirect URL")
        print()
        auth_code = input("👉 Enter authorization code: ").strip()
    
    if not auth_code:
        print("❌ Authorization code is required")
        return
    
    print()
    print("🔄 Getting access token from Upstox API...")
    print()
    
    # Get token
    token_data = refresher.get_token_from_auth_code(auth_code)
    
    if token_data:
        print()
        print("=" * 70)
        print("✅ SUCCESS! Token obtained and saved to secrets.toml")
        print("=" * 70)
        print()
        print("📋 Token Details:")
        print(f"   Access Token: {token_data.get('access_token', '')[:30]}...")
        if token_data.get('extended_token'):
            print(f"   Extended Token: {token_data.get('extended_token', '')[:30]}...")
        print(f"   Expires At: {refresher.secrets['upstox'].get('expires_at', 'N/A')}")
        print()
        print("✅ The system will automatically use these tokens")
        print("   Extended token will be used when access token expires")
        print()
    else:
        print()
        print("=" * 70)
        print("❌ FAILED to get token")
        print("=" * 70)
        print()
        print("Possible reasons:")
        print("  1. Authorization code is invalid or expired")
        print("  2. API credentials (api_key/api_secret) are incorrect")
        print("  3. Redirect URI doesn't match")
        print()
        print("Check your secrets.toml and try again")

if __name__ == "__main__":
    main()
