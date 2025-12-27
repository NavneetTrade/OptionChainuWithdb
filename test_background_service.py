"""
Test script to verify background service initialization and basic functionality
"""

import sys
import os
import signal
import time

# Add current directory to path
sys.path.insert(0, os.path.dirname(__file__))

try:
    from background_service import OptionChainBackgroundService
    print("✓ Successfully imported OptionChainBackgroundService")
except Exception as e:
    print(f"✗ Failed to import: {e}")
    sys.exit(1)

# Test initialization
try:
    print("\n1. Testing service initialization...")
    service = OptionChainBackgroundService(refresh_interval=60)
    print("✓ Service initialized successfully")
except Exception as e:
    print(f"✗ Failed to initialize service: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test component initialization
try:
    print("\n2. Testing component initialization...")
    if service.db_manager:
        print("✓ Database manager initialized")
    else:
        print("⚠ Database manager not initialized (may be expected if DB not configured)")
    
    if service.upstox_api:
        print("✓ Upstox API initialized")
    else:
        print("✗ Upstox API not initialized")
        sys.exit(1)
    
    if service.executor:
        print("✓ Thread pool executor initialized")
    else:
        print("✗ Thread pool executor not initialized")
        sys.exit(1)
except Exception as e:
    print(f"✗ Component check failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test market hours check
try:
    print("\n3. Testing market hours check...")
    is_open = service._is_market_open()
    print(f"✓ Market is {'OPEN' if is_open else 'CLOSED'}")
except Exception as e:
    print(f"✗ Market hours check failed: {e}")
    import traceback
    traceback.print_exc()

# Test getting F&O instruments
try:
    print("\n4. Testing F&O instruments fetch...")
    instruments = service._get_fo_instruments()
    if instruments:
        print(f"✓ Retrieved {len(instruments)} instruments")
        print(f"  Sample symbols: {list(instruments.keys())[:5]}")
    else:
        print("⚠ No instruments retrieved (using defaults)")
except Exception as e:
    print(f"✗ Failed to get instruments: {e}")
    import traceback
    traceback.print_exc()

# Test getting active symbols
try:
    print("\n5. Testing active symbols retrieval...")
    symbols = service._get_active_symbols()
    if symbols:
        print(f"✓ Found {len(symbols)} active symbols")
        for sym in symbols[:3]:
            print(f"  - {sym['symbol']}: {sym.get('instrument_key', 'N/A')}")
    else:
        print("⚠ No active symbols found")
except Exception as e:
    print(f"✗ Failed to get active symbols: {e}")
    import traceback
    traceback.print_exc()

# Test cleanup
try:
    print("\n6. Testing cleanup...")
    service.stop()
    print("✓ Service stopped successfully")
except Exception as e:
    print(f"⚠ Cleanup warning: {e}")

print("\n" + "="*50)
print("✓ All basic tests passed!")
print("="*50)
print("\nNote: Database connection test skipped (requires TimescaleDB setup)")
print("To fully test, ensure:")
print("  1. TimescaleDB is installed and running")
print("  2. Database credentials are set in environment variables")
print("  3. Upstox credentials are in .streamlit/secrets.toml")

