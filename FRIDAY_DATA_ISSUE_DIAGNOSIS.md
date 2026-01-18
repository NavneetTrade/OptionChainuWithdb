# Friday Data Refresh Issue - Diagnosis & Fix

## 🔍 Root Cause Identified

**Issue:** Data was not refreshed on Friday, January 16, 2026 from 9:15 AM to 2:15 PM IST.

**Root Cause:** Upstox API token expired or became invalid, causing all API calls to fail with error `UDAPI100050: Invalid token used to access API`.

## 📊 Evidence from Cloud Server

### Timeline:
- **Friday 5:00 AM IST (Jan 16)**: Service was running and waiting for market to open
- **Friday 5:00-5:01 AM IST**: Multiple `UDAPI100050: Invalid token` errors started appearing
- **Friday 9:15 AM - 2:15 PM**: Service continued running but **failed to fetch data** due to invalid token
- **Friday 2:15 PM**: Token was refreshed or service restarted, data collection resumed
- **Friday 2:15 PM - 3:30 PM**: Data collection working normally

### Database Evidence:
```
Friday Jan 16, 2026:
- First data: 14:15:26 IST (2:15 PM)
- Last data: 15:30:59 IST (3:30 PM)
- Missing: 9:15 AM - 2:15 PM (5 hours of data)
```

### Log Evidence:
```
Jan 16 05:00:37: ERROR: Invalid token used to access API (UDAPI100050)
Jan 16 05:00:41: ERROR: Failed to get expiry for BANKNIFTY
Jan 16 05:00:43: ERROR: Failed to get expiry for FINNIFTY
... (hundreds of similar errors)
```

## ✅ Fixes Applied

### 1. Enhanced Error Detection
- Added specific detection for token expiration errors (`UDAPI100050`)
- Prominent logging when token errors are detected
- Clear instructions for fixing token issues

### 2. Improved Error Handling
- Token errors now logged with clear warnings
- Service allows more retries for token errors (2x normal limit)
- Better error messages guide user to fix token

### 3. Diagnostic Script
- Created `check_token_status.py` to quickly verify token validity
- Can be run anytime to check if token needs refresh

## 🔧 How to Fix on Cloud Server

### Step 1: Check Current Token Status
```bash
ssh -i ~/oracle_key.pem ubuntu@92.4.74.245
cd ~/OptionChainUsingUpstock
python3 check_token_status.py
```

### Step 2: Update Token (if invalid)
1. Go to Upstox Developer Portal: https://account.upstox.com/developer/apps
2. Generate new access token
3. Update `.streamlit/secrets.toml` on server:
   ```bash
   nano ~/OptionChainUsingUpstock/.streamlit/secrets.toml
   # Update access_token value
   ```

### Step 3: Restart Background Service
```bash
# Kill existing processes
pkill -f background_service.py

# Start fresh
cd ~/OptionChainUsingUpstock
source venv/bin/activate
nohup python background_service.py > /dev/null 2>&1 &
```

### Step 4: Verify Service is Running
```bash
ps aux | grep background_service
tail -f logs/background_service.log
```

## 🛡️ Prevention

### Option 1: Set Up Token Auto-Refresh (Recommended)
- Implement OAuth2 refresh token flow
- Automatically refresh token before expiration
- Requires storing `refresh_token` in secrets

### Option 2: Monitor Token Expiration
- Add cron job to check token daily
- Send alerts when token is about to expire
- Use `check_token_status.py` script

### Option 3: Use Long-Lived Tokens
- Request longer expiration times from Upstox
- Document token expiration date
- Set calendar reminder to refresh before expiration

## 📝 Code Changes Made

**File:** `background_service.py`

1. **Enhanced error detection** for token expiration (lines ~2061-2090)
2. **Better logging** with clear action items
3. **Increased retry limit** for token errors (2x normal)

## 🔍 Monitoring

### Check Service Status:
```bash
# On cloud server
ps aux | grep background_service
tail -50 logs/background_service.log | grep -iE 'token|error|market.*open'
```

### Check Data Collection:
```bash
# Query database for recent data
python3 << 'EOF'
import psycopg2
conn = psycopg2.connect(host='localhost', database='optionchain', 
                        user='optionuser', password='optionpass123')
cur = conn.cursor()
cur.execute("""
    SELECT DATE(timestamp AT TIME ZONE 'Asia/Kolkata') as date_ist,
           COUNT(DISTINCT symbol) as symbols,
           MAX(timestamp AT TIME ZONE 'Asia/Kolkata') as last_update
    FROM option_chain_data
    WHERE timestamp > NOW() - INTERVAL '1 day'
    GROUP BY DATE(timestamp AT TIME ZONE 'Asia/Kolkata')
    ORDER BY date_ist DESC
""")
for row in cur.fetchall():
    print(f"{row[0]}: {row[1]} symbols, last update: {row[2]}")
EOF
```

## ✅ Verification

After applying fixes, verify:
1. ✅ Token is valid (`check_token_status.py` returns ✅)
2. ✅ Service is running (`ps aux | grep background_service`)
3. ✅ Data is being collected (check database for today's data)
4. ✅ No token errors in logs (`grep -i token logs/background_service.log`)

---

**Last Updated:** January 18, 2026
**Issue Date:** January 16, 2026 (Friday)
**Status:** ✅ Root cause identified, fixes applied
