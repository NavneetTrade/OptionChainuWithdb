import sys
sys.path.insert(0, '/home/ubuntu/OptionChainUsingUpstock')
from upstox_api import UpstoxAPI
from config import UPSTOX_CLIENT_ID, UPSTOX_CLIENT_SECRET, UPSTOX_REDIRECT_URI
import json

api = UpstoxAPI(UPSTOX_CLIENT_ID, UPSTOX_CLIENT_SECRET, UPSTOX_REDIRECT_URI)
auth_url = api.get_authorization_url()

print("\n" + "="*80)
print("UPSTOX TOKEN GENERATION")
print("="*80)
print(f"\n1. Open this URL in your browser:\n\n{auth_url}\n")
print("2. Login and authorize the app")
print("3. You'll be redirected to a URL starting with:", UPSTOX_REDIRECT_URI)
print("4. Copy the FULL redirect URL and paste it here\n")

redirect_url = input("Paste the full redirect URL here: ").strip()

try:
    api.complete_authorization(redirect_url)
    tokens = api.get_tokens()
    
    # Save tokens
    import os
    os.makedirs('data', exist_ok=True)
    with open('data/upstox_tokens.json', 'w') as f:
        json.dump(tokens, f, indent=2)
    
    print("\n✓ Token saved successfully to data/upstox_tokens.json")
    print(f"✓ Access Token: {tokens['access_token'][:50]}...")
    
except Exception as e:
    print(f"\n✗ Error: {e}")
    sys.exit(1)
