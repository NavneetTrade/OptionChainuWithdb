# Reset Database and Start Fresh

## Steps to Clear Database and Start Fresh Data Collection

### Step 1: Stop Background Service
```bash
pkill -f background_service.py
```

### Step 2: Clear Database
```bash
python3 clear_database.py
```
This will:
- Show current data counts
- Ask for confirmation
- Clear all option chain data and sentiment scores
- Preserve symbol configurations

### Step 3: Start Background Service
```bash
python3 background_service.py --interval 60
```

## How It Works

### When Market is CLOSED:
- ✅ Fetches data **ONCE** for all symbols
- ✅ Stores in database with sentiment scores
- ✅ Checks every 1 minute if market has opened

### When Market is OPEN (9:15 AM - 3:30 PM IST):
- ✅ Fetches data **every 1 minute** for all symbols
- ✅ Calculates and stores sentiment scores
- ✅ Updates database continuously

## Verification

After starting, check the logs:
```bash
tail -f background_service.log
```

You should see:
- "Market is closed. Fetching data once (last available data)..."
- "Fetching data for X symbols..."
- "Successfully stored data for [SYMBOL]"

## Database Check

To verify data is being collected:
```bash
python3 -c "
import os
import psycopg2
conn = psycopg2.connect(
    host=os.getenv('DB_HOST', 'localhost'),
    port=os.getenv('DB_PORT', '5432'),
    database=os.getenv('DB_NAME', 'optionchain'),
    user=os.getenv('DB_USER', 'navneet')
)
cur = conn.cursor()
cur.execute('SELECT COUNT(*) FROM option_chain_data')
print(f'Option Chain Records: {cur.fetchone()[0]}')
cur.execute('SELECT COUNT(*) FROM sentiment_scores')
print(f'Sentiment Scores: {cur.fetchone()[0]}')
conn.close()
"
```

