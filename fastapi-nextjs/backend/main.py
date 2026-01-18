"""
FastAPI Backend - Option Chain Analysis
Reuses all existing Python code, just adds REST API
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from typing import Optional, Dict, Any
import asyncio
import json
import logging
from datetime import datetime, timedelta
from contextlib import asynccontextmanager

# Import existing modules (reuse 100% of your code)
import sys
import os

# Add parent directory to path to import existing modules
parent_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
sys.path.insert(0, parent_dir)

from database import TimescaleDBManager
from upstox_api import UpstoxAPI
from token_manager import get_token_manager

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Database connection
db = TimescaleDBManager()

# Lifespan context for startup/shutdown
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("🚀 FastAPI server starting...")
    yield
    # Shutdown
    logger.info("🛑 FastAPI server shutting down...")

# Create FastAPI app
app = FastAPI(
    title="Option Chain Analysis API",
    description="High-performance API for real-time option chain gamma exposure analysis",
    version="2.0.0",
    lifespan=lifespan
)

# CORS middleware (allow Next.js frontend)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3001"],  # Next.js dev server
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================================
# REST API ENDPOINTS
# ============================================================================

@app.get("/")
async def root():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "Option Chain Analysis API",
        "version": "2.0.0",
        "timestamp": datetime.now().isoformat()
    }

@app.get("/api/symbols")
async def get_symbols():
    """Get list of all active symbols"""
    try:
        with db.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT DISTINCT symbol 
                    FROM gamma_exposure_history 
                    ORDER BY symbol
                """)
                symbols = [row[0] for row in cur.fetchall()]
        
        return {"symbols": symbols, "count": len(symbols)}
    except Exception as e:
        logger.error(f"Error fetching symbols: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/gamma/all")
async def get_all_gamma_data():
    """Get latest gamma data for all symbols - used by HTTP polling"""
    try:
        data = await get_latest_gamma_data()
        return {"data": data, "count": len(data), "timestamp": datetime.now().isoformat()}
    except Exception as e:
        logger.error(f"Error fetching all gamma data: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/gamma/{symbol}")
async def get_gamma_exposure(symbol: str):
    """Get latest gamma exposure data for a symbol"""
    try:
        with db.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT 
                        symbol, expiry_date, timestamp, atm_strike,
                        net_gex, total_positive_gex, total_negative_gex,
                        zero_gamma_level, atm_iv, iv_velocity, iv_percentile,
                        atm_oi, oi_velocity, oi_acceleration,
                        gamma_concentration, gamma_blast_probability,
                        predicted_direction, confidence_level,
                        time_to_blast_minutes
                    FROM gamma_exposure_history
                    WHERE symbol = %s
                    ORDER BY timestamp DESC
                    LIMIT 1
                """, (symbol,))
                
                row = cur.fetchone()
                
                if not row:
                    raise HTTPException(status_code=404, detail=f"No data found for {symbol}")
                
                return {
                    "symbol": row[0],
                    "expiry_date": row[1].isoformat() if row[1] else None,
                    "timestamp": row[2].isoformat(),
                    "atm_strike": float(row[3]) if row[3] else None,
                    "net_gex": float(row[4]) if row[4] else 0,
                    "total_positive_gex": float(row[5]) if row[5] else 0,
                    "total_negative_gex": float(row[6]) if row[6] else 0,
                    "zero_gamma_level": float(row[7]) if row[7] else None,
                    "atm_iv": float(row[8]) if row[8] else 0,
                    "iv_velocity": float(row[9]) if row[9] else 0,
                    "iv_percentile": float(row[10]) if row[10] else 0,
                    "atm_oi": float(row[11]) if row[11] else 0,
                    "oi_velocity": float(row[12]) if row[12] else 0,
                    "oi_acceleration": float(row[13]) if row[13] else 0,
                    "gamma_concentration": float(row[14]) if row[14] else 0,
                    "gamma_blast_probability": float(row[15]) if row[15] else 0,
                    "predicted_direction": row[16],
                    "confidence_level": row[17],
                    "time_to_blast_minutes": float(row[18]) if row[18] else None
                }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching gamma data for {symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/gamma/history/{symbol}")
async def get_gamma_history(symbol: str, hours: int = 24):
    """Get historical gamma exposure data for a symbol - filtered by current expiry"""
    try:
        with db.get_connection() as conn:
            with conn.cursor() as cur:
                # First get the current (nearest) expiry for this symbol
                cur.execute("""
                    SELECT MIN(expiry_date) 
                    FROM gamma_exposure_history 
                    WHERE symbol = %s AND expiry_date >= CURRENT_DATE
                """, (symbol,))
                result = cur.fetchone()
                
                if result and result[0]:
                    current_expiry = result[0]
                else:
                    # Fallback to latest expiry if no future expiry found
                    cur.execute("""
                        SELECT MAX(expiry_date) FROM gamma_exposure_history WHERE symbol = %s
                    """, (symbol,))
                    result = cur.fetchone()
                    current_expiry = result[0] if result else None
                
                if not current_expiry:
                    return {"symbol": symbol, "data": [], "count": 0, "expiry": None}
                
                # Now fetch data filtered by current expiry only
                cur.execute("""
                    SELECT 
                        timestamp, net_gex, atm_iv, atm_oi,
                        gamma_blast_probability, oi_velocity, iv_velocity
                    FROM gamma_exposure_history
                    WHERE symbol = %s 
                        AND expiry_date = %s
                        AND timestamp > NOW() - INTERVAL '%s hours'
                    ORDER BY timestamp ASC
                """, (symbol, current_expiry, hours))
                
                rows = cur.fetchall()
                
                return {
                    "symbol": symbol,
                    "expiry": str(current_expiry),
                    "data": [
                        {
                            "timestamp": row[0].isoformat(),
                            "net_gex": float(row[1]) if row[1] else 0,
                            "atm_iv": float(row[2]) if row[2] else 0,
                            "atm_oi": float(row[3]) if row[3] else 0,
                            "gamma_blast_probability": float(row[4]) if row[4] else 0,
                            "oi_velocity": float(row[5]) if row[5] else 0,
                            "iv_velocity": float(row[6]) if row[6] else 0
                        }
                        for row in rows
                    ],
                    "count": len(rows)
                }
    except Exception as e:
        logger.error(f"Error fetching history for {symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/indices")
async def get_indices_overview():
    """Get overview of all indices (NIFTY, BANKNIFTY, etc.)"""
    indices = ["NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "SENSEX"]
    
    try:
        results = []
        with db.get_connection() as conn:
            with conn.cursor() as cur:
                for symbol in indices:
                    # First get the current (nearest) expiry
                    cur.execute("""
                        SELECT MIN(expiry_date) 
                        FROM gamma_exposure_history 
                        WHERE symbol = %s AND expiry_date >= CURRENT_DATE
                    """, (symbol,))
                    expiry_result = cur.fetchone()
                    current_expiry = expiry_result[0] if expiry_result and expiry_result[0] else None
                    
                    if not current_expiry:
                        cur.execute("""
                            SELECT MAX(expiry_date) FROM gamma_exposure_history WHERE symbol = %s
                        """, (symbol,))
                        expiry_result = cur.fetchone()
                        current_expiry = expiry_result[0] if expiry_result else None
                    
                    if not current_expiry:
                        continue
                    
                    cur.execute("""
                        SELECT 
                            symbol, timestamp, net_gex, atm_iv, atm_oi,
                            gamma_blast_probability, predicted_direction,
                            oi_velocity, iv_velocity
                        FROM gamma_exposure_history
                        WHERE symbol = %s AND expiry_date = %s
                        ORDER BY timestamp DESC
                        LIMIT 1
                    """, (symbol, current_expiry))
                    
                    row = cur.fetchone()
                    if row:
                        results.append({
                            "symbol": row[0],
                            "timestamp": row[1].isoformat(),
                            "net_gex": float(row[2]) if row[2] else 0,
                            "atm_iv": float(row[3]) if row[3] else 0,
                            "atm_oi": float(row[4]) if row[4] else 0,
                            "gamma_blast_probability": float(row[5]) if row[5] else 0,
                            "predicted_direction": row[6],
                            "oi_velocity": float(row[7]) if row[7] else 0,
                            "iv_velocity": float(row[8]) if row[8] else 0
                        })
        
        return {"indices": results, "count": len(results)}
    except Exception as e:
        logger.error(f"Error fetching indices overview: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================================
# HELPER FUNCTION - Position Signal (Same as Streamlit)
# ============================================================================

def get_position_signal(ltp: float, change: float, chg_oi: float) -> str:
    """Determine position type based on price change and change in OI - Same as Streamlit"""
    if change == 0 and chg_oi == 0:
        return "No Change"
    
    price_up = change > 0
    price_down = change < 0
    oi_increase = chg_oi > 0
    oi_decrease = chg_oi < 0
    
    if price_up and oi_increase:
        return "Long Build"
    elif price_down and oi_decrease:
        return "Long Unwinding"
    elif price_down and oi_increase:
        return "Short Buildup"
    elif price_up and oi_decrease:
        return "Short Covering"
    elif oi_increase and change == 0:
        return "Fresh Positions"
    elif oi_decrease and change == 0:
        return "Position Unwinding"
    else:
        return "Mixed Activity"

# ============================================================================
# NEW API ENDPOINTS - Option Chain, Sentiment, ITM Analysis
# ============================================================================

@app.get("/api/option-chain/{symbol}")
async def get_option_chain(symbol: str, expiry: Optional[str] = None):
    """Get full option chain data for a symbol - 100% matching Streamlit calculations"""
    try:
        # Get available expiries if not provided
        if not expiry:
            with db.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT DISTINCT expiry_date 
                        FROM option_chain_data 
                        WHERE symbol = %s
                        ORDER BY expiry_date
                        LIMIT 1
                    """, (symbol,))
                    row = cur.fetchone()
                    if not row:
                        raise HTTPException(status_code=404, detail=f"No option chain data for {symbol}")
                    expiry = row[0].isoformat()
        
        # Get latest option chain data - need to pivot from long to wide format
        with db.get_connection() as conn:
            with conn.cursor() as cur:
                # Get latest timestamp first
                cur.execute("""
                    SELECT MAX(timestamp) 
                    FROM option_chain_data
                    WHERE symbol = %s AND expiry_date = %s
                """, (symbol, expiry))
                latest_ts = cur.fetchone()[0]
                
                if not latest_ts:
                    raise HTTPException(status_code=404, detail=f"No option chain data for {symbol} expiry {expiry}")
                
                # Get all strikes with both CE and PE data
                cur.execute("""
                    WITH latest_data AS (
                        SELECT 
                            strike_price, spot_price, timestamp,
                            option_type,
                            ltp, change, oi, chg_oi, volume,
                            iv, delta, gamma, theta, vega
                        FROM option_chain_data
                        WHERE symbol = %s 
                          AND expiry_date = %s
                          AND timestamp = %s
                    )
                    SELECT 
                        strike_price,
                        MAX(spot_price) as spot_price,
                        MAX(timestamp) as timestamp,
                        MAX(CASE WHEN option_type = 'CE' THEN ltp END) as ce_ltp,
                        MAX(CASE WHEN option_type = 'CE' THEN change END) as ce_change,
                        MAX(CASE WHEN option_type = 'CE' THEN oi END) as ce_oi,
                        MAX(CASE WHEN option_type = 'CE' THEN chg_oi END) as ce_chg_oi,
                        MAX(CASE WHEN option_type = 'CE' THEN volume END) as ce_volume,
                        MAX(CASE WHEN option_type = 'CE' THEN iv END) as ce_iv,
                        MAX(CASE WHEN option_type = 'CE' THEN delta END) as ce_delta,
                        MAX(CASE WHEN option_type = 'CE' THEN gamma END) as ce_gamma,
                        MAX(CASE WHEN option_type = 'CE' THEN theta END) as ce_theta,
                        MAX(CASE WHEN option_type = 'CE' THEN vega END) as ce_vega,
                        MAX(CASE WHEN option_type = 'PE' THEN ltp END) as pe_ltp,
                        MAX(CASE WHEN option_type = 'PE' THEN change END) as pe_change,
                        MAX(CASE WHEN option_type = 'PE' THEN oi END) as pe_oi,
                        MAX(CASE WHEN option_type = 'PE' THEN chg_oi END) as pe_chg_oi,
                        MAX(CASE WHEN option_type = 'PE' THEN volume END) as pe_volume,
                        MAX(CASE WHEN option_type = 'PE' THEN iv END) as pe_iv,
                        MAX(CASE WHEN option_type = 'PE' THEN delta END) as pe_delta,
                        MAX(CASE WHEN option_type = 'PE' THEN gamma END) as pe_gamma,
                        MAX(CASE WHEN option_type = 'PE' THEN theta END) as pe_theta,
                        MAX(CASE WHEN option_type = 'PE' THEN vega END) as pe_vega
                    FROM latest_data
                    GROUP BY strike_price
                    ORDER BY strike_price
                """, (symbol, expiry, latest_ts))
                
                rows = cur.fetchall()
                
                if not rows:
                    raise HTTPException(status_code=404, detail=f"No option chain data for {symbol} expiry {expiry}")
                
                spot_price = float(rows[0][1]) if rows[0][1] else 0
                timestamp = rows[0][2].isoformat() if rows[0][2] else None
                
                strikes = []
                for row in rows:
                    strike = float(row[0])
                    
                    # Calculate position signals (same logic as Streamlit)
                    ce_position = get_position_signal(
                        float(row[3]) if row[3] else 0,
                        float(row[4]) if row[4] else 0,
                        float(row[6]) if row[6] else 0
                    )
                    pe_position = get_position_signal(
                        float(row[13]) if row[13] else 0,
                        float(row[14]) if row[14] else 0,
                        float(row[16]) if row[16] else 0
                    )
                    
                    strikes.append({
                        "strike": strike,
                        "is_atm": False,  # Will be set later to only the nearest strike
                        "call": {
                            "ltp": float(row[3]) if row[3] else 0,
                            "change": float(row[4]) if row[4] else 0,
                            "oi": int(row[5]) if row[5] else 0,
                            "chg_oi": int(row[6]) if row[6] else 0,
                            "volume": int(row[7]) if row[7] else 0,
                            "iv": float(row[8]) if row[8] else 0,
                            "delta": float(row[9]) if row[9] else 0,
                            "gamma": float(row[10]) if row[10] else 0,
                            "theta": float(row[11]) if row[11] else 0,
                            "vega": float(row[12]) if row[12] else 0,
                            "position": ce_position
                        },
                        "put": {
                            "ltp": float(row[13]) if row[13] else 0,
                            "change": float(row[14]) if row[14] else 0,
                            "oi": int(row[15]) if row[15] else 0,
                            "chg_oi": int(row[16]) if row[16] else 0,
                            "volume": int(row[17]) if row[17] else 0,
                            "iv": float(row[18]) if row[18] else 0,
                            "delta": float(row[19]) if row[19] else 0,
                            "gamma": float(row[20]) if row[20] else 0,
                            "theta": float(row[21]) if row[21] else 0,
                            "vega": float(row[22]) if row[22] else 0,
                            "position": pe_position
                        }
                    })
                
                # Mark only the nearest strike as ATM
                if strikes:
                    nearest_strike = min(strikes, key=lambda s: abs(s["strike"] - spot_price))
                    nearest_strike["is_atm"] = True
                
                # Calculate PCR ratios (same as Streamlit)
                total_ce_oi = sum(s["call"]["oi"] for s in strikes)
                total_pe_oi = sum(s["put"]["oi"] for s in strikes)
                total_ce_volume = sum(s["call"]["volume"] for s in strikes)
                total_pe_volume = sum(s["put"]["volume"] for s in strikes)
                total_ce_chgoi = sum(s["call"]["chg_oi"] for s in strikes)
                total_pe_chgoi = sum(s["put"]["chg_oi"] for s in strikes)
                
                pcr_oi = total_pe_oi / total_ce_oi if total_ce_oi > 0 else 0
                pcr_volume = total_pe_volume / total_ce_volume if total_ce_volume > 0 else 0
                pcr_chgoi = total_pe_chgoi / total_ce_chgoi if total_ce_chgoi != 0 else 0
                
                return {
                    "symbol": symbol,
                    "expiry": expiry,
                    "spot_price": spot_price,
                    "timestamp": timestamp,
                    "strikes": strikes,
                    "pcr": {
                        "oi": round(pcr_oi, 3),
                        "volume": round(pcr_volume, 3),
                        "chg_oi": round(pcr_chgoi, 3)
                    },
                    "totals": {
                        "ce_oi": int(total_ce_oi),
                        "pe_oi": int(total_pe_oi),
                        "ce_volume": int(total_ce_volume),
                        "pe_volume": int(total_pe_volume)
                    }
                }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching option chain: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/sentiment/{symbol}")
async def get_sentiment_analysis(symbol: str, hours: int = 4):
    """Get sentiment analysis data - 100% matching Streamlit calculations"""
    try:
        with db.get_connection() as conn:
            with conn.cursor() as cur:
                # Get sentiment history
                cur.execute("""
                    SELECT 
                        timestamp, sentiment_score, sentiment, confidence,
                        spot_price, pcr_oi, pcr_chgoi, pcr_volume
                    FROM sentiment_scores
                    WHERE symbol = %s
                      AND timestamp > NOW() - INTERVAL '%s hours'
                    ORDER BY timestamp DESC
                """, (symbol, hours))
                
                rows = cur.fetchall()
                
                if not rows:
                    raise HTTPException(status_code=404, detail=f"No sentiment data for {symbol}")
                
                # Latest sentiment
                latest = rows[0]
                
                # Historical trend
                history = [
                    {
                        "timestamp": row[0].isoformat(),
                        "sentiment_score": float(row[1]) if row[1] else 0,
                        "sentiment": row[2],
                        "confidence": row[3],
                        "spot_price": float(row[4]) if row[4] else 0,
                        "pcr_oi": float(row[5]) if row[5] else 0,
                        "pcr_chgoi": float(row[6]) if row[6] else 0,
                        "pcr_volume": float(row[7]) if row[7] else 0
                    }
                    for row in reversed(rows)  # Oldest to newest for chart
                ]
                
                return {
                    "symbol": symbol,
                    "current": {
                        "timestamp": latest[0].isoformat(),
                        "sentiment_score": float(latest[1]) if latest[1] else 0,
                        "sentiment": latest[2],
                        "confidence": latest[3],
                        "spot_price": float(latest[4]) if latest[4] else 0,
                        "pcr_oi": float(latest[5]) if latest[5] else 0,
                        "pcr_chgoi": float(latest[6]) if latest[6] else 0,
                        "pcr_volume": float(latest[7]) if latest[7] else 0
                    },
                    "history": history,
                    "data_points": len(history)
                }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching sentiment data: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/expiries/{symbol}")
async def get_available_expiries(symbol: str):
    """Get available expiry dates for a symbol from the database"""
    try:
        with db.get_connection() as conn:
            with conn.cursor() as cur:
                # Get expiries from option_chain_data (only future dates - today and onwards)
                cur.execute("""
                    SELECT DISTINCT expiry_date 
                    FROM option_chain_data 
                    WHERE symbol = %s 
                      AND expiry_date >= CURRENT_DATE
                    ORDER BY expiry_date
                """, (symbol,))
                
                option_expiries = [row[0].isoformat() for row in cur.fetchall()]
                
                # Get expiries from itm_bucket_summaries (only future dates - today and onwards)
                cur.execute("""
                    SELECT DISTINCT expiry_date 
                    FROM itm_bucket_summaries 
                    WHERE symbol = %s
                      AND expiry_date >= CURRENT_DATE
                    ORDER BY expiry_date
                """, (symbol,))
                
                itm_expiries = [row[0].isoformat() for row in cur.fetchall()]
                
                # Combine and deduplicate
                all_expiries = sorted(list(set(option_expiries + itm_expiries)))
                
                return {
                    "symbol": symbol,
                    "expiries": all_expiries,
                    "option_chain_expiries": option_expiries,
                    "itm_expiries": itm_expiries,
                    "count": len(all_expiries)
                }
    except Exception as e:
        logger.error(f"Error fetching expiries for {symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/itm/{symbol}")
async def get_itm_analysis(symbol: str, expiry: str, itm_count: int = 1, hours: int = 24):
    """Get ITM (In-The-Money) analysis - 100% matching Streamlit calculations"""
    try:
        # Get ITM bucket summaries from database
        with db.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT 
                        timestamp, itm_count,
                        ce_oi, pe_oi,
                        ce_volume, pe_volume,
                        ce_chgoi, pe_chgoi,
                        spot_price
                    FROM itm_bucket_summaries
                    WHERE symbol = %s 
                      AND expiry_date = %s
                      AND itm_count = %s
                      AND timestamp > NOW() - INTERVAL '%s hours'
                    ORDER BY timestamp ASC
                """, (symbol, expiry, itm_count, hours))
                
                rows = cur.fetchall()
                
                if not rows:
                    raise HTTPException(
                        status_code=404, 
                        detail=f"No ITM data for {symbol} expiry {expiry} with {itm_count} strikes in last {hours} hours"
                    )
                
                # Format data for charts
                data_points = [
                    {
                        "timestamp": row[0].isoformat(),
                        "itm_count": int(row[1]),
                        "ce_oi": int(row[2]) if row[2] else 0,
                        "pe_oi": int(row[3]) if row[3] else 0,
                        "ce_volume": int(row[4]) if row[4] else 0,
                        "pe_volume": int(row[5]) if row[5] else 0,
                        "ce_chgoi": int(row[6]) if row[6] else 0,
                        "pe_chgoi": int(row[7]) if row[7] else 0,
                        "spot_price": float(row[8]) if row[8] else 0
                    }
                    for row in rows
                ]
                
                # Calculate statistics (same as Streamlit)
                latest = data_points[-1] if data_points else None
                
                return {
                    "symbol": symbol,
                    "expiry": expiry,
                    "itm_count": itm_count,
                    "hours": hours,
                    "data_points": len(data_points),
                    "latest": latest,
                    "history": data_points,
                    "summary": {
                        "avg_ce_oi": int(sum(d["ce_oi"] for d in data_points) / len(data_points)) if data_points else 0,
                        "avg_pe_oi": int(sum(d["pe_oi"] for d in data_points) / len(data_points)) if data_points else 0,
                        "max_ce_oi": max((d["ce_oi"] for d in data_points), default=0),
                        "max_pe_oi": max((d["pe_oi"] for d in data_points), default=0)
                    }
                }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching ITM data: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/bucket-summary/{symbol}")
async def get_bucket_summary(symbol: str, expiry: str):
    """Get ITM/OTM bucket summaries with Greeks - matching Streamlit"""
    try:
        with db.get_connection() as conn:
            with conn.cursor() as cur:
                # Get latest option chain data
                cur.execute("""
                    SELECT MAX(timestamp) 
                    FROM option_chain_data
                    WHERE symbol = %s AND expiry_date = %s
                """, (symbol, expiry))
                latest_ts = cur.fetchone()[0]
                
                if not latest_ts:
                    raise HTTPException(status_code=404, detail=f"No data for {symbol} expiry {expiry}")
                
                # Get all strikes with pivot
                cur.execute("""
                    WITH latest_data AS (
                        SELECT 
                            strike_price, spot_price, option_type,
                            oi, chg_oi, volume, iv, delta, gamma, theta, vega
                        FROM option_chain_data
                        WHERE symbol = %s AND expiry_date = %s AND timestamp = %s
                    )
                    SELECT 
                        strike_price,
                        MAX(spot_price) as spot_price,
                        MAX(CASE WHEN option_type = 'CE' THEN oi END) as ce_oi,
                        MAX(CASE WHEN option_type = 'CE' THEN chg_oi END) as ce_chg_oi,
                        MAX(CASE WHEN option_type = 'CE' THEN volume END) as ce_volume,
                        MAX(CASE WHEN option_type = 'CE' THEN iv END) as ce_iv,
                        MAX(CASE WHEN option_type = 'CE' THEN delta END) as ce_delta,
                        MAX(CASE WHEN option_type = 'CE' THEN gamma END) as ce_gamma,
                        MAX(CASE WHEN option_type = 'CE' THEN theta END) as ce_theta,
                        MAX(CASE WHEN option_type = 'CE' THEN vega END) as ce_vega,
                        MAX(CASE WHEN option_type = 'PE' THEN oi END) as pe_oi,
                        MAX(CASE WHEN option_type = 'PE' THEN chg_oi END) as pe_chg_oi,
                        MAX(CASE WHEN option_type = 'PE' THEN volume END) as pe_volume,
                        MAX(CASE WHEN option_type = 'PE' THEN iv END) as pe_iv,
                        MAX(CASE WHEN option_type = 'PE' THEN delta END) as pe_delta,
                        MAX(CASE WHEN option_type = 'PE' THEN gamma END) as pe_gamma,
                        MAX(CASE WHEN option_type = 'PE' THEN theta END) as pe_theta,
                        MAX(CASE WHEN option_type = 'PE' THEN vega END) as pe_vega
                    FROM latest_data
                    GROUP BY strike_price
                    ORDER BY strike_price
                """, (symbol, expiry, latest_ts))
                
                rows = cur.fetchall()
                if not rows:
                    raise HTTPException(status_code=404, detail="No strikes found")
                
                spot_price = float(rows[0][1]) if rows[0][1] else 0
                
                # Find ATM strike
                atm_strike = float(min(rows, key=lambda r: abs(float(r[0]) - spot_price))[0])
                
                # Separate ITM and OTM (same logic as Streamlit)
                ce_itm_data = [r for r in rows if float(r[0]) < atm_strike]
                ce_otm_data = [r for r in rows if float(r[0]) > atm_strike]
                pe_itm_data = [r for r in rows if float(r[0]) > atm_strike]
                pe_otm_data = [r for r in rows if float(r[0]) < atm_strike]
                
                def aggregate_bucket(data, side_idx_offset):
                    """Aggregate bucket - matching Streamlit logic"""
                    if not data:
                        return {"oi": 0, "chg_oi": 0, "volume": 0, "iv": 0, "delta": 0, "gamma": 0, "theta": 0, "vega": 0}
                    
                    total_oi = sum(float(r[2 + side_idx_offset]) or 0 for r in data)
                    if total_oi == 0:
                        return {"oi": 0, "chg_oi": 0, "volume": 0, "iv": 0, "delta": 0, "gamma": 0, "theta": 0, "vega": 0}
                    
                    # Weight Greeks by OI
                    weighted_delta = sum((float(r[6 + side_idx_offset]) or 0) * (float(r[2 + side_idx_offset]) or 0) for r in data) / total_oi
                    weighted_gamma = sum((float(r[7 + side_idx_offset]) or 0) * (float(r[2 + side_idx_offset]) or 0) for r in data) / total_oi
                    weighted_theta = sum((float(r[8 + side_idx_offset]) or 0) * (float(r[2 + side_idx_offset]) or 0) for r in data) / total_oi
                    weighted_vega = sum((float(r[9 + side_idx_offset]) or 0) * (float(r[2 + side_idx_offset]) or 0) for r in data) / total_oi
                    
                    return {
                        "oi": int(total_oi),
                        "chg_oi": int(sum(float(r[3 + side_idx_offset]) or 0 for r in data)),
                        "volume": int(sum(float(r[4 + side_idx_offset]) or 0 for r in data)),
                        "iv": sum(float(r[5 + side_idx_offset]) or 0 for r in data) / len(data),
                        "delta": weighted_delta,
                        "gamma": weighted_gamma,
                        "theta": weighted_theta,
                        "vega": weighted_vega
                    }
                
                # Calculate buckets (CE columns start at index 2, PE at index 10)
                ce_itm = aggregate_bucket(ce_itm_data, 0)
                ce_otm = aggregate_bucket(ce_otm_data, 0)
                pe_itm = aggregate_bucket(pe_itm_data, 8)
                pe_otm = aggregate_bucket(pe_otm_data, 8)
                
                # Calculate PCR ratios (same as Streamlit)
                def safe_pcr(pe_val, ce_val):
                    return round(pe_val / ce_val, 3) if ce_val != 0 else 0
                
                pcr = {
                    "itm_oi": safe_pcr(pe_itm["oi"], ce_itm["oi"]),
                    "otm_oi": safe_pcr(pe_otm["oi"], ce_otm["oi"]),
                    "overall_oi": safe_pcr(pe_itm["oi"] + pe_otm["oi"], ce_itm["oi"] + ce_otm["oi"]),
                    "itm_chgoi": safe_pcr(pe_itm["chg_oi"], ce_itm["chg_oi"]),
                    "otm_chgoi": safe_pcr(pe_otm["chg_oi"], ce_otm["chg_oi"]),
                    "overall_chgoi": safe_pcr(pe_itm["chg_oi"] + pe_otm["chg_oi"], ce_itm["chg_oi"] + ce_otm["chg_oi"]),
                    "itm_volume": safe_pcr(pe_itm["volume"], ce_itm["volume"]),
                    "otm_volume": safe_pcr(pe_otm["volume"], ce_otm["volume"]),
                    "overall_volume": safe_pcr(pe_itm["volume"] + pe_otm["volume"], ce_itm["volume"] + ce_otm["volume"])
                }
                
                return {
                    "symbol": symbol,
                    "expiry": expiry,
                    "atm_strike": float(atm_strike),
                    "spot_price": spot_price,
                    "buckets": {
                        "ce_itm": ce_itm,
                        "ce_otm": ce_otm,
                        "pe_itm": pe_itm,
                        "pe_otm": pe_otm
                    },
                    "pcr": pcr
                }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error calculating bucket summary: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/volatility-skew/{symbol}")
async def get_volatility_skew(symbol: str, expiry: str):
    """Get volatility skew analysis - matching Streamlit"""
    try:
        with db.get_connection() as conn:
            with conn.cursor() as cur:
                # Get latest data
                cur.execute("""
                    SELECT MAX(timestamp) 
                    FROM option_chain_data
                    WHERE symbol = %s AND expiry_date = %s
                """, (symbol, expiry))
                latest_ts = cur.fetchone()[0]
                
                if not latest_ts:
                    raise HTTPException(status_code=404, detail="No data found")
                
                cur.execute("""
                    WITH latest_data AS (
                        SELECT 
                            strike_price, spot_price, option_type, iv
                        FROM option_chain_data
                        WHERE symbol = %s AND expiry_date = %s AND timestamp = %s
                    )
                    SELECT 
                        strike_price,
                        MAX(spot_price) as spot_price,
                        MAX(CASE WHEN option_type = 'CE' THEN iv END) as ce_iv,
                        MAX(CASE WHEN option_type = 'PE' THEN iv END) as pe_iv
                    FROM latest_data
                    GROUP BY strike_price
                    ORDER BY strike_price
                """, (symbol, expiry, latest_ts))
                
                rows = cur.fetchall()
                if not rows:
                    raise HTTPException(status_code=404, detail="No volatility data")
                
                spot_price = float(rows[0][1])
                
                # Find ATM IV
                atm_row = min(rows, key=lambda r: abs(float(r[0]) - spot_price))
                atm_iv = (float(atm_row[2] or 0) + float(atm_row[3] or 0)) / 2
                
                # Calculate skew data
                skew_points = []
                for row in rows:
                    strike = float(row[0])
                    ce_iv = float(row[2]) if row[2] else 0
                    pe_iv = float(row[3]) if row[3] else 0
                    
                    moneyness = spot_price / strike
                    
                    skew_points.append({
                        "strike": strike,
                        "ce_iv": ce_iv,
                        "pe_iv": pe_iv,
                        "moneyness": moneyness,
                        "ce_skew": ce_iv - atm_iv,
                        "pe_skew": pe_iv - atm_iv
                    })
                
                # Calculate skew metrics (same as Streamlit)
                otm_puts = [p for p in skew_points if p["moneyness"] < 1]
                otm_calls = [p for p in skew_points if p["moneyness"] > 1]
                
                otm_put_iv = sum(p["pe_iv"] for p in otm_puts) / len(otm_puts) if otm_puts else 0
                otm_call_iv = sum(p["ce_iv"] for p in otm_calls) / len(otm_calls) if otm_calls else 0
                risk_reversal = otm_put_iv - otm_call_iv
                
                otm_avg_iv = (otm_put_iv + otm_call_iv) / 2 if (otm_puts or otm_calls) else 0
                butterfly = atm_iv - otm_avg_iv
                
                return {
                    "symbol": symbol,
                    "expiry": expiry,
                    "atm_iv": round(atm_iv, 2),
                    "spot_price": spot_price,
                    "metrics": {
                        "risk_reversal": round(risk_reversal, 2),
                        "butterfly": round(butterfly, 2)
                    },
                    "skew_points": skew_points
                }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error calculating volatility skew: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/support-resistance/{symbol}")
async def get_support_resistance(symbol: str, expiry: str):
    """Get support and resistance levels - matching Streamlit"""
    try:
        with db.get_connection() as conn:
            with conn.cursor() as cur:
                # Get latest data
                cur.execute("""
                    SELECT MAX(timestamp) 
                    FROM option_chain_data
                    WHERE symbol = %s AND expiry_date = %s
                """, (symbol, expiry))
                latest_ts = cur.fetchone()[0]
                
                if not latest_ts:
                    raise HTTPException(status_code=404, detail="No data found")
                
                cur.execute("""
                    WITH latest_data AS (
                        SELECT 
                            strike_price, spot_price, option_type,
                            oi, volume
                        FROM option_chain_data
                        WHERE symbol = %s AND expiry_date = %s AND timestamp = %s
                    )
                    SELECT 
                        strike_price,
                        MAX(spot_price) as spot_price,
                        MAX(CASE WHEN option_type = 'CE' THEN oi END) as ce_oi,
                        MAX(CASE WHEN option_type = 'CE' THEN volume END) as ce_volume,
                        MAX(CASE WHEN option_type = 'PE' THEN oi END) as pe_oi,
                        MAX(CASE WHEN option_type = 'PE' THEN volume END) as pe_volume
                    FROM latest_data
                    GROUP BY strike_price
                    ORDER BY strike_price
                """, (symbol, expiry, latest_ts))
                
                rows = cur.fetchall()
                if not rows:
                    raise HTTPException(status_code=404, detail="No support/resistance data")
                
                spot_price = float(rows[0][1])
                
                # Calculate strength (same as Streamlit: OI * log(Volume))
                import math
                
                levels = []
                for row in rows:
                    strike = float(row[0])
                    ce_oi = int(row[2]) if row[2] else 0
                    ce_volume = int(row[3]) if row[3] else 0
                    pe_oi = int(row[4]) if row[4] else 0
                    pe_volume = int(row[5]) if row[5] else 0
                    
                    ce_strength = ce_oi * math.log1p(ce_volume)
                    pe_strength = pe_oi * math.log1p(pe_volume)
                    
                    distance_pct = abs(strike - spot_price) / spot_price * 100
                    
                    levels.append({
                        "strike": strike,
                        "ce_strength": ce_strength,
                        "pe_strength": pe_strength,
                        "distance_pct": distance_pct
                    })
                
                # Find significant levels
                total_ce_strength = sum(l["ce_strength"] for l in levels)
                total_pe_strength = sum(l["pe_strength"] for l in levels)
                
                ce_threshold = sum(l["ce_strength"] for l in levels) / len(levels) * 1.5
                pe_threshold = sum(l["pe_strength"] for l in levels) / len(levels) * 1.5
                
                supports = []
                resistances = []
                
                for level in levels:
                    # Resistance (calls above spot)
                    if level["strike"] > spot_price and level["ce_strength"] > ce_threshold:
                        resistances.append({
                            "level": level["strike"],
                            "strength": "Strong" if level["ce_strength"] > ce_threshold * 1.5 else "Moderate",
                            "distance_pct": round(level["distance_pct"], 2)
                        })
                    
                    # Support (puts below spot)
                    if level["strike"] < spot_price and level["pe_strength"] > pe_threshold:
                        supports.append({
                            "level": level["strike"],
                            "strength": "Strong" if level["pe_strength"] > pe_threshold * 1.5 else "Moderate",
                            "distance_pct": round(level["distance_pct"], 2)
                        })
                
                # Sort by strength and take top 3
                supports.sort(key=lambda x: x["distance_pct"])
                resistances.sort(key=lambda x: x["distance_pct"])
                
                return {
                    "symbol": symbol,
                    "expiry": expiry,
                    "spot_price": spot_price,
                    "supports": supports[:3],
                    "resistances": resistances[:3]
                }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error calculating support/resistance: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/put-call-parity/{symbol}")
async def get_put_call_parity(symbol: str, expiry: str):
    """Get Put-Call Parity Analysis for OTM equidistant pairs - matching Streamlit"""
    try:
        with db.get_connection() as conn:
            with conn.cursor() as cur:
                # Get latest data
                cur.execute("""
                    SELECT MAX(timestamp) 
                    FROM option_chain_data
                    WHERE symbol = %s AND expiry_date = %s
                """, (symbol, expiry))
                latest_ts = cur.fetchone()[0]
                
                if not latest_ts:
                    raise HTTPException(status_code=404, detail="No data found")
                
                cur.execute("""
                    WITH latest_data AS (
                        SELECT 
                            strike_price, spot_price, option_type,
                            ltp, iv
                        FROM option_chain_data
                        WHERE symbol = %s AND expiry_date = %s AND timestamp = %s
                    )
                    SELECT 
                        strike_price,
                        MAX(spot_price) as spot_price,
                        MAX(CASE WHEN option_type = 'CE' THEN ltp END) as ce_ltp,
                        MAX(CASE WHEN option_type = 'CE' THEN iv END) as ce_iv,
                        MAX(CASE WHEN option_type = 'PE' THEN ltp END) as pe_ltp,
                        MAX(CASE WHEN option_type = 'PE' THEN iv END) as pe_iv
                    FROM latest_data
                    GROUP BY strike_price
                    ORDER BY strike_price
                """, (symbol, expiry, latest_ts))
                
                rows = cur.fetchall()
                if not rows:
                    raise HTTPException(status_code=404, detail="No parity data")
                
                spot_price = float(rows[0][1])
                atm_strike = float(min(rows, key=lambda r: abs(float(r[0]) - spot_price))[0])
                
                # Separate OTM calls and puts
                otm_calls = [r for r in rows if float(r[0]) > atm_strike]
                otm_puts = [r for r in rows if float(r[0]) < atm_strike]
                
                parity_pairs = []
                
                for call_row in otm_calls:
                    call_strike = float(call_row[0])
                    call_distance = call_strike - atm_strike
                    target_put_strike = atm_strike - call_distance
                    
                    # Find matching put
                    put_row = next((r for r in otm_puts if abs(float(r[0]) - target_put_strike) < 0.01), None)
                    
                    if put_row:
                        ce_ltp = float(call_row[2]) if call_row[2] else 0
                        pe_ltp = float(put_row[4]) if put_row[4] else 0
                        ce_iv = float(call_row[3]) if call_row[3] else 0
                        pe_iv = float(put_row[5]) if put_row[5] else 0
                        
                        actual_diff = ce_ltp - pe_ltp
                        deviation_pct = (actual_diff / pe_ltp) * 100 if pe_ltp > 0 else 0
                        
                        mispricing = "Overvalued" if actual_diff > 0 else "Undervalued" if actual_diff < 0 else "Fair"
                        
                        parity_pairs.append({
                            "distance": int(call_distance),
                            "call_strike": int(call_strike),
                            "put_strike": int(target_put_strike),
                            "call_price": round(ce_ltp, 2),
                            "put_price": round(pe_ltp, 2),
                            "call_iv": round(ce_iv, 2),
                            "put_iv": round(pe_iv, 2),
                            "deviation_pct": round(deviation_pct, 2),
                            "mispricing": mispricing
                        })
                
                return {
                    "symbol": symbol,
                    "expiry": expiry,
                    "atm_strike": float(atm_strike),
                    "spot_price": spot_price,
                    "parity_pairs": parity_pairs
                }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error calculating put-call parity: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/top-blasts")
async def get_top_gamma_blasts(limit: int = 10):
    """Get symbols with highest gamma blast probability"""
    try:
        with db.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    WITH latest_data AS (
                        SELECT DISTINCT ON (symbol)
                            symbol, timestamp, gamma_blast_probability,
                            predicted_direction, confidence_level,
                            net_gex, atm_iv, oi_velocity
                        FROM gamma_exposure_history
                        WHERE timestamp > NOW() - INTERVAL '1 hour'
                        ORDER BY symbol, timestamp DESC
                    )
                    SELECT * FROM latest_data
                    WHERE gamma_blast_probability > 0.3
                    ORDER BY gamma_blast_probability DESC
                    LIMIT %s
                """, (limit,))
                
                rows = cur.fetchall()
                
                return {
                    "top_blasts": [
                        {
                            "symbol": row[0],
                            "timestamp": row[1].isoformat(),
                            "probability": float(row[2]),
                            "direction": row[3],
                            "confidence": row[4],
                            "net_gex": float(row[5]) if row[5] else 0,
                            "atm_iv": float(row[6]) if row[6] else 0,
                            "oi_velocity": float(row[7]) if row[7] else 0
                        }
                        for row in rows
                    ],
                    "count": len(rows)
                }
    except Exception as e:
        logger.error(f"Error fetching top blasts: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

async def get_latest_gamma_data():
    """Get latest gamma data for all symbols"""
    try:
        with db.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT DISTINCT ON (symbol)
                        symbol, timestamp, net_gex, atm_iv, atm_oi,
                        gamma_blast_probability, predicted_direction,
                        oi_velocity, iv_velocity, gamma_concentration
                    FROM gamma_exposure_history
                    WHERE timestamp > NOW() - INTERVAL '1 hour'
                    ORDER BY symbol, timestamp DESC
                """)
                
                rows = cur.fetchall()
                
                return [
                    {
                        "symbol": row[0],
                        "timestamp": row[1].isoformat(),
                        "net_gex": float(row[2]) if row[2] else 0,
                        "atm_iv": float(row[3]) if row[3] else 0,
                        "atm_oi": float(row[4]) if row[4] else 0,
                        "gamma_blast_probability": float(row[5]) if row[5] else 0,
                        "predicted_direction": row[6],
                        "oi_velocity": float(row[7]) if row[7] else 0,
                        "iv_velocity": float(row[8]) if row[8] else 0,
                        "gamma_concentration": float(row[9]) if row[9] else 0
                    }
                    for row in rows
                ]
    except Exception as e:
        logger.error(f"Error fetching latest data: {e}")
        return []

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
