# Data Storage After 3:30 PM - Analysis

## Current Situation (Based on Database Query)

### BANKNIFTY ITM Data Timeline (Today - Jan 1, 2026):
- **09:00-09:59**: 70 records ✓ (Market open at 9:15)
- **10:00-10:59**: 70 records ✓
- **11:00-11:59**: 30 records ✓
- **13:00-13:59**: 45 records ✓
- **14:00-14:59**: 80 records ✓
- **15:00-15:59**: 35 records (⚠️ Includes post-3:30 PM)
- **16:00-16:59**: 5 records ❌ (Should NOT exist)

### Problematic Records:
1. **15:38:55** (3:38 PM) - 8 minutes after market close
2. **16:02:25** (4:02 PM) - 32 minutes after market close

## Why This Happened:

1. **Background Service Timing**: The service runs every 3 minutes (180 seconds)
   - Last market cycle: ~3:27 PM (within market hours)
   - Next cycle: ~3:30 PM (exactly at market close, may process)
   - Following cycle: ~3:33 PM or later (after market close)

2. **Race Condition**: If the service started a fetch cycle at 3:29:xx PM:
   - It begins fetching all 215 symbols
   - Takes ~2-3 minutes to complete
   - Finishes at 3:31-3:33 PM
   - Data gets stored with timestamps after 3:30 PM

3. **Previous Force Mode**: Service was running with `--force` flag earlier, bypassing market hour checks

## Solutions:

### Option 1: Filter Display (Recommended)
- Keep all data in database for historical analysis
- Filter dashboard queries to only show data until 3:30 PM
- Modify `get_itm_bucket_summaries()` to add WHERE clause

### Option 2: Prevent Storage
- Add market hour check BEFORE storing data
- Check timestamp before INSERT operations
- Reject data if timestamp > 3:30 PM

### Option 3: Clean Up Task
- Daily cleanup job to remove data after 3:30 PM
- Preserve data integrity for that trading day

## Recommendation:
**Use Option 1** - Filter at display time:
- Preserves all collected data
- Allows post-market analysis if needed
- Simple query modification
- No data loss risk
