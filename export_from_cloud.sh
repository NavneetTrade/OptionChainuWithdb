#!/bin/bash
# Remote export script - Runs on cloud server and downloads files locally

set -e

CLOUD_IP="92.4.74.245"
SSH_KEY="~/oracle_key.pem"
REMOTE_SCRIPT="/tmp/export_db_remote.py"
LOCAL_EXPORT_DIR="./exports"

echo "========================================================================"
echo "📥 EXPORTING DATABASE FROM CLOUD TO LOCAL EXCEL FILES"
echo "========================================================================"
echo "Cloud Server: $CLOUD_IP"
echo "Local Export Directory: $LOCAL_EXPORT_DIR"
echo "========================================================================"
echo ""

# Parse arguments
EXPORT_TYPE="${1:-all}"
SYMBOL="${2:-NIFTY}"
DAYS="${3:-7}"

echo "Export Type: $EXPORT_TYPE"
echo "Symbol: $SYMBOL"
echo "Days: $DAYS"
echo ""

# Step 1: Upload export script to cloud server
echo "📤 Step 1/4: Uploading export script to cloud server..."
scp -i "$SSH_KEY" "/Users/navneet/Desktop/Stock Option /OptionChainUsingUpstock/export_db_to_excel.py" "ubuntu@$CLOUD_IP:$REMOTE_SCRIPT"
echo "✅ Upload complete"
echo ""

# Step 2: Run export on cloud server (using local PostgreSQL connection)
echo "🔄 Step 2/4: Running export on cloud server..."
ssh -i "$SSH_KEY" "ubuntu@$CLOUD_IP" << REMOTE_EOF
# Install required packages if not present
pip3 install --quiet psycopg2-binary openpyxl pandas 2>/dev/null || true

# Modify script to use localhost connection
sed -i "s/'host': '92.4.74.245'/'host': 'localhost'/g" "$REMOTE_SCRIPT"

# Run export
cd ~/OptionChainUsingUpstock
python3 "$REMOTE_SCRIPT" --export "$EXPORT_TYPE" --symbol "$SYMBOL" --days "$DAYS" --output exports
REMOTE_EOF

if [ $? -eq 0 ]; then
    echo "✅ Export completed on cloud server"
else
    echo "❌ Export failed on cloud server"
    exit 1
fi
echo ""

# Step 3: Create local export directory
echo "📁 Step 3/4: Creating local export directory..."
mkdir -p "$LOCAL_EXPORT_DIR"
echo "✅ Directory ready: $LOCAL_EXPORT_DIR"
echo ""

# Step 4: Download exported files
echo "📥 Step 4/4: Downloading Excel files from cloud server..."
scp -i "$SSH_KEY" "ubuntu@$CLOUD_IP:~/OptionChainUsingUpstock/exports/*.xlsx" "$LOCAL_EXPORT_DIR/" 2>/dev/null

if [ $? -eq 0 ]; then
    echo "✅ Files downloaded successfully"
    echo ""
    echo "========================================================================"
    echo "✅ EXPORT COMPLETE!"
    echo "========================================================================"
    echo "Files saved to: $LOCAL_EXPORT_DIR/"
    echo ""
    ls -lh "$LOCAL_EXPORT_DIR"/*.xlsx 2>/dev/null | tail -10
    echo ""
else
    echo "⚠️  No files to download (check if export was successful)"
fi

# Cleanup remote files (optional)
echo "🧹 Cleaning up remote files..."
ssh -i "$SSH_KEY" "ubuntu@$CLOUD_IP" "rm -f $REMOTE_SCRIPT"
echo "✅ Cleanup complete"
echo ""
