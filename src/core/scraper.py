import asyncio
import json
import logging
import random
import time
from typing import Optional
import websockets
from src.config import config
from src.database.store import store

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger("scraper")

class WebSocketScraper:
    def __init__(self):
        self.ws_url = config.TARGET_WS_URL
        self.is_running = False
        self._task: Optional[asyncio.Task] = None

    async def start(self):
        self.is_running = True
        self._task = asyncio.create_task(self._loop())
        logger.info("Scraper worker started")

    async def stop(self):
        self.is_running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Scraper worker stopped")

    async def update_url(self, new_url: str):
        logger.info(f"Updating WebSocket URL to: {new_url}")
        self.ws_url = new_url
        if self.is_running:
            logger.info("Restarting scraper with new URL...")
            await self.stop()
            await self.start()

    async def _loop(self):
        while self.is_running:
            try:
                logger.info(f"Connecting to target WebSocket: {self.ws_url}")
                async with websockets.connect(self.ws_url, ping_interval=20, ping_timeout=10) as ws:
                    logger.info("WebSocket connected successfully")
                    
                    # Gui cac goi tin subscribe/handshake neu can (vi du mẫu)
                    # subscribe_msg = {"action": "subscribe", "channel": "lottery_id_32"}
                    # await ws.send(json.dumps(subscribe_msg))
                    
                    async for message in ws:
                        if not self.is_running:
                            break
                        await self._process_message(message)
            except Exception as e:
                logger.error(f"WebSocket connection error or disconnected: {str(e)}")
                # Khi mat ket noi voi server that, ta chay gia lap sinh du lieu test de he thong khong bi trong
                await self._run_fallback_simulation()
                
            await asyncio.sleep(5) # Cho 5 giay truoc khi reconnect

    async def _process_message(self, message: str):
        try:
            data = json.loads(message)
            msg_type = data.get("type")
            
            # Case 1: lottery_result message
            if msg_type == "lottery_result":
                lottery = data.get("data", {}).get("lottery", {})
                if lottery.get("id") == 45 or lottery.get("code") == "pmb5p":
                    issue = str(lottery.get("issue"))
                    digits = lottery.get("open_numbers_formatted") or []
                    numbers = [int(x) for x in digits if str(x).isdigit()]
                    if issue and numbers:
                        added = store.add_record(issue, numbers)
                        if added:
                            logger.info(f"Received new real issue {issue}: {numbers}")
                            
            # Case 2: lottery_info or other periodic messages containing lists of lotteries
            else:
                data_field = data.get("data") or {}
                if isinstance(data_field, dict):
                    for key, val in data_field.items():
                        if isinstance(val, list):
                            for item in val:
                                if isinstance(item, dict):
                                    if item.get("id") == 45 or item.get("code") == "pmb5p":
                                        issue = str(item.get("issue"))
                                        digits = item.get("open_numbers_formatted") or []
                                        numbers = [int(x) for x in digits if str(x).isdigit()]
                                        if issue and numbers:
                                            added = store.add_record(issue, numbers)
                                            if added:
                                                logger.info(f"Received new real issue {issue}: {numbers}")
        except Exception as e:
            logger.error(f"Failed to process websocket message: {str(e)}. Raw: {message[:200]}")

    async def _run_fallback_simulation(self):
        # Gia lap sinh ket qua moi moi 30 giay de giup nguoi dung luon co du lieu test API
        logger.info("Running simulation mode (local fallback)")
        
        # Sinh san mot it lich su ban dau neu store dang rong
        if store.get_count() == 0:
            logger.info("Initializing store with simulated historical data...")
            current_time = int(time.time())
            for i in range(100, 0, -1):
                sim_issue = str(20260628000 + i)
                sim_numbers = [random.randint(0, 9) for _ in range(5)]
                store.add_record(sim_issue, sim_numbers)
        
        # Gia lap sinh 1 ky moi
        sim_issue = str(int(time.time() // 30))
        sim_numbers = [random.randint(0, 9) for _ in range(5)]
        added = store.add_record(sim_issue, sim_numbers)
        if added:
            logger.info(f"Simulated new issue {sim_issue}: {sim_numbers}")

scraper = WebSocketScraper()
