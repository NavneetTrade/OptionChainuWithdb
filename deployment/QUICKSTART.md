# 🚀 Quick Start - Oracle Cloud Free Deployment

## TL;DR - 5 Steps to Free 24/7 Deployment

### 1. Sign Up Oracle Cloud
```
→ https://cloud.oracle.com/free
→ Choose region: Mumbai (ap-mumbai-1)
→ Free: 2 VMs, 200GB storage, forever
```

### 2. Create VM
```
Compute → Create Instance
- Ubuntu 22.04
- Shape: VM.Standard.A1.Flex (1 OCPU, 6GB RAM)
- Download SSH key
- Open ports: 80, 443 in Security List
```

### 3. Upload & Run Setup
```bash
# On VM (SSH)
wget https://raw.githubusercontent.com/YOUR_REPO/main/deployment/oracle-cloud-setup.sh
chmod +x oracle-cloud-setup.sh
./oracle-cloud-setup.sh
```

### 4. Configure & Login
```bash
# Edit credentials
nano .env

# Initial Upstox login (one-time)
source venv/bin/activate
python initial_login.py
```

### 5. Start Services
```bash
sudo systemctl start option-chain-token-refresh  # Auto-refresh tokens
sudo systemctl start option-chain-worker         # Data collection
sudo systemctl start option-chain-dashboard      # Web UI
```

---

## Access Dashboard
```
http://YOUR_PUBLIC_IP
```

---

## Key Features

✅ **Auto Token Refresh**: Refreshes every hour automatically  
✅ **24/7 Uptime**: No sleep, always running  
✅ **Free Forever**: Oracle Always Free tier  
✅ **Auto Restart**: Services restart if they crash  
✅ **Logs**: All logs in `~/option-chain/OptionChainUsingUpstock/logs/`  

---

## Quick Commands

```bash
# Check status
sudo systemctl status option-chain-*

# View logs
tail -f ~/option-chain/OptionChainUsingUpstock/logs/worker.log

# Restart
sudo systemctl restart option-chain-worker

# Stop
sudo systemctl stop option-chain-*
```

---

## Cost: $0/month 🎉
