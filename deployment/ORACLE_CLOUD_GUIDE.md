# 🚀 Oracle Cloud Always Free - Complete Deployment Guide

## Why Oracle Cloud?

✅ **100% FREE Forever** - No trial period, no credit card charges
✅ **2 VMs** (1GB RAM, 1 CPU each) - Plenty for your app
✅ **200GB Storage** - More than enough
✅ **10TB Bandwidth/month** - Generous limits
✅ **Automatic Token Refresh** - Set it and forget it
✅ **24/7 Uptime** - No sleep/downtime

---

## Part 1: Sign Up for Oracle Cloud (5 minutes)

### Step 1: Create Account
1. Go to: https://cloud.oracle.com/free
2. Click **Start for free**
3. Fill in details:
   - Email
   - Country: India
   - Home region: **Mumbai** (ap-mumbai-1) - closest to Indian markets
4. **Credit card required** for verification (won't be charged)
5. Verify email and phone
6. Login to Oracle Cloud Console

---

## Part 2: Create Ubuntu VM (10 minutes)

### Step 2: Launch Compute Instance

1. In Oracle Cloud Console → **Compute** → **Instances**
2. Click **Create Instance**

3. **Configure Instance**:
   - **Name**: `option-chain-server`
   - **Compartment**: (root)
   - **Availability Domain**: AD-1
   
4. **Image and Shape**:
   - **Image**: Ubuntu 22.04 (latest)
   - **Shape**: 
     - Click "Change Shape"
     - Select **VM.Standard.A1.Flex** (ARM-based, Always Free)
     - OCPU: 1
     - Memory: 6GB (you get 4 OCPUs + 24GB total free, can split)
     
5. **Networking**:
   - Create new virtual cloud network (default settings)
   - Assign public IP: ✅ Yes
   
6. **SSH Keys**:
   - Generate SSH key pair (Download both private and public keys)
   - **Save the private key** - you'll need it to connect!
   
7. Click **Create**

8. **Wait 2-3 minutes** for VM to provision

9. **Note down the Public IP** (shown in instance details)

---

## Part 3: Configure Network (5 minutes)

### Step 3: Open Firewall Ports

1. In instance details → **Subnet** → Click subnet name
2. Click **Default Security List**
3. Click **Add Ingress Rules**

**Rule 1 - HTTP**:
- Source CIDR: `0.0.0.0/0`
- IP Protocol: TCP
- Destination Port: `80`
- Description: HTTP

**Rule 2 - HTTPS**:
- Source CIDR: `0.0.0.0/0`
- IP Protocol: TCP
- Destination Port: `443`
- Description: HTTPS

4. Click **Add Ingress Rules**

---

## Part 4: Connect to VM (2 minutes)

### Step 4: SSH into Your Server

**On macOS/Linux**:
```bash
# Make key private
chmod 400 ~/Downloads/ssh-key-*.key

# Connect
ssh -i ~/Downloads/ssh-key-*.key ubuntu@YOUR_PUBLIC_IP
```

**On Windows** (use PuTTY):
1. Convert `.key` to `.ppk` using PuTTYgen
2. Connect via PuTTY using the `.ppk` file

---

## Part 5: Setup Application (15 minutes)

### Step 5: Copy Setup Script to VM

**Option A: Direct Download** (if you've pushed to GitHub):
```bash
# On the VM
git clone https://github.com/YOUR_USERNAME/YOUR_REPO.git ~/option-chain
cd ~/option-chain/OptionChainUsingUpstock
chmod +x deployment/oracle-cloud-setup.sh
./deployment/oracle-cloud-setup.sh
```

**Option B: Upload from Local** (if code not on GitHub yet):
```bash
# On your Mac (new terminal, not SSH)
cd "/Users/navneet/Desktop/Stock Option "
tar -czf option-chain.tar.gz OptionChainUsingUpstock/
scp -i ~/Downloads/ssh-key-*.key option-chain.tar.gz ubuntu@YOUR_PUBLIC_IP:~

# Back on VM (SSH terminal)
tar -xzf option-chain.tar.gz
mv OptionChainUsingUpstock ~/option-chain/
cd ~/option-chain/OptionChainUsingUpstock
chmod +x deployment/oracle-cloud-setup.sh
./deployment/oracle-cloud-setup.sh
```

### Step 6: Update Configuration

The setup script will pause asking you to update credentials:

```bash
nano .env
```

Update these values:
```bash
# Change database password (optional but recommended)
DATABASE_URL=postgresql://optionuser:YOUR_STRONG_PASSWORD@localhost:5432/optionchain

# Add your Upstox credentials
UPSTOX_API_KEY=your_actual_api_key
UPSTOX_SECRET=your_actual_secret
UPSTOX_REDIRECT_URI=http://localhost:8080
```

Save: `Ctrl+O`, `Enter`, `Ctrl+X`

---

## Part 6: Initial Login & Start Services (5 minutes)

### Step 7: Login to Upstox (One-time)

```bash
cd ~/option-chain/OptionChainUsingUpstock
source venv/bin/activate
python initial_login.py
```

This will:
1. Show you an authorization URL
2. Open it in your browser
3. Login to Upstox
4. Copy the code from redirect URL
5. Paste it in terminal
6. Save tokens to `data/upstox_tokens.json`

### Step 8: Start All Services

```bash
# Start token auto-refresh service (refreshes every hour)
sudo systemctl start option-chain-token-refresh
sudo systemctl status option-chain-token-refresh

# Start background data collector
sudo systemctl start option-chain-worker
sudo systemctl status option-chain-worker

# Start Streamlit dashboard
sudo systemctl start option-chain-dashboard
sudo systemctl status option-chain-dashboard
```

All should show **active (running)** in green ✅

### Step 9: Access Your Dashboard

Open browser: `http://YOUR_PUBLIC_IP`

🎉 **Your dashboard is now live 24/7!**

---

## Part 7: Enable SSL (Optional - 10 minutes)

### Step 10: Setup Free HTTPS with Let's Encrypt

**Prerequisites**: You need a domain name (free options: freenom.com, afraid.org)

1. **Point domain to VM**:
   - Add A record: `optionchain.yourdomain.com` → `YOUR_PUBLIC_IP`

2. **Get SSL certificate**:
```bash
sudo certbot --nginx -d optionchain.yourdomain.com
```

3. Follow prompts, certbot will auto-configure Nginx

4. Access: `https://optionchain.yourdomain.com` 🔒

---

## 🔧 Management Commands

### Check Service Status
```bash
sudo systemctl status option-chain-token-refresh
sudo systemctl status option-chain-worker
sudo systemctl status option-chain-dashboard
```

### View Logs
```bash
# Token refresh logs
tail -f ~/option-chain/OptionChainUsingUpstock/logs/token-refresh.log

# Worker logs
tail -f ~/option-chain/OptionChainUsingUpstock/logs/worker.log

# Dashboard logs
tail -f ~/option-chain/OptionChainUsingUpstock/logs/dashboard.log
```

### Restart Services
```bash
sudo systemctl restart option-chain-token-refresh
sudo systemctl restart option-chain-worker
sudo systemctl restart option-chain-dashboard
```

### Stop Services
```bash
sudo systemctl stop option-chain-token-refresh
sudo systemctl stop option-chain-worker
sudo systemctl stop option-chain-dashboard
```

### Update Code
```bash
cd ~/option-chain/OptionChainUsingUpstock
git pull  # If using GitHub

# Or upload new version
# Then restart services
sudo systemctl restart option-chain-worker
sudo systemctl restart option-chain-dashboard
```

---

## 🔄 How Auto Token Refresh Works

1. **Initial Login** (once): You run `initial_login.py` to get first tokens
2. **Token Storage**: Tokens saved to `data/upstox_tokens.json`
3. **Auto Refresh Service**: Runs every hour, checks token expiry
4. **Automatic Refresh**: If token expires in <1 hour, auto-refreshes
5. **Background Worker**: Loads fresh token from file every minute
6. **Dashboard**: Loads fresh token on every page load

**You never need to login again!** 🎉

---

## 📊 System Architecture

```
┌─────────────────────────────────────────┐
│      Oracle Cloud VM (Always Free)      │
├─────────────────────────────────────────┤
│                                          │
│  ┌────────────────────────────────────┐ │
│  │  Token Refresh Service (systemd)   │ │
│  │  - Checks every 60 minutes         │ │
│  │  - Auto-refreshes tokens           │ │
│  │  - Saves to upstox_tokens.json     │ │
│  └────────────────────────────────────┘ │
│               ↓ updates                  │
│  ┌────────────────────────────────────┐ │
│  │    upstox_tokens.json (file)       │ │
│  └────────────────────────────────────┘ │
│         ↓ reads           ↓ reads        │
│  ┌──────────────┐   ┌─────────────────┐ │
│  │   Worker     │   │   Dashboard     │ │
│  │  (systemd)   │   │   (systemd)     │ │
│  └──────────────┘   └─────────────────┘ │
│         ↓                    ↓           │
│  ┌─────────────────────────────────────┐│
│  │   PostgreSQL + TimescaleDB          ││
│  └─────────────────────────────────────┘│
│                                          │
│  ┌─────────────────────────────────────┐│
│  │   Nginx (Reverse Proxy)             ││
│  └─────────────────────────────────────┘│
└─────────────────────────────────────────┘
              ↓
         Public IP :80
              ↓
    🌐 Your Dashboard (24/7)
```

---

## 💰 Cost Breakdown

| Resource | Free Tier | Your Usage | Cost |
|----------|-----------|------------|------|
| VM | 2× 1GB ARM | 1× 6GB | **$0** |
| Storage | 200GB | ~5GB | **$0** |
| Bandwidth | 10TB/month | ~100GB | **$0** |
| Database | N/A (self-hosted) | PostgreSQL | **$0** |
| **TOTAL** | | | **$0/month** |

---

## 🛟 Troubleshooting

### Services Won't Start
```bash
# Check logs for errors
sudo journalctl -u option-chain-worker -n 50
sudo journalctl -u option-chain-dashboard -n 50

# Check if ports are in use
sudo netstat -tlnp | grep 8502
```

### Token Refresh Fails
```bash
# Check token refresh service
sudo systemctl status option-chain-token-refresh
tail -f ~/option-chain/OptionChainUsingUpstock/logs/token-refresh.log

# Manual refresh test
cd ~/option-chain/OptionChainUsingUpstock
source venv/bin/activate
python initial_login.py
```

### Can't Access Dashboard
```bash
# Check nginx
sudo systemctl status nginx
sudo nginx -t

# Check firewall (Oracle Cloud)
# Make sure ports 80/443 are open in Security List

# Check VM firewall
sudo iptables -L -n | grep 80
```

### Database Connection Error
```bash
# Check PostgreSQL
sudo systemctl status postgresql

# Test connection
psql -h localhost -U optionuser -d optionchain
# Password: (from .env file)
```

---

## 🎯 Next Steps

1. ✅ **Monitor**: Set up monitoring (optional)
   ```bash
   sudo apt install htop
   htop  # View CPU/memory usage
   ```

2. ✅ **Backups**: Setup daily database backups
   ```bash
   # Add to crontab
   crontab -e
   # Add: 0 2 * * * pg_dump optionchain > ~/backups/db_$(date +\%Y\%m\%d).sql
   ```

3. ✅ **Alerts**: Get notified if services go down
   - Use https://uptimerobot.com (free)
   - Monitor: `http://YOUR_IP/health`

4. ✅ **Custom Domain**: Point your domain to VM
   - Free domains: freenom.com, afraid.org
   - Or buy: namecheap.com ($1-5/year)

5. ✅ **SSL Certificate**: Enable HTTPS (see Step 10)

---

## 📞 Support

**Oracle Cloud Issues**: https://docs.oracle.com/en-us/iaas/
**Upstox API**: https://upstox.com/developer/api-documentation/
**PostgreSQL**: https://www.postgresql.org/docs/

---

**Enjoy your FREE 24/7 Option Chain Analysis Dashboard!** 🎉

Total Setup Time: **~45 minutes**  
Monthly Cost: **$0** ✅  
Uptime: **99.9%** 🚀
