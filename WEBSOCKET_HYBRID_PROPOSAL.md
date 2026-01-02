# WebSocket + REST Hybrid Architecture Proposal

## Current Issues
1. **30-second delay** - Data feels stale even with optimizations
2. **Full cycle time** - 215 symbols takes 30-60 seconds to complete
3. **No real-time prices** - Spot price and LTP update only every 30 seconds
4. **Rate limit concerns** - Must stay within API limits

## Proposed Hybrid Solution

### Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    BACKGROUND SERVICE                       │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌──────────────────┐         ┌──────────────────┐        │
│  │  WebSocket       │         │  REST API        │        │
│  │  (Real-time)     │         │  (Periodic)      │        │
│  ├──────────────────┤         ├──────────────────┤        │
│  │ • Spot Price     │         │ • Option Chain   │        │
│  │ • Strike LTP     │         │ • OI             │        │
│  │ • Bid/Ask        │         │ • IV             │        │
│  │ • Volume         │         │ • Greeks         │        │
│  │                  │         │                  │        │
│  │ Update: < 1 sec  │         │ Update: 2-5 min  │        │
│  └────────┬─────────┘         └────────┬─────────┘        │
│           │                            │                   │
│           └────────────┬───────────────┘                   │
│                        ▼                                   │
│              ┌──────────────────┐                          │
│              │   MERGE LAYER    │                          │
│              │                  │                          │
│              │ Combine:         │                          │
│              │ • Real-time LTP  │                          │
│              │ • Periodic OI/IV │                          │
│              │ • Live prices    │                          │
│              └────────┬─────────┘                          │
│                       ▼                                    │
│              ┌──────────────────┐                          │
│              │    DATABASE      │                          │
│              │  (TimescaleDB)   │                          │
│              └──────────────────┘                          │
└─────────────────────────────────────────────────────────────┘
```

### Implementation Strategy

#### Phase 1: WebSocket for Key Symbols (Indices + Top 50 stocks)
- Subscribe to NIFTY, BANKNIFTY, FINNIFTY, SENSEX, MIDCPNIFTY
- Subscribe to top 50 liquid F&O stocks
- **Benefit:** Real-time price updates for most-watched symbols
- **Overhead:** ~55 WebSocket subscriptions (low resource usage)

#### Phase 2: Reduce REST API Frequency
- Change option chain refresh from 30 sec → 2-5 minutes
- Focus on OI changes, IV updates, Greeks recalculation
- **Benefit:** Drastically reduce API calls, avoid rate limits
- **Trade-off:** OI/IV update slower (acceptable since they change gradually)

#### Phase 3: Smart Update Logic
```python
# Real-time (WebSocket) - Every tick
- Spot price
- ATM strike LTP
- Volume spikes
- Price breakouts

# Periodic (REST API) - Every 2-5 minutes
- Full option chain snapshot
- OI changes
- IV recalculation
- Greeks update
- Gamma exposure

# Calculated (On-demand)
- Gamma blast probability (uses real-time spot + periodic OI/IV)
- PCR ratio (uses periodic OI)
- ITM analysis (uses periodic data)
```

## Benefits

### 1. **Truly Real-Time Dashboard**
   - Spot price updates < 1 second
   - LTP updates instantly
   - Volume spikes detected immediately
   - Price breakouts trigger alerts in real-time

### 2. **Reduced API Load**
   - From: 215 symbols × 2 calls every 30 sec = **860 calls/min**
   - To: 55 symbols WebSocket + 215 symbols every 5 min = **86 calls/min**
   - **90% reduction in API calls!**

### 3. **Better User Experience**
   - Charts update smoothly (not jumping every 30 sec)
   - Price movements feel live
   - No stale data feeling
   - Gamma blast detection more responsive

### 4. **No Rate Limit Issues**
   - WebSocket data is unlimited once subscribed
   - REST API calls reduced 10x
   - Can add more symbols without hitting limits

## Implementation Code Structure

```python
class HybridDataManager:
    def __init__(self):
        # WebSocket for real-time prices
        self.ws_manager = UpstoxWebSocketManager()
        
        # REST API for option chain
        self.rest_api = UpstoxAPI()
        
        # Separate refresh intervals
        self.ws_symbols = ['NIFTY', 'BANKNIFTY', ...top 50]  # Real-time
        self.rest_interval = 300  # 5 minutes for option chain
        
    def start_realtime_stream(self):
        """Subscribe to WebSocket for spot prices and LTP"""
        for symbol in self.ws_symbols:
            self.ws_manager.subscribe(symbol)
        
        # Handle ticks in callback
        self.ws_manager.on_tick = self.handle_realtime_tick
    
    def handle_realtime_tick(self, tick_data):
        """Process real-time WebSocket data"""
        # Update only: spot_price, ltp, volume
        # Don't update: OI, IV, Greeks (use periodic data)
        self.db.update_realtime_price(
            symbol=tick_data['symbol'],
            spot_price=tick_data['ltp'],
            timestamp=tick_data['timestamp']
        )
        
        # Trigger gamma blast recalculation with new spot price
        self.recalculate_gamma_risk(tick_data['symbol'])
    
    def periodic_option_chain_update(self):
        """Fetch full option chain every 5 minutes"""
        while self.running:
            for symbol in self.all_symbols:
                # Fetch complete option chain
                option_data = self.rest_api.get_option_chain(symbol)
                
                # Update: OI, IV, Greeks, full snapshot
                self.db.update_option_chain(symbol, option_data)
            
            time.sleep(300)  # 5 minutes
```

## Migration Plan

### Step 1: Keep Current System Running
- No disruption to existing functionality
- Run hybrid in parallel for testing

### Step 2: Add WebSocket Layer
- Implement WebSocket manager
- Subscribe to indices + top 50 stocks
- Store real-time prices in separate table

### Step 3: Update Dashboard
- Use WebSocket data for price charts
- Use REST data for OI/IV charts
- Merge data in display layer

### Step 4: Reduce REST Frequency
- Gradually increase interval: 30s → 1min → 2min → 5min
- Monitor data quality
- Adjust based on user feedback

### Step 5: Full Cutover
- Switch dashboard to hybrid mode
- Keep REST-only mode as fallback
- Monitor performance

## Expected Performance

| Metric | Current (REST Only) | Hybrid (WebSocket + REST) |
|--------|-------------------|-------------------------|
| Price Update Latency | 30 seconds | < 1 second |
| OI Update Latency | 30 seconds | 5 minutes (acceptable) |
| API Calls per Minute | 860 | 86 (-90%) |
| Data Freshness | Batch updates | Real-time prices + periodic OI |
| Rate Limit Risk | Medium | Very Low |
| User Experience | Laggy | Smooth |

## Recommendation

**YES, implement WebSocket hybrid approach!**

### Priority Order:
1. **High Priority:** WebSocket for indices (NIFTY, BANKNIFTY, FINNIFTY) - these are watched most
2. **Medium Priority:** Top 20 liquid stocks (RELIANCE, TCS, INFY, HDFC, etc.)
3. **Low Priority:** All 215 symbols via WebSocket (if needed)

### Start Small:
- Week 1: Implement WebSocket for 5 indices
- Week 2: Add top 20 stocks
- Week 3: Adjust REST interval to 2 minutes
- Week 4: Measure and optimize

This gives you the best of both worlds: real-time responsiveness + comprehensive data coverage!
