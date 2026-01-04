#!/bin/bash

# 🚀 Oracle Cloud Deployment Script
# Deploys all 3 UIs + Background Service

echo "========================================"
echo "🚀 ORACLE CLOUD DEPLOYMENT"
echo "========================================"
echo ""
echo "This will deploy:"
echo "  1. Streamlit Dashboard (with Sentiment) - Port 8501"
echo "  2. FastAPI + Next.js Dashboard - Ports 8000 + 3000"
echo "  3. Background Data Service (shared)"
echo "  4. PostgreSQL Database (shared)"
echo ""
echo "Both UIs use the same data source!"
echo ""
read -p "Continue? (y/n) " -n 1 -r
echo ""

if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Cancelled."
    exit 0
fi

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo ""
echo "${GREEN}Step 1: System Update${NC}"
sudo apt update && sudo apt upgrade -y

echo ""
echo "${GREEN}Step 2: Install Dependencies${NC}"
sudo apt install -y \
    python3-pip \
    python3-venv \
    postgresql \
    postgresql-contrib \
    nginx \
    git

echo ""
echo "${GREEN}Step 3: Setup PostgreSQL Database${NC}"
sudo -u postgres psql << EOF
CREATE DATABASE optionchain;
CREATE USER optionuser WITH PASSWORD 'option2026secure';
GRANT ALL PRIVILEGES ON DATABASE optionchain TO optionuser;
\q
EOF

echo ""
echo "${GREEN}Step 4: Install TimescaleDB Extension${NC}"
sudo -u postgres psql -d optionchain << EOF
CREATE EXTENSION IF NOT EXISTS timescaledb;
\q
EOF

echo ""
echo "${GREEN}Step 5: Setup Python Environment${NC}"
python3 -m venv ~/venv
source ~/venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
pip install -r requirements_dashboard.txt

echo ""
echo "${GREEN}Step 6: Install Node.js LTS${NC}"
curl -fsSL https://deb.nodesource.com/setup_18.x | sudo -E bash -
sudo apt-get install -y nodejs

echo ""
echo "${GREEN}Step 7: Setup Next.js Frontend${NC}"
cd fastapi-nextjs/frontend
npm install
npm run build
cd ../..

echo ""
echo "${GREEN}Step 8: Configure Environment${NC}"

# Prompt for credentials
echo ""
echo "${YELLOW}📋 Upstox API Configuration${NC}"
echo "You'll need:"
echo "  • Client ID (from Upstox developer console)"
echo "  • Client Secret (from Upstox developer console)"
echo "  • Redirect URI (default: http://localhost:5000/callback)"
echo ""
read -p "Upstox Client ID: " UPSTOX_CLIENT_ID
read -p "Upstox Client Secret: " UPSTOX_CLIENT_SECRET
read -p "Redirect URI [http://localhost:5000/callback]: " UPSTOX_REDIRECT_URI
UPSTOX_REDIRECT_URI=${UPSTOX_REDIRECT_URI:-http://localhost:5000/callback}

# Get server IP for instructions
SERVER_IP=$(curl -s ifconfig.me || echo "YOUR_VM_IP")

# Create .env file
cat > .env << ENVEOF
DATABASE_URL=postgresql://optionuser:option2026secure@localhost/optionchain
UPSTOX_API_KEY=${UPSTOX_CLIENT_ID}
UPSTOX_SECRET=${UPSTOX_CLIENT_SECRET}
UPSTOX_REDIRECT_URI=${UPSTOX_REDIRECT_URI}
ENVEOF

# Create config.py for Python scripts
cat > config.py << PYCONF
# Upstox API Configuration
UPSTOX_CLIENT_ID = "${UPSTOX_CLIENT_ID}"
UPSTOX_CLIENT_SECRET = "${UPSTOX_CLIENT_SECRET}"
UPSTOX_REDIRECT_URI = "${UPSTOX_REDIRECT_URI}"

# Database Configuration  
DATABASE_URL = "postgresql://optionuser:option2026secure@localhost/optionchain"
PYCONF

echo ""
echo "${GREEN}✅ Configuration files created!${NC}"
echo ""
echo "${YELLOW}ℹ️  Access Token Generation:${NC}"
echo "Access tokens are auto-generated via OAuth flow."
echo "After deployment completes:"
echo "  1. Visit: http://${SERVER_IP}/streamlit"
echo "  2. Click 'Login with Upstox' button"
echo "  3. Complete OAuth authorization"
echo "  4. Token auto-saved to data/upstox_tokens.json"
echo ""

# Create data directory for token storage
mkdir -p /home/ubuntu/OptionChainUsingUpstock/data
mkdir -p /home/ubuntu/OptionChainUsingUpstock/logs

echo ""
echo "${GREEN}Step 9: Create Systemd Services${NC}"

# Service 1: Streamlit Dashboard (with Sentiment included)
sudo tee /etc/systemd/system/option-dashboard.service > /dev/null << 'EOF'
[Unit]
Description=Option Chain Dashboard (Streamlit with Sentiment)
After=network.target postgresql.service option-worker.service

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/OptionChainUsingUpstock
Environment="PATH=/home/ubuntu/venv/bin"
ExecStart=/home/ubuntu/venv/bin/streamlit run optionchain.py --server.port 8501 --server.address 0.0.0.0 --server.headless true
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# Service 2: FastAPI Backend
sudo tee /etc/systemd/system/fastapi-backend.service > /dev/null << 'EOF'
[Unit]
Description=FastAPI Backend (Option Chain API)
After=network.target postgresql.service option-worker.service

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/OptionChainUsingUpstock/fastapi-nextjs/backend
Environment="PATH=/home/ubuntu/venv/bin"
ExecStart=/home/ubuntu/venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# Service 3: Next.js Frontend
sudo tee /etc/systemd/system/nextjs-frontend.service > /dev/null << 'EOF'
[Unit]
Description=Next.js Frontend (Option Chain UI)
After=network.target fastapi-backend.service

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/OptionChainUsingUpstock/fastapi-nextjs/frontend
Environment="PATH=/usr/bin:/usr/local/bin"
Environment="NODE_ENV=production"
ExecStart=/usr/bin/npm start
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# Service 4: Background Worker (SHARED - feeds data to both UIs)
sudo tee /etc/systemd/system/option-worker.service > /dev/null << 'EOF'
[Unit]
Description=Option Chain Background Worker
After=network.target postgresql.service

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/OptionChainUsingUpstock
Environment="PATH=/home/ubuntu/venv/bin"
ExecStart=/home/ubuntu/venv/bin/python background_service.py --force
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

echo ""
echo "${GREEN}Step 10: Configure Nginx Reverse Proxy${NC}"
sudo tee /etc/nginx/sites-available/option-chain > /dev/null << 'EOF'
server {
    listen 80;
    server_name _;

    # Main Next.js Dashboard (Modern UI)
    location / {
        proxy_pass http://localhost:3000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
    }

    # Streamlit Dashboard (includes sentiment)
    location /streamlit {
        proxy_pass http://localhost:8501;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }

    # FastAPI Backend
    location /api {
        proxy_pass http://localhost:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }

    # WebSocket endpoint
    location /ws {
        proxy_pass http://localhost:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
    }
}
EOF

sudo ln -s /etc/nginx/sites-available/option-chain /etc/nginx/sites-enabled/ 2>/dev/null
sudo rm /etc/nginx/sites-enabled/default 2>/dev/null
sudo nginx -t

echo ""
echo "${GREEN}Step 11: Configure Firewall${NC}"
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 80 -j ACCEPT
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 8501 -j ACCEPT
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 8000 -j ACCEPT
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 3000 -j ACCEPT
sudo netfilter-persistent save 2>/dev/null || sudo iptables-save | sudo tee /etc/iptables/rules.v4

echo ""
echo "${GREEN}Step 12: Start All Services${NC}"
sudo systemctl daemon-reload

sudo systemctl enable option-dashboard
# Start in order: database → worker → backends → frontends
echo "Starting Background Worker (data collection)..."
sudo systemctl enable option-worker
sudo systemctl start option-worker
sleep 3

echo "Starting Streamlit Dashboard..."
sudo systemctl enable option-dashboard
sudo systemctl start option-dashboard

echo "Starting FastAPI Backend..."
sudo systemctl enable fastapi-backend
sudo systemctl start fastapi-backend

echo "Starting Next.js Frontend..."
sudo systemctl enable nextjs-frontend
sudo systemctl start nextjs-frontend

echo "Restarting Nginx..."
sudo systemctl enable nginx
sudo systemctl restart nginx

echo ""
echo "========================================"
echo "${GREEN}✅ DEPLOYMENT COMPLETE!${NC}"
echo "========================================"
echo ""
echo "📊 Access Your Dashboards:"
echo ""
echo "1️⃣  Modern UI (FastAPI + Next.js) - RECOMMENDED:"
echo "    http://${SERVER_IP}/"
echo "    • Fastest performance"
echo "    • Real-time WebSocket updates"
echo "    • Production-grade"
echo ""
echo "2️⃣  Streamlit Dashboard (with Sentiment):"
echo "    http://${SERVER_IP}/streamlit"
echo "    or direct: http://${SERVER_IP}:8501"
echo "    • Full-featured option chain"
echo "    • Sentiment analysis included"
echo ""
echo "${YELLOW}⚠️  FIRST TIME SETUP:${NC}"
echo "    Visit Streamlit dashboard and click 'Login with Upstox'"
echo "    Complete OAuth flow to generate access token"
echo "    Token auto-saves to data/upstox_tokens.json"
echo ""
echo "🔧 Data Flow:"
echo "    Background Worker → PostgreSQL → Both UIs"
echo "    (One worker feeds both dashboards!)"
echo ""
echo "🔧 Manage Services:"
echo "    sudo systemctl status option-worker     # Data collection"
echo "    sudo systemctl status option-dashboard  # Streamlit UI"
echo "    sudo systemctl status fastapi-backend   # FastAPI"
echo "    sudo systemctl status nextjs-frontend   # Next.js UI"
echo ""
echo "📋 View Logs:"
echo "    sudo journalctl -u option-worker -f"
echo "    sudo journalctl -u option-dashboard -f"
echo "    sudo journalctl -u fastapi-backend -f"
echo "    sudo journalctl -u nextjs-frontend -f"
echo ""
echo "💡 Tip: Start with the Modern UI at http://YOUR_VM_IP/"
echo "========================================"