# Automatic Token Refresh Implementation

## ✅ Overview

The system now automatically refreshes Upstox API access tokens when they expire, eliminating the need for manual token updates.

## 🔧 Implementation Details

### 1. Enhanced Token Manager (`token_manager.py`)

**New Features:**
- **Automatic Token Refresh**: `get_access_token()` now accepts `auto_refresh`, `api_key`, and `api_secret` parameters
- **Expiration Detection**: Checks if token is expired or will expire within 5 minutes (buffer)
- **Secrets.toml Fallback**: Can read tokens from `secrets.toml` if token file doesn't exist
- **Automatic Refresh**: Calls Upstox API to refresh token using refresh token when expired

**Key Methods:**
```python
# Get token with auto-refresh
access_token = token_manager.get_access_token(
    auto_refresh=True,
    api_key=api_key,
    api_secret=api_secret
)

# Internal refresh method
token_manager._refresh_token(api_key, api_secret, refresh_token)
```

### 2. Background Service Integration (`background_service.py`)

**Changes:**
- Initializes `TokenManager` on startup
- Automatically refreshes token during initialization
- Periodically checks token status every 5 minutes
- Automatically refreshes token when API returns `UDAPI100050` (Invalid token) error
- Resets error count on successful token refresh

**Key Features:**
- **Proactive Refresh**: Checks token every 5 minutes and refreshes if needed
- **Reactive Refresh**: Automatically refreshes when API returns token expiration error
- **Error Recovery**: Resets consecutive error count after successful refresh

## 📋 How It Works

### Token Refresh Flow

1. **Initialization**:
   - Background service loads credentials from `secrets.toml`
   - Initializes `TokenManager`
   - Attempts to get access token with auto-refresh enabled

2. **Periodic Checks** (Every 5 minutes):
   - Checks if token is expired or expiring soon
   - If expired, automatically refreshes using refresh token
   - Updates `upstox_api.access_token` with new token

3. **Error-Based Refresh**:
   - When API returns `UDAPI100050` (Invalid token) error
   - Automatically attempts token refresh
   - If successful, continues with new token
   - If failed, logs error and continues retrying

### Token Storage

The system checks tokens in this order:
1. **Token File** (`data/upstox_tokens.json`) - Primary source
2. **Secrets File** (`.streamlit/secrets.toml`) - Fallback

## 🔑 Required Configuration

### secrets.toml

Make sure your `secrets.toml` contains:

```toml
[upstox]
access_token = "your_access_token"
api_key = "your_api_key"
api_secret = "your_api_secret"
redirect_uri = "your_redirect_uri"
```

**Important**: The `refresh_token` should be stored in the token file (`data/upstox_tokens.json`) or in `secrets.toml` under `upstox.refresh_token`.

## 🚀 Benefits

1. **Zero Manual Intervention**: Tokens refresh automatically
2. **Continuous Operation**: Service continues running even when tokens expire
3. **Error Recovery**: Automatically recovers from token expiration errors
4. **Proactive Management**: Refreshes tokens before they expire (5-minute buffer)

## 📝 Logging

The system logs token refresh activities:

- `🔄 Access token expired. Attempting automatic refresh...` - Starting refresh
- `✅ Token automatically refreshed!` - Refresh successful
- `❌ Failed to automatically refresh token` - Refresh failed
- `⚠️ Token expired but auto-refresh requires api_key and api_secret` - Missing credentials

## ⚠️ Important Notes

1. **Refresh Token Required**: Auto-refresh requires a valid `refresh_token`
2. **API Credentials**: `api_key` and `api_secret` must be in `secrets.toml`
3. **Token File**: If using token file, ensure it has `refresh_token` field
4. **Fallback**: If auto-refresh fails, service will log error but continue retrying

## 🧪 Testing

To test auto-refresh:

1. **Simulate Expired Token**: Set `expires_at` in token file to past date
2. **Run Background Service**: Service should automatically refresh token
3. **Check Logs**: Look for refresh messages in logs

## 📊 Monitoring

Monitor token refresh in logs:
```bash
tail -f background_service.log | grep -i "token\|refresh"
```

## 🔄 Manual Refresh (If Needed)

If auto-refresh fails, you can still manually refresh:

1. Update `access_token` in `secrets.toml`
2. Or use the token refresh endpoint (if available)
3. Restart the background service

## ✅ Status

- ✅ Token Manager enhanced with auto-refresh
- ✅ Background Service integrated with auto-refresh
- ✅ Periodic token checks (every 5 minutes)
- ✅ Error-based token refresh on API errors
- ✅ Secrets.toml fallback support
- ✅ Comprehensive logging

The system is now fully automated for token management!
