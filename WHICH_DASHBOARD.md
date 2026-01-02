# 🎯 WHICH DASHBOARD TO USE?

## 📊 TWO DASHBOARDS AVAILABLE:

### 1. Simple Dashboard (Modern HTML) - Port 8501
**Start:** `./start_system.sh`  
**URL:** http://localhost:8501

**Features:**
- ✅ Real-time sentiment signals
- ✅ Gamma exposure charts
- ✅ WebSocket auto-updates
- ✅ Fast & lightweight
- ✅ Good for quick overview

**Best for:**
- Quick sentiment checks
- Monitoring multiple symbols
- Real-time alerts
- Mobile/tablet friendly

---

### 2. Full Analysis (Streamlit) - Port 8502
**Start:** `./start_full_analysis.sh`  
**URL:** http://localhost:8502

**Features:**
- ✅ **Bucket Summaries** (ITM/OTM for CE/PE)
- ✅ **PCR Analysis** (OI/ChgOI/Volume)
- ✅ **Gamma Exposure & GEX Analysis**
- ✅ **Option Chain Table** with all Greeks
- ✅ **Sentiment Score** with component breakdown
- ✅ **Position Tracking** (Long/Short Build/Covering)
- ✅ **ITM Filtering** (3/5/7 strikes)
- ✅ **All calculations and logic from original**

**Best for:**
- Deep option chain analysis
- Detailed PCR metrics
- Greek analysis
- Trading decisions
- Complete market view

---

## 🚀 QUICK START:

### For Full Features (Recommended):
```bash
./start_full_analysis.sh
```
Then open: **http://localhost:8502**

### For Simple Dashboard:
```bash
./start_system.sh
```
Then open: **http://localhost:8501**

---

## ⏹️ TO STOP EITHER:
```bash
./stop_system.sh
```

---

## 💡 RECOMMENDATION:

**Use Full Analysis (8502)** - It has ALL the logic you want:
- Complete bucket summaries
- Comprehensive PCR analysis  
- Gamma exposure calculations
- All Greeks (Delta, Gamma, Theta, Vega)
- Position tracking
- Everything from the original Streamlit app!

The simple dashboard (8501) is just for quick sentiment overview.
