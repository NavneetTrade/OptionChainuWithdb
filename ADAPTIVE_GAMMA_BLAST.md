# Adaptive Gamma Blast Detection System

## Overview
The system now uses **statistical z-score based adaptive thresholds** instead of constant values for gamma blast detection. This allows the detector to adapt to each symbol's unique volatility patterns and market conditions.

## Key Features

### 1. Statistical Approach
- **Z-Score Calculation**: Compares current values against historical mean and standard deviation
- **Adaptive Thresholds**: Automatically adjusts sensitivity based on recent market behavior
- **Lookback Period**: Uses last 20 data points (60 minutes of market data)
- **Minimum Data**: Requires at least 5 historical periods, otherwise falls back to simple logic

### 2. Six Detection Signals

#### Signal 1: IV Z-Score Spike
- **2.5σ threshold**: +0.25 probability (extreme volatility spike)
- **2.0σ threshold**: +0.15 probability (significant increase)
- **Trigger Example**: "IV Spike (2.8σ)" indicates IV is 2.8 standard deviations above normal

#### Signal 2: OI Acceleration Z-Score
- **-2.0σ threshold**: +0.30 probability (rapid unwinding = high risk)
- **+2.0σ threshold**: +0.20 probability (rapid buildup)
- **Acceleration**: Second derivative of OI (rate of change of the rate of change)
- **Trigger Example**: "OI Unwinding (-2.3σ)" means positions closing at 2.3σ faster than normal

#### Signal 3: Gamma Concentration Z-Score
- **2.0σ threshold**: +0.20 probability
- **Measures**: How concentrated gamma is at specific strikes
- **High concentration** = Market makers hedging at specific levels
- **Trigger Example**: "Gamma Clustering (2.4σ)"

#### Signal 4: Strike Pin Risk
- **Distance < 0.5%**: +0.10 probability
- **Non-statistical**: Direct measure of spot vs ATM strike
- **Purpose**: Detects when price is "pinned" near high OI strikes
- **Trigger Example**: "Pin Risk (0.23%)"

#### Signal 5: GEX Flip Detection
- **Zero crossing**: +0.25 probability
- **Detects**: When Net GEX changes sign (positive → negative or vice versa)
- **Significance**: Market maker hedging behavior reversal
- **Trigger Example**: "GEX Flip Detected"

#### Signal 6: GEX Extremes (Percentile-Based)
- **>90th percentile**: +0.15 probability (extreme resistance)
- **<10th percentile**: +0.15 probability (extreme support)
- **Adaptive**: Based on recent GEX distribution
- **Trigger Example**: "Extreme GEX (93rd percentile)"

### 3. Direction Prediction
Multi-factor weighted scoring system:

- **Put/Call OI Ratio**:
  - PCR < 0.7: +3 (heavy call OI = bullish)
  - PCR > 1.3: -3 (heavy put OI = bearish)
  
- **GEX Direction** (adaptive percentile):
  - GEX > 75th percentile: -2 (resistance = bearish)
  - GEX < 25th percentile: +2 (support = bullish)
  
- **IV Skew**:
  - Call IV > Put IV * 1.1: -1 (bearish expectation)
  - Put IV > Call IV * 1.1: +1 (bullish expectation)

**Final Direction**:
- Score ≥ 3: **UPSIDE**
- Score ≤ -3: **DOWNSIDE**
- -3 < Score < 3: **NEUTRAL**

### 4. Confidence Levels
Based on probability and number of triggered signals:

- **CRITICAL**: probability > 0.7 AND triggers ≥ 4 → **3 minutes to blast**
- **VERY_HIGH**: probability > 0.6 AND triggers ≥ 3 → **10 minutes to blast**
- **HIGH**: probability > 0.4 → **20 minutes to blast**
- **MEDIUM**: probability > 0.25 → **30 minutes to blast**
- **LOW**: probability ≤ 0.25 → **60 minutes to blast**

## Implementation Details

### Historical Data Query
```sql
SELECT atm_iv, atm_oi, gamma_concentration, net_gex
FROM gamma_exposure_history
WHERE symbol = %s AND expiry_date = %s
ORDER BY timestamp DESC
LIMIT 20
```

### Current Data Structure
```python
current_data = {
    'atm_iv': float,           # ATM implied volatility
    'atm_oi': float,           # ATM open interest
    'gamma_concentration': float,  # Gamma clustering metric
    'net_gex': float,          # Net gamma exposure
    'spot_price': float,       # Current spot price
    'atm_strike': float,       # Nearest ATM strike
    'ce_oi_total': float,      # Total call OI
    'pe_oi_total': float,      # Total put OI
    'ce_iv_avg': float,        # Average call IV
    'pe_iv_avg': float         # Average put IV
}
```

### Output Signal
```python
@dataclass
class GammaBlastSignal:
    probability: float         # 0.0 to 0.95 (capped)
    direction: str            # "UPSIDE", "DOWNSIDE", "NEUTRAL"
    confidence: str           # "CRITICAL", "VERY_HIGH", "HIGH", "MEDIUM", "LOW"
    time_to_blast_min: int    # 3, 10, 20, 30, or 60 minutes
    triggers: List[str]       # List of activated signals
    risk_level: str           # "CRITICAL", "VERY_HIGH", "HIGH", "MEDIUM", "LOW"
```

## Advantages Over Previous System

### Old System (Constant Thresholds)
- ❌ Fixed thresholds (e.g., IV velocity > 0.1)
- ❌ Same sensitivity for all symbols
- ❌ Doesn't adapt to different market conditions
- ❌ Base probability of 0.1 even with no signals

### New System (Adaptive Z-Scores)
- ✅ **Symbol-specific**: Each symbol has its own baseline
- ✅ **Regime-aware**: Adapts to current volatility regime
- ✅ **Statistical confidence**: Z-scores provide probabilistic meaning
- ✅ **Starts at 0.0**: Only increases with actual signals
- ✅ **Transparent**: Logs all triggers for debugging
- ✅ **Acceleration metrics**: Second derivative for early detection

## Logging Example
```
BANKNIFTY Adaptive Gamma Blast: 67.5% | Triggers: IV Spike (2.8σ), OI Unwinding (-2.3σ), GEX Flip Detected, Extreme GEX (93rd percentile)
```

## Fallback Mode
When insufficient historical data (< 5 periods):
- Uses simple constant thresholds temporarily
- Base probability: 0.1
- Basic signals: IV velocity > 0.1, OI acceleration < -500, gamma trend > 0
- Direction: NEUTRAL, Confidence: LOW
- Automatically switches to adaptive mode as history accumulates

## Database Storage
All metrics stored in `gamma_exposure_history` table:
- `gamma_blast_probability`: float (0.0 - 0.95)
- `predicted_direction`: varchar ("UPSIDE"/"DOWNSIDE"/"NEUTRAL")
- `confidence_level`: varchar ("CRITICAL"/"VERY_HIGH"/"HIGH"/"MEDIUM"/"LOW")
- `time_to_blast_minutes`: integer (3/10/20/30/60)

## Usage in Dashboard
The sentiment_dashboard.py automatically displays:
- Gamma blast probability with color coding
- Predicted direction with arrow indicators
- Confidence level badges
- Time to blast countdown
- Historical trend charts

## Performance Notes
- Z-score calculation: O(n) where n = 20 (very fast)
- Database query: ~12ms for 20 records
- Total overhead: < 50ms per symbol per refresh
- No impact on 180-second refresh cycle
