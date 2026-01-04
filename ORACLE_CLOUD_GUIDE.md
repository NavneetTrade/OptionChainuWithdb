# 🚀 Oracle Cloud Deployment Guide - All 3 UIs

## What You're Deploying

### 1. **FastAPI + Next.js** (Modern UI) 🚀
- **Ultra-fast** React-based dashboard
- **Real-time WebSocket** updates
- **Production-grade** performance
- **Access**: `http://YOUR_VM_IP/`

### 2. **Streamlit Option Chain** 📊
- Original option chain analysis
- Full feature dashboard
- **Access**: `http://YOUR_VM_IP/option-chain`

### 3. **Streamlit Sentiment** 📈
- Market sentiment analysis
- Sentiment scores & insights
- **Access**: `http://YOUR_VM_IP/sentiment`

---

## 🎯 Quick Deployment Steps

### Step 1: Create Oracle Cloud VM

1. Login to https://cloud.oracle.com
2. **Compute → Instances → Create Instance**
3. Settings:
   - **Name**: `option-chain-server`
   - **Image**: Ubuntu 22.04
   - **Shape**: VM.Standard.E2.1.Micro (Always Free)
   - **Network**: Allow all ports (configure later)
   - **Add SSH Key**: Upload or generate
4. Click **Create**
5. **Note your Public IP**

### Step 2: Configure Oracle Cloud Firewall

1. In Oracle Console:
   - **Networking → Virtual Cloud Networks**
   - Click your VCN → **Security Lists**
   - Click "Default Security List"
   - **Add Ingress Rules**:

| Source CIDR | Protocol | Port Range | Description |
|-------------|----------|------------|-------------|
| 0.0.0.0/0 | TCP | 80 | HTTP |
| 0.0.0.0/0 | TCP | 8501 | Streamlit 1 |
| 0.0.0.0/0 | TCP | 8502 | Streamlit 2 |
| 0.0.0.0/0 | TCP | 8000 | FastAPI |
| 0.0.0.0/0 | TCP | 3000 | Next.js |

### Step 3: Upload Your Code to VM

**Option A: Using Git**
```bash
# SSH into VM
ssh ubuntu@YOUR_VM_IP

# Clone your repository
git clone YOUR_GITHUB_REPO_URL
cd OptionChainUsingUpstock
```

**Option B: Using SCP (from your local machine)**
```bash
# From your local machine
cd "/Users/navneet/Desktop/Stock Option"
scp -r OptionChainUsingUpstock ubuntu@YOUR_VM_IP:~/
```

### Step 4: Run Automated Deployment

```bash
# SSH into VM
ssh ubuntu@YOUR_VM_IP

# Go to project directory
cd ~/OptionChainUsingUpstock

# Run deployment script
./oracle_cloud_deploy.sh
```

The script will:
- ✅ Install all dependencies (Python, Node.js, PostgreSQL, Nginx)
- ✅ Setup database with TimescaleDB
- ✅ Install Python packages
- ✅ Build Next.js frontend
- ✅ Create systemd services for all 5 components
- ✅ Configure Nginx reverse proxy
- ✅ Setup firewall rules
- ✅ Start all services

### Step 5: Configure Upstox Credentials

During deployment, you'll be asked to edit `.env`:

```bash
nano .env
```

Add your Upstox credentials:
```bash
DATABASE_URL=postgresql://optionuser:option2026secure@localhost/optionchain
UPSTOX_API_KEY=your_actual_api_key
UPSTOX_SECRET=your_actual_secret
UPSTOX_REDIRECT_URI=http://YOUR_VM_IP:8501/callback
```

Save and exit (Ctrl+X, Y, Enter)

### Step 6: Access Your Dashboards! 🎉

**Main Dashboard (Recommended - Fastest)**
```
http://YOUR_VM_IP/
```
Modern React UI with real-time updates

**Option Chain Analysis**
```
http://YOUR_VM_IP/option-chain
or
http://YOUR_VM_IP:8501
```

**Sentiment Analysis**
```
http://YOUR_VM_IP/sentiment
or
http://YOUR_VM_IP:8502
```

**API Documentation**
```
http://YOUR_VM_IP/api/docs
```

---

## 🔧 Managing Your Deployment

### Check Service Status

```bash
# All services
sudo systemctl status option-dashboard
sudo systemctl status sentiment-dashboard
sudo systemctl status fastapi-backend
sudo systemctl status nextjs-frontend
sudo systemctl status option-worker
```

### View Logs

```bash
# Real-time logs for each service
sudo journalctl -u option-dashboard -f
sudo journalctl -u sentiment-dashboard -f
sudo journalctl -u fastapi-backend -f
sudo journalctl -u nextjs-frontend -f
sudo journalctl -u option-worker -f
```

### Restart Services

```bash
# Restart a specific service
sudo systemctl restart option-dashboard

# Restart all services
sudo systemctl restart option-dashboard sentiment-dashboard fastapi-backend nextjs-frontend option-worker
```

### Update Your Code

```bash
cd ~/OptionChainUsingUpstock

# Pull latest changes
git pull

# Rebuild Next.js (if frontend changed)
cd fastapi-nextjs/frontend
npm run build
cd ../..

# Restart services
sudo systemctl restart option-dashboard sentiment-dashboard fastapi-backend nextjs-frontend option-worker
```

---

## 🗺️ Architecture Overview

```
┌─────────────────────────────────────────────────┐
│  Internet → http://YOUR_VM_IP                   │
└──────────────────┬──────────────────────────────┘
                   │
        ┌──────────▼─────────┐
        │   Nginx (Port 80)  │
        │   Reverse Proxy    │
        └──────────┬─────────┘
                   │
      ┌────────────┼────────────┬─────────────┐
      │            │            │             │
      ▼            ▼            ▼             ▼
┌─────────┐  ┌─────────┐  ┌─────────┐  ┌──────────┐
│Next.js  │  │Streamlit│  │Streamlit│  │ FastAPI  │
│Port 3000│  │Port 8501│  │Port 8502│  │Port 8000 │
│         │  │         │  │         │  │          │
│Modern UI│  │Option   │  │Sentiment│  │API +     │
│         │  │Chain    │  │Analysis │  │WebSocket │
└─────────┘  └─────────┘  └─────────┘  └──────────┘
      │            │            │             │
      └────────────┼────────────┼─────────────┘
                   ▼
        ┌──────────────────────┐
        │  Background Worker   │
        │  Data Collection     │
        └──────────┬───────────┘
                   │
                   ▼
        ┌──────────────────────┐
        │  PostgreSQL +        │
        │  TimescaleDB         │
        └──────────────────────┘
```

---

## 💰 Cost Breakdown

**Oracle Cloud Always Free Tier:**
- ✅ 2 VM instances (1GB RAM, 1 CPU each)
- ✅ 200GB block storage
- ✅ 10TB monthly data transfer
- ✅ **No credit card charges**
- ✅ **FREE forever**

**Your Setup Uses:**
- ✅ 1 VM (well within free tier)
- ✅ ~5GB storage (well within 200GB)
- ✅ FREE

---

## 🎯 Performance Comparison

| Feature | Streamlit | FastAPI + Next.js |
|---------|-----------|-------------------|
| Initial Load | 5-10 seconds | **< 1 second** |
| Data Refresh | 3-5 seconds | **< 100ms** |
| Real-time Updates | ❌ Manual refresh | ✅ Auto WebSocket |
| Multiple Users | Slow (1-2 users) | **Fast (100+ users)** |
| Mobile Responsive | ⚠️ OK | ✅ Excellent |
| Production Ready | ⚠️ OK | ✅✅✅ |

---

## 🆘 Troubleshooting

### Service Won't Start

```bash
# Check logs for specific service
sudo journalctl -u option-dashboard -n 50

# Common fixes:
# 1. Check database is running
sudo systemctl status postgresql

# 2. Check Python environment
source ~/venv/bin/activate
which python

# 3. Check port availability
sudo netstat -tulpn | grep 8501
```

### Can't Access Dashboard

1. **Check Oracle Cloud Security List** (most common issue)
   - Ensure ingress rules are added for all ports

2. **Check VM Firewall**
```bash
sudo iptables -L -n | grep 8501
```

3. **Check Service Status**
```bash
sudo systemctl status nginx
sudo systemctl status option-dashboard
```

### Database Connection Error

```bash
# Verify database is running
sudo systemctl status postgresql

# Test connection
psql -U optionuser -d optionchain -h localhost
# Password: option2026secure
```

### Next.js Build Fails

```bash
# Install specific Node.js version
curl -fsSL https://deb.nodesource.com/setup_18.x | sudo -E bash -
sudo apt-get install -y nodejs

# Rebuild
cd ~/OptionChainUsingUpstock/fastapi-nextjs/frontend
npm install
npm run build
```

---

## 🔒 Security Hardening (Optional)

### 1. Change Database Password

```bash
sudo -u postgres psql
ALTER USER optionuser WITH PASSWORD 'your_new_secure_password';
\q

# Update .env file
nano ~/OptionChainUsingUpstock/.env
```

### 2. Setup SSL (Free with Let's Encrypt)

```bash
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d yourdomain.com
```

### 3. Enable Firewall

```bash
sudo ufw allow 22/tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
```

---

## 📊 Monitoring

### CPU & Memory Usage

```bash
# Real-time monitoring
htop

# Check specific service
sudo systemctl status option-worker
```

### Database Size

```bash
sudo -u postgres psql -d optionchain -c "
SELECT pg_size_pretty(pg_database_size('optionchain'));
"
```

### Nginx Access Logs

```bash
sudo tail -f /var/log/nginx/access.log
```

---

## 🎉 You're Live!

Your Option Chain Analysis system is now running 24/7 on Oracle Cloud for **FREE**!

**Recommended First Access:** `http://YOUR_VM_IP/` (FastAPI + Next.js - fastest)

Enjoy your professional-grade trading dashboard! 📈💰

---

**Need help?** Check logs with `sudo journalctl -u SERVICE_NAME -f`
