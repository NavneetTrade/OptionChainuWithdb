"""
FastAPI Backend - Option Chain Analysis
Reuses all existing Python code, just adds REST API + WebSocket
"""

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from typing import List, Optional, Dict, Any
import asyncio
import json
import logging
from datetime import datetime, timedelta
from contextlib import asynccontextmanager

# Import existing modules (reuse 100% of your code)
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

from database import DatabaseManager
from upstox_api import UpstoxAPI
from token_manager import get_token_manager

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Database connection
db = DatabaseManager()

# Active WebSocket connections for real-time updates
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"Client connected. Total connections: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)
        logger.info(f"Client disconnected. Total connections: {len(self.active_connections)}")

    async def broadcast(self, message: dict):
        """Send message to all connected clients"""
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.error(f"Error sending to client: {e}")
                disconnected.append(connection)
        
        # Remove disconnected clients
        for conn in disconnected:
            self.active_connections.remove(conn)

manager = ConnectionManager()

# Background task for real-time updates
async def broadcast_updates():
    """Send real-time updates to all connected clients"""
    while True:
        try:
            # Fetch latest data from database
            latest_data = await get_latest_gamma_data()
            
            if latest_data:
                await manager.broadcast({
                    "type": "gamma_update",
                    "data": latest_data,
                    "timestamp": datetime.now().isoformat()
                })
            
            # Update every 5 seconds
            await asyncio.sleep(5)
            
        except Exception as e:
            logger.error(f"Error in broadcast loop: {e}")
            await asyncio.sleep(5)

# Lifespan context for startup/shutdown
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("🚀 FastAPI server starting...")
    # Start background task for real-time updates
    task = asyncio.create_task(broadcast_updates())
    yield
    # Shutdown
    logger.info("🛑 FastAPI server shutting down...")
    task.cancel()

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
    """Get historical gamma exposure data for a symbol"""
    try:
        with db.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT 
                        timestamp, net_gex, atm_iv, atm_oi,
                        gamma_blast_probability, oi_velocity, iv_velocity
                    FROM gamma_exposure_history
                    WHERE symbol = %s 
                        AND timestamp > NOW() - INTERVAL '%s hours'
                    ORDER BY timestamp ASC
                """, (symbol, hours))
                
                rows = cur.fetchall()
                
                return {
                    "symbol": symbol,
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
                    cur.execute("""
                        SELECT 
                            symbol, timestamp, net_gex, atm_iv, atm_oi,
                            gamma_blast_probability, predicted_direction,
                            oi_velocity, iv_velocity
                        FROM gamma_exposure_history
                        WHERE symbol = %s
                        ORDER BY timestamp DESC
                        LIMIT 1
                    """, (symbol,))
                    
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
# WEBSOCKET ENDPOINT (Real-time Updates)
# ============================================================================

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time data streaming"""
    await manager.connect(websocket)
    
    try:
        # Send initial data on connect
        initial_data = await get_latest_gamma_data()
        await websocket.send_json({
            "type": "initial",
            "data": initial_data
        })
        
        # Keep connection alive and listen for client messages
        while True:
            data = await websocket.receive_text()
            # Client can request specific symbol updates
            message = json.loads(data)
            
            if message.get("type") == "subscribe":
                symbol = message.get("symbol")
                # Send symbol-specific data
                symbol_data = await get_gamma_exposure(symbol)
                await websocket.send_json({
                    "type": "symbol_update",
                    "symbol": symbol,
                    "data": symbol_data
                })
                
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        manager.disconnect(websocket)

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
