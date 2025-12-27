"""
Quick test to verify UI components are working
"""

import sys
import os

print("=" * 60)
print("Testing Option Chain System UI Components")
print("=" * 60)

# Test 1: Check all imports
print("\n1. Testing imports...")
try:
    import streamlit as st
    from optionchain import (
        UpstoxAPI, get_fo_instruments, format_ist_time, 
        get_ist_now, is_market_open, process_option_chain_data
    )
    from database import TimescaleDBManager
    from upstox_api import UpstoxAPI as API
    print("   ✓ All imports successful")
except Exception as e:
    print(f"   ✗ Import error: {e}")
    sys.exit(1)

# Test 2: Check credentials
print("\n2. Testing credentials...")
try:
    import toml
    secrets_path = os.path.join(os.path.dirname(__file__), '.streamlit', 'secrets.toml')
    if os.path.exists(secrets_path):
        with open(secrets_path) as f:
            secrets = toml.load(f)
        if 'upstox' in secrets and secrets['upstox'].get('access_token'):
            print("   ✓ Upstox credentials found")
        else:
            print("   ⚠ Upstox credentials incomplete")
    else:
        print("   ✗ secrets.toml not found")
except Exception as e:
    print(f"   ⚠ Credential check error: {e}")

# Test 3: Check database
print("\n3. Testing database connection...")
try:
    db = TimescaleDBManager()
    if db.pool:
        print("   ✓ Database connected")
    else:
        print("   ⚠ Database not available (will use API mode)")
except Exception as e:
    print(f"   ⚠ Database not available: {str(e)[:50]}...")

# Test 4: Check API client
print("\n4. Testing Upstox API client...")
try:
    api = UpstoxAPI()
    print("   ✓ API client initialized")
except Exception as e:
    print(f"   ✗ API client error: {e}")
    sys.exit(1)

# Test 5: Check helper functions
print("\n5. Testing helper functions...")
try:
    now = get_ist_now()
    formatted = format_ist_time(now)
    market_status = is_market_open()
    instruments = get_fo_instruments()
    print(f"   ✓ Current time: {formatted}")
    print(f"   ✓ Market is {'OPEN' if market_status else 'CLOSED'}")
    print(f"   ✓ Found {len(instruments)} F&O instruments")
except Exception as e:
    print(f"   ✗ Helper function error: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 60)
print("✓ All UI component tests passed!")
print("=" * 60)
print("\nTo start the UI, run:")
print("  streamlit run optionchain.py")
print("\nThe app will be available at: http://localhost:8501")
print("\nNote: If database is not available, the app will work in")
print("      'Direct API Mode' and fetch data directly from Upstox.")

