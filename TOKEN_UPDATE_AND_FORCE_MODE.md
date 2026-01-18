# Access Token Update & Force Mode Implementation

## ✅ Completed Tasks

### 1. Access Token Updated
- **Status:** ✅ Successfully updated on cloud server
- **Token:** Valid (tested and confirmed)
- **User:** Navneet Ranjan
- **Location:** `~/.streamlit/secrets.toml`

### 2. Force Mode Flag Implemented
- **Status:** ✅ Code updated and deployed
- **Flag:** `--force` 
- **Purpose:** Allows service to run during market closed hours for testing

## 🔧 Force Mode Features

### What It Does:
- **Bypasses market hours check** - Service runs regardless of time/day
- **Useful for testing** - Verify service works even when market is closed
- **Logging** - Clear warnings when force mode is active

### Usage:

```bash
# Normal mode (respects market hours)
python background_service.py

# Force mode (runs anytime)
python background_service.py --force
```

### Force Mode Behavior:
1. ✅ Service starts regardless of market hours
2. ✅ Continues fetching data even when market is closed
3. ⚠️  Logs warning messages indicating force mode is active
4. ✅ Useful for testing token validity and API connectivity

## 📋 Verification Steps

### 1. Check Token Status
```bash
ssh -i ~/oracle_key.pem ubuntu@92.4.74.245
cd ~/OptionChainUsingUpstock
python3 check_token_status.py
```

**Expected Output:**
```
✅ Token is VALID
   User: Navneet Ranjan
```

### 2. Test Force Mode
```bash
# Stop any running service
pkill -f background_service.py

# Start with force mode
cd ~/OptionChainUsingUpstock
source venv/bin/activate
python background_service.py --force
```

**Expected Output:**
```
🚀 Starting Option Chain Background Service - REST API MODE [FORCE MODE - Market hours check disabled]
======================================================================
⚠️  FORCE MODE ENABLED: Service will run regardless of market hours
   This is useful for testing but should be disabled in production
...
```

### 3. Verify Data Collection
```bash
# In another terminal, check logs
tail -f logs/background_service.log

# Check database for recent data
python3 << 'EOF'
import psycopg2
conn = psycopg2.connect(host='localhost', database='optionchain', 
                        user='optionuser', password='optionpass123')
cur = conn.cursor()
cur.execute("""
    SELECT symbol, MAX(timestamp AT TIME ZONE 'Asia/Kolkata') as last_update
    FROM option_chain_data
    WHERE timestamp > NOW() - INTERVAL '1 hour'
    GROUP BY symbol
    ORDER BY last_update DESC
    LIMIT 10
""")
for row in cur.fetchall():
    print(f"{row[0]}: {row[1]}")
EOF
```

## 🚀 Production Deployment

### For Production (Normal Mode):
```bash
# Stop service
pkill -f background_service.py

# Start without --force flag (respects market hours)
cd ~/OptionChainUsingUpstock
source venv/bin/activate
nohup python background_service.py > /dev/null 2>&1 &
```

### For Testing (Force Mode):
```bash
# Start with --force flag
cd ~/OptionChainUsingUpstock
source venv/bin/activate
python background_service.py --force
```

## 📝 Code Changes

### Files Modified:
1. ✅ `background_service.py`
   - Added `force_mode` parameter to `__init__()`
   - Modified `_is_market_open()` to return `True` when `force_mode=True`
   - Added `--force` command-line argument
   - Updated logging to show force mode status

### Key Changes:
```python
# Added force_mode parameter
def __init__(self, refresh_interval: int = 180, force_mode: bool = False):
    self.force_mode = force_mode

# Modified market hours check
def _is_market_open(self) -> bool:
    if self.force_mode:
        return True  # Bypass check
    # ... normal market hours logic

# Added CLI argument
parser.add_argument('--force', action='store_true', 
                   help='Force mode: Run service regardless of market hours')
```

## ⚠️ Important Notes

1. **Force Mode is for Testing Only**
   - Don't use `--force` in production
   - Market hours check exists for a reason (API rate limits, data validity)

2. **Token Expiration**
   - Current token expires: Check JWT payload
   - Set reminder to refresh before expiration
   - Use `check_token_status.py` to verify token validity

3. **Service Monitoring**
   - Check logs regularly: `tail -f logs/background_service.log`
   - Monitor for errors: `grep -i error logs/background_service.log`
   - Verify data collection: Check database for recent timestamps

## 🔍 Troubleshooting

### Service Not Starting:
```bash
# Check if service is already running
ps aux | grep background_service

# Check for errors
tail -50 logs/background_service.log | grep -i error
```

### Token Issues:
```bash
# Test token validity
python3 check_token_status.py

# If invalid, update token in .streamlit/secrets.toml
nano .streamlit/secrets.toml
```

### Force Mode Not Working:
```bash
# Verify --force flag is recognized
python background_service.py --help

# Check if force_mode is set
grep -A 5 "FORCE MODE" logs/background_service.log
```

---

**Date:** January 18, 2026
**Status:** ✅ Complete
**Token Status:** ✅ Valid
**Force Mode:** ✅ Implemented
