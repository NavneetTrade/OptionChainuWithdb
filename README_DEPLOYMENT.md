# 🚀 FREE Deployment Guide

## Option 1: Hugging Face Spaces + Neon.tech (100% FREE)

### Step 1: Setup Free PostgreSQL Database (Neon.tech)

1. Go to https://neon.tech
2. Sign up (free, no credit card)
3. Create new project: "option-chain-db"
4. Copy connection string:
   ```
   postgresql://user:pass@ep-xxx.us-east-2.aws.neon.tech/neondb
   ```
5. Run TimescaleDB extension:
   ```sql
   CREATE EXTENSION IF NOT EXISTS timescaledb;
   ```

### Step 2: Deploy Dashboard to Hugging Face

1. Go to https://huggingface.co/spaces
2. Click "Create new Space"
3. Name: `option-chain-analysis`
4. Space SDK: **Streamlit**
5. Visibility: Public (or Private)
6. Click "Create Space"

7. In Space settings → Repository secrets, add:
   ```
   DATABASE_URL = postgresql://user:pass@ep-xxx.neon.tech/neondb
   UPSTOX_API_KEY = your_api_key
   UPSTOX_SECRET = your_secret
   ```

8. Push these files to the Space repo:
   - `app.py` (renamed from optionchain.py)
   - `requirements.txt`
   - `config.py`
   - `database.py`

### Step 3: Deploy Background Worker (Fly.io - FREE)

1. Install flyctl:
   ```bash
   brew install flyctl  # macOS
   # or: curl -L https://fly.io/install.sh | sh
   ```

2. Sign up:
   ```bash
   fly auth signup
   ```

3. Create app:
   ```bash
   cd OptionChainUsingUpstock
   fly launch --name option-chain-worker --no-deploy
   ```

4. Set secrets:
   ```bash
   fly secrets set DATABASE_URL="postgresql://..."
   fly secrets set UPSTOX_API_KEY="your_key"
   fly secrets set UPSTOX_SECRET="your_secret"
   ```

5. Deploy:
   ```bash
   fly deploy
   ```

### Your Free Stack:
- **Dashboard**: `https://huggingface.co/spaces/yourname/option-chain-analysis`
- **Database**: Neon.tech (0.5GB free)
- **Worker**: Fly.io (256MB RAM free)
- **Cost**: $0/month ✅

---

## Option 2: Oracle Cloud Always Free (All-in-One)

### What You Get (FREE FOREVER):
- 2 VMs (1GB RAM, 1 CPU each)
- 200GB storage
- Ubuntu/Oracle Linux
- Public IP

### Setup (30 minutes):

1. **Sign up**: https://cloud.oracle.com/free
   - Need credit card for verification (won't be charged)

2. **Create VM**:
   - Compute → Instances → Create Instance
   - Image: Ubuntu 22.04
   - Shape: VM.Standard.A1.Flex (ARM) - Always Free
   - Add SSH key

3. **Install on VM**:
   ```bash
   # SSH into VM
   ssh ubuntu@your-vm-ip

   # Install dependencies
   sudo apt update
   sudo apt install -y python3-pip python3-venv postgresql nginx

   # Setup PostgreSQL
   sudo -u postgres psql
   CREATE DATABASE optionchain;
   CREATE USER optionuser WITH PASSWORD 'yourpass';
   GRANT ALL PRIVILEGES ON DATABASE optionchain TO optionuser;
   \q

   # Clone your code
   git clone https://github.com/yourusername/your-repo.git
   cd your-repo/OptionChainUsingUpstock

   # Setup Python environment
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt

   # Run as systemd services (auto-restart)
   sudo cp deployment/systemd/* /etc/systemd/system/
   sudo systemctl enable option-chain-worker
   sudo systemctl enable option-chain-dashboard
   sudo systemctl start option-chain-worker
   sudo systemctl start option-chain-dashboard

   # Setup Nginx reverse proxy
   sudo cp deployment/nginx/option-chain /etc/nginx/sites-available/
   sudo ln -s /etc/nginx/sites-available/option-chain /etc/nginx/sites-enabled/
   sudo systemctl restart nginx
   ```

4. **Access**:
   - Dashboard: `http://your-vm-ip`
   - Add free SSL with Let's Encrypt

### Cost: $0/month ✅

---

## Option 3: Render.com Free Tier

### What's Free:
- 750 hours/month web service
- Sleeps after 15 min inactivity
- 90 second boot time (cold start)

### Setup (10 minutes):

1. Go to https://render.com
2. Connect GitHub repo
3. Create **Web Service**:
   - Build: `pip install -r requirements.txt`
   - Start: `streamlit run optionchain.py --server.port 8502`
4. Create **Background Worker**:
   - Build: `pip install -r requirements.txt`
   - Start: `python background_service.py --force`
5. Create **PostgreSQL** database (90 days free, then $7/month)

### Limitation:
- ⚠️ Services sleep after inactivity
- ⚠️ Database only free for 90 days

---

## 📊 Comparison

| Platform | Cost | Uptime | Setup Time | Best For |
|----------|------|--------|------------|----------|
| **Hugging Face + Neon** | FREE | 24/7 | 15 min | Easiest |
| **Oracle Cloud** | FREE | 24/7 | 30 min | Full control |
| **Fly.io** | FREE | 24/7 | 20 min | Good balance |
| **Render** | FREE* | Sleeps | 10 min | Quick test |

*Render database not free after 90 days

---

## 🎯 Recommendation

**For easiest setup**: Hugging Face + Neon.tech
**For best free tier**: Oracle Cloud Always Free
**For quick test**: Render.com

Choose based on your comfort level with Linux servers!
