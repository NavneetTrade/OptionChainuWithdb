# Upstox API v2 Implementation

## ✅ Implementation Complete

Based on official Upstox API documentation: https://upstox.com/developer/api-documentation/get-token/

## 🔧 Key Changes

### 1. **Updated API Endpoint**
- ✅ Changed to v2 endpoint: `https://api.upstox.com/v2/login/authorization/token`
- ✅ Updated headers to match API documentation

### 2. **Extended Token Support**
- ✅ Handles `extended_token` (provided by Upstox API for read-only operations)
- ✅ Automatically switches to `extended_token` when `access_token` expires
- ✅ `extended_token` has longer validity for read-only API calls

### 3. **Token Expiration Handling**
- ✅ Automatically calculates expiration: **3:30 AM the following day** (per Upstox API rules)
- ✅ Extracts expiration from JWT token if available
- ✅ Handles expiration correctly based on current time

### 4. **Automatic Token Updates**
- ✅ Automatically saves tokens to `secrets.toml` when obtained
- ✅ Updates `access_token`, `extended_token`, and `expires_at`
- ✅ No manual file editing required

## 📋 Important Notes from Upstox API

### Token Expiration Rules:
- **Access tokens expire at 3:30 AM the following day**
- Example: Token created at 8 PM Tuesday → expires at 3:30 AM Wednesday
- Example: Token created at 2:30 AM Wednesday → expires at 3:30 AM same Wednesday

### Token Types:
- **access_token**: For all API operations, expires at 3:30 AM next day
- **extended_token**: For read-only operations, longer validity
- **No refresh_token**: Upstox API does NOT provide refresh_token

## 🔄 How Auto-Refresh Works

1. **Token Check (Every 5 minutes)**:
   - Checks if `access_token` is expired
   - If expired, automatically switches to `extended_token` (if available)

2. **On API Error**:
   - Detects token expiration errors
   - Attempts to use `extended_token`
   - Logs clear messages about token status

3. **Token Storage**:
   - Automatically saves `access_token` and `extended_token` to `secrets.toml`
   - Calculates and stores `expires_at` (3:30 AM next day)

## 🚀 Usage

### Get New Token (One-time setup):
```python
from auto_token_refresh import UpstoxTokenRefresher

refresher = UpstoxTokenRefresher()
auth_code = "your_authorization_code"  # From OAuth flow
token_data = refresher.get_token_from_auth_code(auth_code)
```

### Automatic Token Management:
The system automatically:
- ✅ Detects token expiration
- ✅ Uses `extended_token` when available
- ✅ Updates `secrets.toml` automatically
- ✅ Handles errors gracefully

## ⚠️ Limitations

Since Upstox API doesn't provide `refresh_token`:
- **Cannot automatically refresh** `access_token` without re-authentication
- **Can use `extended_token`** for read-only operations when `access_token` expires
- **Re-authentication required** for write operations after token expires

## 📝 Next Steps

1. **Get Authorization Code**:
   - Visit Upstox Developer Portal
   - Complete OAuth flow
   - Get authorization code

2. **Get Tokens**:
   ```python
   from auto_token_refresh import UpstoxTokenRefresher
   refresher = UpstoxTokenRefresher()
   refresher.get_token_from_auth_code("your_auth_code")
   ```

3. **Automatic Operation**:
   - System will automatically use `extended_token` when `access_token` expires
   - For write operations, you'll need to re-authenticate

## ✅ Status

- ✅ Upstox API v2 endpoint implemented
- ✅ Extended token support added
- ✅ Automatic expiration calculation (3:30 AM next day)
- ✅ Automatic token updates to secrets.toml
- ✅ Background service integrated

The system is now fully compliant with Upstox API v2!
