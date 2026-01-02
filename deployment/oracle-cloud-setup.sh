#!/bin/bash
# Oracle Cloud Always Free - Complete Setup Script
# This script sets up everything on a single VM

set -e  # Exit on error

echo "🚀 Oracle Cloud - Option Chain Analysis Setup"
echo "=============================================="
echo ""

# Check if running as root
if [ "$EUID" -eq 0 ]; then 
   echo "⚠️  Please run as ubuntu user, not root"
   exit 1
fi

# Update system
echo "📦 Updating system packages..."
sudo apt update
sudo apt upgrade -y

# Install dependencies
echo "📦 Installing required packages..."
sudo apt install -y \
    python3.10 \
    python3.10-venv \
    python3-pip \
    postgresql \
    postgresql-contrib \
    nginx \
    git \
    certbot \
    python3-certbot-nginx \
    redis-server \
    supervisor

# Setup PostgreSQL with TimescaleDB
echo "🗄️  Setting up PostgreSQL database..."
sudo -u postgres psql <<EOF
CREATE DATABASE optionchain;
CREATE USER optionuser WITH ENCRYPTED PASSWORD 'Change_This_Password_123';
GRANT ALL PRIVILEGES ON DATABASE optionchain TO optionuser;
\c optionchain
GRANT ALL ON SCHEMA public TO optionuser;
EOF

# Install TimescaleDB extension
echo "📊 Installing TimescaleDB..."
sudo add-apt-repository -y ppa:timescale/timescaledb-ppa
sudo apt update
sudo apt install -y timescaledb-postgresql-14

# Enable TimescaleDB
sudo -u postgres psql -d optionchain -c "CREATE EXTENSION IF NOT EXISTS timescaledb;"

echo "✅ Database setup complete"

# Setup application directory
APP_DIR="/home/ubuntu/option-chain"
echo "📁 Setting up application directory: $APP_DIR"

if [ -d "$APP_DIR" ]; then
    echo "⚠️  Directory exists. Updating..."
    cd "$APP_DIR"
    git pull
else
    echo "📥 Cloning repository..."
    echo "⚠️  You need to update this with your GitHub repo URL"
    # git clone https://github.com/YOUR_USERNAME/YOUR_REPO.git "$APP_DIR"
    
    # For now, create directory structure
    mkdir -p "$APP_DIR"
    mkdir -p "$APP_DIR/OptionChainUsingUpstock"
    mkdir -p "$APP_DIR/OptionChainUsingUpstock/logs"
    mkdir -p "$APP_DIR/OptionChainUsingUpstock/data"
    
    echo "⚠️  Please copy your code to $APP_DIR/OptionChainUsingUpstock/"
    echo "   Press Enter when ready..."
    read
fi

cd "$APP_DIR/OptionChainUsingUpstock"

# Create Python virtual environment
echo "🐍 Setting up Python virtual environment..."
python3.10 -m venv venv
source venv/bin/activate

# Install Python packages
echo "📦 Installing Python dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

# Create environment file
echo "🔐 Creating environment configuration..."
cat > .env <<EOF
# Database Configuration
DATABASE_URL=postgresql://optionuser:Change_This_Password_123@localhost:5432/optionchain

# Upstox API Credentials (CHANGE THESE!)
UPSTOX_API_KEY=your_api_key_here
UPSTOX_SECRET=your_secret_here
UPSTOX_REDIRECT_URI=http://localhost:8080

# Timezone
TZ=Asia/Kolkata

# Token Storage
TOKEN_FILE=/home/ubuntu/option-chain/OptionChainUsingUpstock/data/upstox_tokens.json
EOF

echo ""
echo "⚠️  IMPORTANT: Edit .env file and add your Upstox credentials:"
echo "   nano .env"
echo ""
echo "Press Enter when you've updated the credentials..."
read

# Setup Redis for token caching
echo "📦 Configuring Redis..."
sudo systemctl enable redis-server
sudo systemctl start redis-server

# Create token refresh service
echo "🔄 Setting up automatic token refresh..."
cat > token_refresh_service.py <<'PYEOF'
"""
Automatic Token Refresh Service
Runs every hour to keep Upstox tokens fresh
"""

import os
import json
import time
import logging
from datetime import datetime, timedelta
from pathlib import Path
from dotenv import load_dotenv
from upstox_api import UpstoxAPI

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/token_refresh.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Load environment
load_dotenv()

TOKEN_FILE = os.getenv('TOKEN_FILE', 'data/upstox_tokens.json')
API_KEY = os.getenv('UPSTOX_API_KEY')
API_SECRET = os.getenv('UPSTOX_SECRET')

class TokenRefreshService:
    """Manages automatic token refresh"""
    
    def __init__(self):
        self.api = UpstoxAPI()
        self.token_file = Path(TOKEN_FILE)
        self.token_file.parent.mkdir(exist_ok=True)
    
    def load_tokens(self):
        """Load tokens from file"""
        try:
            if self.token_file.exists():
                with open(self.token_file, 'r') as f:
                    data = json.load(f)
                    return data.get('access_token'), data.get('refresh_token'), data.get('expires_at')
            return None, None, None
        except Exception as e:
            logger.error(f"Error loading tokens: {e}")
            return None, None, None
    
    def save_tokens(self, access_token, refresh_token, expires_in=86400):
        """Save tokens to file"""
        try:
            expires_at = (datetime.now() + timedelta(seconds=expires_in)).isoformat()
            data = {
                'access_token': access_token,
                'refresh_token': refresh_token,
                'expires_at': expires_at,
                'updated_at': datetime.now().isoformat()
            }
            with open(self.token_file, 'w') as f:
                json.dump(data, f, indent=2)
            logger.info("✅ Tokens saved successfully")
            return True
        except Exception as e:
            logger.error(f"Error saving tokens: {e}")
            return False
    
    def is_token_expired(self, expires_at):
        """Check if token is expired or will expire in next hour"""
        if not expires_at:
            return True
        try:
            expiry = datetime.fromisoformat(expires_at)
            # Refresh if less than 1 hour remaining
            return datetime.now() >= expiry - timedelta(hours=1)
        except:
            return True
    
    def refresh_tokens(self):
        """Refresh access token using refresh token"""
        access_token, refresh_token, expires_at = self.load_tokens()
        
        if not refresh_token:
            logger.error("❌ No refresh token available. Need manual login.")
            return False
        
        if not self.is_token_expired(expires_at):
            logger.info("✅ Token still valid, no refresh needed")
            return True
        
        logger.info("🔄 Refreshing access token...")
        
        success, result = self.api.refresh_access_token(API_KEY, API_SECRET, refresh_token)
        
        if success:
            new_access = result.get('access_token')
            new_refresh = result.get('refresh_token', refresh_token)
            expires_in = result.get('expires_in', 86400)
            
            self.save_tokens(new_access, new_refresh, expires_in)
            logger.info("✅ Token refreshed successfully")
            return True
        else:
            logger.error(f"❌ Token refresh failed: {result}")
            return False
    
    def run_forever(self):
        """Run token refresh service continuously"""
        logger.info("🚀 Token Refresh Service started")
        
        while True:
            try:
                self.refresh_tokens()
                # Check every hour
                time.sleep(3600)
            except KeyboardInterrupt:
                logger.info("🛑 Service stopped by user")
                break
            except Exception as e:
                logger.error(f"Error in refresh loop: {e}")
                time.sleep(300)  # Wait 5 minutes on error

if __name__ == "__main__":
    service = TokenRefreshService()
    service.run_forever()
PYEOF

# Create initial login helper
cat > initial_login.py <<'PYEOF'
"""
One-time initial login to get tokens
Run this once, then the service will auto-refresh
"""

import os
import json
from dotenv import load_dotenv
from upstox_api import UpstoxAPI

load_dotenv()

API_KEY = os.getenv('UPSTOX_API_KEY')
API_SECRET = os.getenv('UPSTOX_SECRET')
REDIRECT_URI = os.getenv('UPSTOX_REDIRECT_URI')
TOKEN_FILE = os.getenv('TOKEN_FILE', 'data/upstox_tokens.json')

api = UpstoxAPI()

print("\n🔐 Upstox Initial Login")
print("=" * 50)
print("\nStep 1: Open this URL in your browser:")
print(api.get_auth_url(API_KEY, REDIRECT_URI))
print("\nStep 2: After login, copy the authorization code from URL")
print("Example: http://localhost:8080/?code=ABC123")
print("\nEnter the authorization code: ", end="")

auth_code = input().strip()

print("\n🔄 Exchanging code for tokens...")
success, result = api.get_access_token(auth_code, API_KEY, API_SECRET, REDIRECT_URI)

if success:
    access_token = result.get('access_token')
    refresh_token = result.get('refresh_token')
    
    # Save tokens
    os.makedirs(os.path.dirname(TOKEN_FILE), exist_ok=True)
    with open(TOKEN_FILE, 'w') as f:
        json.dump({
            'access_token': access_token,
            'refresh_token': refresh_token,
            'expires_at': None
        }, f, indent=2)
    
    print("\n✅ Login successful! Tokens saved to:", TOKEN_FILE)
    print("\nYou can now start the services:")
    print("  sudo systemctl start option-chain-worker")
    print("  sudo systemctl start option-chain-dashboard")
else:
    print("\n❌ Login failed:", result)
PYEOF

# Create systemd services
echo "⚙️  Creating systemd services..."

# Token refresh service
sudo tee /etc/systemd/system/option-chain-token-refresh.service > /dev/null <<EOF
[Unit]
Description=Option Chain Token Refresh Service
After=network.target redis-server.service

[Service]
Type=simple
User=ubuntu
Group=ubuntu
WorkingDirectory=$APP_DIR/OptionChainUsingUpstock
Environment="PATH=$APP_DIR/OptionChainUsingUpstock/venv/bin"
Environment="TZ=Asia/Kolkata"
EnvironmentFile=$APP_DIR/OptionChainUsingUpstock/.env
ExecStart=$APP_DIR/OptionChainUsingUpstock/venv/bin/python token_refresh_service.py

Restart=always
RestartSec=60

StandardOutput=append:$APP_DIR/OptionChainUsingUpstock/logs/token-refresh.log
StandardError=append:$APP_DIR/OptionChainUsingUpstock/logs/token-refresh-error.log

[Install]
WantedBy=multi-user.target
EOF

# Background worker
sudo tee /etc/systemd/system/option-chain-worker.service > /dev/null <<EOF
[Unit]
Description=Option Chain Background Data Collection
After=network.target postgresql.service option-chain-token-refresh.service
Wants=postgresql.service option-chain-token-refresh.service

[Service]
Type=simple
User=ubuntu
Group=ubuntu
WorkingDirectory=$APP_DIR/OptionChainUsingUpstock
Environment="PATH=$APP_DIR/OptionChainUsingUpstock/venv/bin"
Environment="TZ=Asia/Kolkata"
EnvironmentFile=$APP_DIR/OptionChainUsingUpstock/.env
ExecStart=$APP_DIR/OptionChainUsingUpstock/venv/bin/python background_service.py --force

Restart=always
RestartSec=30

StandardOutput=append:$APP_DIR/OptionChainUsingUpstock/logs/worker.log
StandardError=append:$APP_DIR/OptionChainUsingUpstock/logs/worker-error.log

[Install]
WantedBy=multi-user.target
EOF

# Dashboard service
sudo tee /etc/systemd/system/option-chain-dashboard.service > /dev/null <<EOF
[Unit]
Description=Option Chain Streamlit Dashboard
After=network.target postgresql.service
Wants=postgresql.service

[Service]
Type=simple
User=ubuntu
Group=ubuntu
WorkingDirectory=$APP_DIR/OptionChainUsingUpstock
Environment="PATH=$APP_DIR/OptionChainUsingUpstock/venv/bin"
Environment="TZ=Asia/Kolkata"
EnvironmentFile=$APP_DIR/OptionChainUsingUpstock/.env
ExecStart=$APP_DIR/OptionChainUsingUpstock/venv/bin/streamlit run optionchain.py --server.port 8502 --server.headless true

Restart=always
RestartSec=30

StandardOutput=append:$APP_DIR/OptionChainUsingUpstock/logs/dashboard.log
StandardError=append:$APP_DIR/OptionChainUsingUpstock/logs/dashboard-error.log

[Install]
WantedBy=multi-user.target
EOF

# Nginx configuration
echo "🌐 Setting up Nginx reverse proxy..."
sudo tee /etc/nginx/sites-available/option-chain > /dev/null <<'EOF'
server {
    listen 80;
    server_name _;  # Replace with your domain

    # Increase buffer sizes for Streamlit
    client_max_body_size 100M;
    
    location / {
        proxy_pass http://localhost:8502;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # Streamlit specific
        proxy_buffering off;
        proxy_read_timeout 86400;
        proxy_redirect off;
    }
    
    # Health check endpoint
    location /health {
        access_log off;
        return 200 "OK\n";
        add_header Content-Type text/plain;
    }
}
EOF

sudo ln -sf /etc/nginx/sites-available/option-chain /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl restart nginx

# Firewall rules (Oracle Cloud uses iptables)
echo "🔒 Configuring firewall..."
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 80 -j ACCEPT
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 443 -j ACCEPT
sudo netfilter-persistent save

# Enable services
echo "✅ Enabling services..."
sudo systemctl daemon-reload
sudo systemctl enable option-chain-token-refresh
sudo systemctl enable option-chain-worker
sudo systemctl enable option-chain-dashboard
sudo systemctl enable nginx

echo ""
echo "=" * 60
echo "✅ Installation Complete!"
echo "=" * 60
echo ""
echo "📋 Next Steps:"
echo ""
echo "1. Run initial login to get tokens:"
echo "   cd $APP_DIR/OptionChainUsingUpstock"
echo "   source venv/bin/activate"
echo "   python initial_login.py"
echo ""
echo "2. Start all services:"
echo "   sudo systemctl start option-chain-token-refresh"
echo "   sudo systemctl start option-chain-worker"
echo "   sudo systemctl start option-chain-dashboard"
echo ""
echo "3. Check service status:"
echo "   sudo systemctl status option-chain-token-refresh"
echo "   sudo systemctl status option-chain-worker"
echo "   sudo systemctl status option-chain-dashboard"
echo ""
echo "4. View logs:"
echo "   tail -f logs/token-refresh.log"
echo "   tail -f logs/worker.log"
echo "   tail -f logs/dashboard.log"
echo ""
echo "5. Access dashboard:"
echo "   http://$(curl -s ifconfig.me)"
echo ""
echo "6. (Optional) Setup SSL with Let's Encrypt:"
echo "   sudo certbot --nginx -d your-domain.com"
echo ""
echo "🔄 Token Auto-Refresh: Enabled (checks every hour)"
echo "💾 Database: PostgreSQL + TimescaleDB"
echo "🌐 Web Server: Nginx"
echo ""
echo "💰 Cost: \$0/month (Oracle Always Free tier)"
echo ""
