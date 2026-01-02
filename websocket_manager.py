"""
WebSocket Manager for Upstox Market Data
Uses WebSocket to avoid rate limiting issues with REST API
"""

import asyncio
import json
import logging
import threading
import time
from queue import Queue
from typing import Dict, Set, Optional, List
from datetime import datetime
import pytz

# Optional websockets import - can work without it using REST API
try:
    import websockets
    WEBSOCKETS_AVAILABLE = True
except ImportError:
    WEBSOCKETS_AVAILABLE = False

logger = logging.getLogger(__name__)

IST = pytz.timezone('Asia/Kolkata')

# Upstox WebSocket endpoint
WEBSOCKET_URL = "wss://ws-api.upstox.com/v2/feed/market-data-feed"


class UpstoxWebSocketManager:
    """Manages WebSocket connection to Upstox for real-time market data"""
    
    def __init__(self, access_token: str):
        self.access_token = access_token
        self.websocket = None
        self.is_connected = False
        self.subscribed_instruments: Set[str] = set()
        self.data_queue = Queue()
        self.latest_data: Dict[str, Dict] = {}
        self.loop = None
        self.thread = None
        self.running = False
        
    def start(self):
        """Start WebSocket connection in a separate thread"""
        if self.running:
            logger.warning("WebSocket manager already running")
            return
            
        self.running = True
        self.thread = threading.Thread(target=self._run_async_loop, daemon=True)
        self.thread.start()
        logger.info("WebSocket manager thread started")
        
    def stop(self):
        """Stop WebSocket connection"""
        self.running = False
        if self.loop:
            asyncio.run_coroutine_threadsafe(self._disconnect(), self.loop)
        if self.thread:
            self.thread.join(timeout=5)
        logger.info("WebSocket manager stopped")
    
    def _run_async_loop(self):
        """Run asyncio event loop in a separate thread"""
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.loop.run_until_complete(self._connect_and_listen())
    
    async def _connect_and_listen(self):
        """Connect to WebSocket and start listening"""
        while self.running:
            try:
                await self._connect()
                await self._listen()
            except Exception as e:
                logger.error(f"WebSocket error: {e}")
                if self.running:
                    logger.info("Reconnecting in 10 seconds...")
                    await asyncio.sleep(10)
    
    async def _connect(self):
        """Establish WebSocket connection"""
        try:
            # Use additional_headers parameter instead of extra_headers
            additional_headers = [
                ('Authorization', f'Bearer {self.access_token}'),
                ('User-Agent', 'upstox-python-sdk')
            ]
            
            self.websocket = await websockets.connect(
                WEBSOCKET_URL,
                additional_headers=additional_headers,
                ping_interval=20,
                ping_timeout=10
            )
            self.is_connected = True
            logger.info("WebSocket connected successfully")
        except Exception as e:
            logger.error(f"WebSocket connection failed: {e}")
            self.is_connected = False
            raise
    
    async def _disconnect(self):
        """Disconnect WebSocket"""
        if self.websocket:
            try:
                await self.websocket.close()
            except:
                pass
            self.websocket = None
        self.is_connected = False
    
    async def _listen(self):
        """Listen for WebSocket messages"""
        try:
            while self.websocket and self.is_connected and self.running:
                try:
                    message = await asyncio.wait_for(self.websocket.recv(), timeout=30.0)
                    await self._process_message(message)
                except asyncio.TimeoutError:
                    # Send ping to keep connection alive
                    if self.websocket:
                        await self.websocket.ping()
                except websockets.exceptions.ConnectionClosed:
                    logger.warning("WebSocket connection closed")
                    self.is_connected = False
                    break
        except Exception as e:
            logger.error(f"WebSocket listen error: {e}")
            self.is_connected = False
    
    async def _process_message(self, message: str):
        """Process incoming WebSocket message"""
        try:
            data = json.loads(message)
            
            # Handle different message types
            if 'feeds' in data:
                # Market data update
                for instrument_key, feed_data in data['feeds'].items():
                    self.latest_data[instrument_key] = feed_data
                    self.data_queue.put({
                        'instrument_key': instrument_key,
                        'data': feed_data,
                        'timestamp': datetime.now(IST)
                    })
            elif 'action' in data:
                # Subscription confirmation or other actions
                if data.get('action') == 'sub':
                    logger.debug(f"Subscription confirmed: {data}")
                elif data.get('action') == 'unsub':
                    logger.debug(f"Unsubscription confirmed: {data}")
        except json.JSONDecodeError:
            logger.warning(f"Invalid JSON message: {message[:100]}")
        except Exception as e:
            logger.error(f"Error processing message: {e}")
    
    async def subscribe(self, instrument_keys: List[str], mode: str = 'full'):
        """Subscribe to instruments via WebSocket"""
        if not self.websocket or not self.is_connected:
            logger.warning("WebSocket not connected. Cannot subscribe.")
            return False
        
        try:
            # Filter out already subscribed instruments
            new_instruments = [key for key in instrument_keys if key not in self.subscribed_instruments]
            
            if not new_instruments:
                logger.debug("All instruments already subscribed")
                return True
            
            subscription_data = {
                "guid": f"sub_{int(time.time())}",
                "method": "sub",
                "data": {
                    "mode": mode,  # 'ltpc', 'full', 'option_greeks', 'full_d30'
                    "instrumentKeys": new_instruments
                }
            }
            
            await self.websocket.send(json.dumps(subscription_data))
            self.subscribed_instruments.update(new_instruments)
            logger.info(f"Subscribed to {len(new_instruments)} instruments via WebSocket (mode: {mode})")
            return True
        except Exception as e:
            logger.error(f"Subscription failed: {e}")
            return False
    
    async def unsubscribe(self, instrument_keys: List[str]):
        """Unsubscribe from instruments"""
        if not self.websocket or not self.is_connected:
            return False
        
        try:
            unsubscription_data = {
                "guid": f"unsub_{int(time.time())}",
                "method": "unsub",
                "data": {
                    "instrumentKeys": instrument_keys
                }
            }
            
            await self.websocket.send(json.dumps(unsubscription_data))
            self.subscribed_instruments.difference_update(instrument_keys)
            logger.info(f"Unsubscribed from {len(instrument_keys)} instruments")
            return True
        except Exception as e:
            logger.error(f"Unsubscription failed: {e}")
            return False
    
    def subscribe_sync(self, instrument_keys: List[str], mode: str = 'full'):
        """Synchronous wrapper for subscribe (for use from main thread)"""
        if self.loop and self.loop.is_running():
            asyncio.run_coroutine_threadsafe(
                self.subscribe(instrument_keys, mode),
                self.loop
            )
        else:
            logger.warning("Event loop not running. Cannot subscribe.")
    
    def get_latest_data(self, instrument_key: Optional[str] = None) -> Dict:
        """Get latest data for an instrument or all instruments"""
        if instrument_key:
            return self.latest_data.get(instrument_key, {})
        return self.latest_data.copy()
    
    def get_queued_data(self) -> List[Dict]:
        """Get all queued data updates"""
        updates = []
        while not self.data_queue.empty():
            try:
                updates.append(self.data_queue.get_nowait())
            except:
                break
        return updates

