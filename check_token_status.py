#!/usr/bin/env python3
"""Quick script to check Upstox API token status"""
import re
import requests
from pathlib import Path

def get_token_from_secrets():
    secrets_paths = [Path('.streamlit/secrets.toml'), Path('secrets.toml')]
    
    for secrets_path in secrets_paths:
        if secrets_path.exists():
            content = secrets_path.read_text()
            # Simple regex to extract access_token
            match = re.search(r'access_token\s*=\s*["']([^"']+)["']', content)
            if match:
                return match.group(1)
    return None

try:
    access_token = get_token_from_secrets()
    
    if not access_token:
        print('❌ No access token found in secrets.toml')
        exit(1)
    
    print(f'🔍 Testing token: {access_token[:20]}...')
    
    # Test token by making a simple API call
    headers = {
        'Authorization': f'Bearer {access_token}',
        'Accept': 'application/json'
    }
    
    # Try to get user profile (simple endpoint)
    response = requests.get('https://api.upstox.com/v2/user/profile', headers=headers, timeout=10)
    
    if response.status_code == 200:
        print('✅ Token is VALID')
        try:
            data = response.json()
            if 'data' in data:
                print(f'   User: {data["data"].get("user_name", "N/A")}')
        except:
            pass
    elif response.status_code == 401:
        print('❌ Token is INVALID or EXPIRED (401 Unauthorized)')
        print('   Error: UDAPI100050 - Invalid token used to access API')
        print('   ACTION: Update access_token in .streamlit/secrets.toml')
        try:
            error_data = response.json()
            print(f'   Details: {error_data}')
        except:
            pass
    else:
        print(f'⚠️  Unexpected response: {response.status_code}')
        print(f'   Response: {response.text[:200]}')
        
except FileNotFoundError:
    print('❌ secrets.toml file not found')
except Exception as e:
    print(f'❌ Error checking token: {e}')
    import traceback
    traceback.print_exc()
