#!/bin/bash
# Quick script to fetch and diagnose cloud logs
# Usage: ./check_cloud_logs.sh [platform]

set -e

PLATFORM="${1:-auto}"
TODAY=$(date +%Y-%m-%d)

echo "🔍 Cloud Log Diagnostic Tool"
echo "============================="
echo "Date: $TODAY"
echo ""

# Function to check Fly.io logs
check_flyio() {
    echo "📡 Checking Fly.io logs..."
    echo ""
    
    if ! command -v fly &> /dev/null; then
        echo "❌ Fly CLI not installed"
        echo "   Install: curl -L https://fly.io/install.sh | sh"
        return 1
    fi
    
    echo "🔄 Fetching logs from Fly.io (last 200 lines)..."
    fly logs -a option-chain-worker -n 200 > /tmp/flyio_logs.txt
    
    echo ""
    echo "=== ANALYZING LOGS ==="
    echo ""
    
    # Check for common issues
    echo "❌ Errors found:"
    grep -i "error\|exception\|failed\|fatal" /tmp/flyio_logs.txt || echo "   No errors found"
    echo ""
    
    echo "⚠️  Warnings found:"
    grep -i "warning\|warn" /tmp/flyio_logs.txt || echo "   No warnings found"
    echo ""
    
    echo "🔑 Token/Auth issues:"
    grep -i "token\|auth\|unauthorized\|403\|401" /tmp/flyio_logs.txt || echo "   No auth issues"
    echo ""
    
    echo "💾 Database issues:"
    grep -i "database\|postgres\|connection" /tmp/flyio_logs.txt || echo "   No database issues"
    echo ""
    
    echo "📊 Data refresh status:"
    grep -i "fetching\|updating\|processed\|symbols" /tmp/flyio_logs.txt | tail -10
    echo ""
    
    echo "⏰ Last activity:"
    tail -20 /tmp/flyio_logs.txt
    echo ""
    
    echo "📄 Full log saved to: /tmp/flyio_logs.txt"
}

# Function to check Render logs
check_render() {
    echo "📡 Checking Render.com logs..."
    echo ""
    echo "⚠️  Render logs are best viewed via dashboard:"
    echo "   https://dashboard.render.com"
    echo ""
    echo "Select your service → Logs tab"
    echo ""
    echo "Look for:"
    echo "  - Service restarts (free tier sleeps after 15 min)"
    echo "  - Memory issues (512MB limit on free tier)"
    echo "  - Build failures"
    echo "  - Runtime errors"
}

# Function to check Railway logs
check_railway() {
    echo "📡 Checking Railway logs..."
    echo ""
    
    if ! command -v railway &> /dev/null; then
        echo "❌ Railway CLI not installed"
        echo "   Install: npm i -g @railway/cli"
        return 1
    fi
    
    echo "🔄 Fetching Railway logs..."
    railway logs > /tmp/railway_logs.txt 2>&1 || true
    
    cat /tmp/railway_logs.txt
    echo ""
    echo "📄 Full log saved to: /tmp/railway_logs.txt"
}

# Auto-detect platform or use specified
case "$PLATFORM" in
    flyio|fly)
        check_flyio
        ;;
    render)
        check_render
        ;;
    railway)
        check_railway
        ;;
    auto)
        echo "🔍 Auto-detecting platform..."
        echo ""
        
        # Try Fly.io first
        if command -v fly &> /dev/null; then
            if fly status -a option-chain-worker &> /dev/null; then
                echo "✅ Found Fly.io deployment"
                check_flyio
                exit 0
            fi
        fi
        
        # Try Railway
        if command -v railway &> /dev/null; then
            echo "✅ Found Railway deployment"
            check_railway
            exit 0
        fi
        
        # Default to showing options
        echo "❌ Could not auto-detect platform"
        echo ""
        echo "Please specify platform manually:"
        echo "  ./check_cloud_logs.sh flyio"
        echo "  ./check_cloud_logs.sh render"
        echo "  ./check_cloud_logs.sh railway"
        ;;
    *)
        echo "❌ Unknown platform: $PLATFORM"
        echo ""
        echo "Usage: ./check_cloud_logs.sh [flyio|render|railway|auto]"
        exit 1
        ;;
esac

echo ""
echo "=== COMMON SOLUTIONS ==="
echo ""
echo "If data not refreshing, check:"
echo ""
echo "1. ⏰ Market Hours (9:15 AM - 3:30 PM IST, Mon-Fri)"
echo "   Current IST: $(TZ=Asia/Kolkata date '+%Y-%m-%d %H:%M:%S %Z')"
echo ""
echo "2. 🔑 Access Token (expires daily)"
echo "   Update token via: fly secrets set ACCESS_TOKEN=xxx"
echo ""
echo "3. 📊 Background Service Running"
echo "   Check: fly status -a option-chain-worker"
echo ""
echo "4. 💾 Database Connection"
echo "   Verify DATABASE_URL secret is set"
echo ""
echo "5. 🌐 API Rate Limits"
echo "   Upstox has rate limits - check for 429 errors"
