# Token Auto-Refresh Troubleshooting

## Issue: Auto-refresh not working

### Problem
The auto-refresh feature requires a `refresh_token` to work. If `refresh_token` is missing from `secrets.toml`, auto-refresh cannot function.

### Current Status
Based on the check:
- ✅ `access_token` - Present in secrets.toml
- ❌ `refresh_token` - **MISSING** from secrets.toml
- ✅ `api_key` - Present
- ✅ `api_secret` - Present

### Solution

You need to add `refresh_token` to your `secrets.toml`:

```toml
[upstox]
access_token = "your_access_token"
refresh_token = "your_refresh_token"  # <-- ADD THIS
api_key = "your_api_key"
api_secret = "your_api_secret"
redirect_uri = "your_redirect_uri"
```

### How to Get Refresh Token

1. **From Upstox Developer Portal**:
   - Log in to https://account.upstox.com/
   - Go to Developer section
   - Generate new tokens
   - Copy both `access_token` and `refresh_token`

2. **From Initial Login**:
   - If you used `initial_login.py` or similar script
   - Check the token file: `data/upstox_tokens.json`
   - Copy the `refresh_token` from there

3. **From API Response**:
   - When you first authenticate, the API returns both tokens
   - Save the `refresh_token` for future use

### Testing Auto-Refresh

Once `refresh_token` is added:

1. **Check token expiration**:
   ```python
   from token_manager import get_token_manager
   tm = get_token_manager()
   access, refresh = tm.load_tokens()
   print(f"Access token: {access[:20]}...")
   print(f"Refresh token: {refresh[:20]}...")
   print(f"Expired: {tm._is_expired()}")
   ```

2. **Test auto-refresh**:
   ```python
   # This should automatically refresh if expired
   token = tm.get_access_token(
       auto_refresh=True,
       api_key="your_api_key",
       api_secret="your_api_secret"
   )
   ```

3. **Monitor logs**:
   ```bash
   tail -f background_service.log | grep -i "token\|refresh"
   ```

### Expected Behavior

When auto-refresh works:
- ✅ Logs: `🔄 Access token expired. Attempting automatic refresh...`
- ✅ Logs: `✅ Token automatically refreshed successfully`
- ✅ New token saved to `secrets.toml` (if loaded from there)
- ✅ API calls continue without interruption

### Current Implementation

The system now:
1. ✅ Checks token expiration every 5 minutes
2. ✅ Automatically refreshes when expired (if refresh_token available)
3. ✅ Saves refreshed token back to source (secrets.toml or token file)
4. ✅ Handles token expiration errors gracefully
5. ⚠️ **Requires refresh_token to be present**

### Next Steps

1. Add `refresh_token` to `secrets.toml`
2. Restart background service
3. Monitor logs for refresh messages
4. Verify API calls work after token refresh
