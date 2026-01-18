# Upstox Token Update Guide - Oracle Cloud

## Overview
Upstox access tokens expire daily at **10:00 PM IST**. This guide shows how to update the token on your Oracle Cloud server.

---

## Prerequisites
- Oracle Cloud VM IP: `92.4.74.245`
- SSH Key: `~/oracle_key.pem`
- New Upstox access token (get from Upstox API dashboard)

---

## Method 1: Quick Update (Recommended)

### Step 1: Get New Token
1. Login to Upstox Developer Console: https://api.upstox.com/
2. Generate new access token
3. Copy the token (starts with `eyJ0eXAi...`)

### Step 2: Update on Cloud Server

Open terminal and run:

```bash
ssh -i ~/oracle_key.pem ubuntu@92.4.74.245
```

Edit the secrets file:
```bash
nano ~/OptionChainUsingUpstock/.streamlit/secrets.toml
```

Update the `access_token` line with your new token:
```toml
[upstox]
access_token="YOUR_NEW_TOKEN_HERE"
api_key="d01c59be-8f1a-46b5-9094-131bcdd05e7b"
api_secret="v6oo0uqmow"
redirect_uri="http://localhost:8501/oauth2callback"
```

Press `Ctrl+O` to save, `Enter` to confirm, `Ctrl+X` to exit.

### Step 3: Restart Services

```bash
sudo systemctl restart option-worker option-dashboard
```

### Step 4: Verify

```bash
sudo systemctl status option-worker
```

Look for `Active: active (running)` status.

Check logs for any errors:
```bash
sudo journalctl -u option-worker -n 20 --no-pager
```

---

## Method 2: One-Line Update (From Local Mac)

Replace `YOUR_NEW_TOKEN` with your actual token:

```bash
ssh -i ~/oracle_key.pem ubuntu@92.4.74.245 "echo '[upstox]
access_token=\"YOUR_NEW_TOKEN\"
api_key=\"d01c59be-8f1a-46b5-9094-131bcdd05e7b\"
api_secret=\"v6oo0uqmow\"
redirect_uri=\"http://localhost:8501/oauth2callback\"' > ~/OptionChainUsingUpstock/.streamlit/secrets.toml && sudo systemctl restart option-worker option-dashboard && echo '✅ Token updated and services restarted'"
```

---

## Verification Steps

### 1. Check Service Status
```bash
ssh -i ~/oracle_key.pem ubuntu@92.4.74.245 'sudo systemctl status option-worker --no-pager | head -15'
```

### 2. Check Recent Logs
```bash
ssh -i ~/oracle_key.pem ubuntu@92.4.74.245 'sudo journalctl -u option-worker -n 30 --no-pager | tail -20'
```

### 3. Verify Data Collection
After 3-5 minutes, check if data is being collected:
```bash
ssh -i ~/oracle_key.pem ubuntu@92.4.74.245 'sudo journalctl -u option-worker -n 50 --no-pager | grep -E "inserted|Gamma|NIFTY" | tail -10'
```

### 4. Check UI
Open browser: http://92.4.74.245/
- Modern UI should show live data
- Gamma Blast table should populate
- Option chain should load

---

## Troubleshooting

### Issue: "Invalid token" errors in logs
**Solution:** Token expired or incorrect. Get fresh token from Upstox and update again.

### Issue: Services not starting
```bash
# Check service logs
ssh -i ~/oracle_key.pem ubuntu@92.4.74.245 'sudo journalctl -u option-worker -n 50 --no-pager'

# Restart all services
ssh -i ~/oracle_key.pem ubuntu@92.4.74.245 'sudo systemctl restart option-worker option-dashboard fastapi-backend nextjs-frontend'
```

### Issue: UI shows "OFFLINE"
**Solution:** 
1. Check if services are running: `sudo systemctl status option-worker`
2. Wait 2-3 minutes for data collection to start
3. Hard refresh browser: `Cmd + Shift + R` (Mac) or `Ctrl + Shift + R` (Windows)

---

## Token Expiry Schedule

- **Token Validity**: ~24 hours
- **Expires**: Daily at 10:00 PM IST
- **Update Before**: 9:30 PM IST (to avoid service disruption)
- **Market Hours**: 9:15 AM - 3:30 PM IST (Mon-Fri)

---

## Quick Reference Commands

### Connect to Server
```bash
ssh -i ~/oracle_key.pem ubuntu@92.4.74.245
```

### View Secrets File
```bash
cat ~/OptionChainUsingUpstock/.streamlit/secrets.toml
```

### Restart Services
```bash
sudo systemctl restart option-worker option-dashboard
```

### Check All Services Status
```bash
sudo systemctl status option-worker option-dashboard fastapi-backend nextjs-frontend
```

### View Live Logs
```bash
sudo journalctl -u option-worker -f
```

---

## Notes

1. **Token Format**: Always starts with `eyJ0eXAi...`
2. **Keep Quotes**: Token must be wrapped in double quotes `"..."`
3. **No Spaces**: Ensure no extra spaces before/after the token
4. **Service Restart**: Always restart services after updating token
5. **Timing**: Update token before market hours (ideally evening before trading day)

---

## Emergency Contact

If services fail to start after token update:
1. SSH to server
2. Check logs: `sudo journalctl -u option-worker -n 100`
3. Verify token validity at Upstox dashboard
4. Ensure all 4 services are running: `sudo systemctl status option-*`

---

**Last Updated**: January 9, 2026  
**Server**: AlgoOption (92.4.74.245)  
**Platform**: Oracle Cloud Always Free Tier
