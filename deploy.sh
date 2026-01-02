#!/bin/bash
# Quick deployment script for FREE platforms

echo "🚀 Option Chain Analysis - FREE Deployment Setup"
echo "=================================================="
echo ""
echo "Choose your FREE deployment platform:"
echo ""
echo "1) Hugging Face Spaces + Neon.tech (Easiest - 100% Free)"
echo "2) Fly.io (Good free tier - 3 VMs free)"
echo "3) Render.com (Free tier - sleeps after inactivity)"
echo "4) Oracle Cloud Always Free (Best free tier - requires Linux knowledge)"
echo ""
read -p "Enter choice (1-4): " choice

case $choice in
  1)
    echo ""
    echo "📦 Setting up for Hugging Face Spaces..."
    echo ""
    echo "Step 1: Create free database at Neon.tech"
    echo "  → Go to: https://neon.tech"
    echo "  → Sign up (no credit card needed)"
    echo "  → Create project: option-chain-db"
    echo "  → Copy connection string"
    echo ""
    echo "Step 2: Create Hugging Face Space"
    echo "  → Go to: https://huggingface.co/spaces"
    echo "  → Click 'Create new Space'"
    echo "  → Name: option-chain-analysis"
    echo "  → SDK: Streamlit"
    echo "  → Create Space"
    echo ""
    echo "Step 3: Add files to Space"
    echo "  → Upload: app.py, requirements.txt, config.py, database.py"
    echo "  → Settings → Repository secrets:"
    echo "    DATABASE_URL = (your Neon connection string)"
    echo "    UPSTOX_API_KEY = (your API key)"
    echo "    UPSTOX_SECRET = (your secret)"
    echo ""
    echo "✅ Your dashboard will be live at:"
    echo "   https://huggingface.co/spaces/YOUR_USERNAME/option-chain-analysis"
    ;;
    
  2)
    echo ""
    echo "📦 Setting up for Fly.io..."
    echo ""
    
    # Check if flyctl is installed
    if ! command -v flyctl &> /dev/null; then
      echo "Installing flyctl..."
      curl -L https://fly.io/install.sh | sh
      export FLYCTL_INSTALL="$HOME/.fly"
      export PATH="$FLYCTL_INSTALL/bin:$PATH"
    fi
    
    echo "✅ flyctl installed"
    echo ""
    echo "Next steps:"
    echo "1) fly auth signup"
    echo "2) fly launch --name option-chain-worker"
    echo "3) fly secrets set DATABASE_URL='...'"
    echo "4) fly secrets set UPSTOX_API_KEY='...'"
    echo "5) fly deploy"
    ;;
    
  3)
    echo ""
    echo "📦 Setting up for Render.com..."
    echo ""
    echo "Step 1: Push code to GitHub"
    echo "Step 2: Go to https://render.com"
    echo "Step 3: Connect your GitHub repo"
    echo "Step 4: Create services:"
    echo "  - Web Service (optionchain.py)"
    echo "  - Background Worker (background_service.py)"
    echo "  - PostgreSQL database (free for 90 days)"
    echo ""
    echo "⚠️  Note: Free tier sleeps after 15 min inactivity"
    ;;
    
  4)
    echo ""
    echo "📦 Setting up for Oracle Cloud Always Free..."
    echo ""
    echo "This gives you 2 VMs (1GB RAM each) FOREVER FREE!"
    echo ""
    echo "Steps:"
    echo "1) Sign up: https://cloud.oracle.com/free"
    echo "2) Create VM instance (Ubuntu 22.04)"
    echo "3) SSH into VM"
    echo "4) Run deployment script:"
    echo ""
    echo "   git clone your-repo"
    echo "   cd OptionChainUsingUpstock"
    echo "   chmod +x deployment/oracle-cloud-setup.sh"
    echo "   sudo ./deployment/oracle-cloud-setup.sh"
    echo ""
    echo "✅ Your app will run at: http://your-vm-ip"
    ;;
    
  *)
    echo "Invalid choice!"
    exit 1
    ;;
esac

echo ""
echo "📖 For detailed instructions, see: README_DEPLOYMENT.md"
