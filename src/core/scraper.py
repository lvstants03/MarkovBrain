import asyncio
import json
import logging
import random
import time
from typing import Optional
import websockets
import requests
from src.config import config
from src.database.store import store

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger("scraper")

class WebSocketScraper:
    def __init__(self):
        self.ws_url = config.TARGET_WS_URL
        self.is_running = False
        self._task: Optional[asyncio.Task] = None
        self._fetch_task: Optional[asyncio.Task] = None
        self.fetch_url = config.DRAWS_RESULT_URL
        self.fetch_interval = config.AUTO_FETCH_INTERVAL
        self.fetch_headers = config.DRAWS_RESULT_HEADERS

    async def start(self):
        self.is_running = True
        self._task = asyncio.create_task(self._loop())
        self._fetch_task = asyncio.create_task(self._fetch_loop())
        logger.info("Scraper worker started")

    async def stop(self):
        self.is_running = False
        tasks = []
        if self._task:
            self._task.cancel()
            tasks.append(self._task)
        if self._fetch_task:
            self._fetch_task.cancel()
            tasks.append(self._fetch_task)
        if tasks:
            try:
                await asyncio.gather(*tasks, return_exceptions=True)
            except Exception:
                pass
        logger.info("Scraper worker stopped")

    async def update_url(self, new_url: str):
        logger.info(f"Updating WebSocket URL to: {new_url}")
        self.ws_url = new_url
        if self.is_running:
            logger.info("Restarting scraper with new URL...")
            await self.stop()
            await self.start()

    async def update_fetch_config(self, new_url: str, new_interval: int, new_headers: dict = None):
        logger.info(f"Updating fetch URL to: {new_url}, interval: {new_interval}")
        self.fetch_url = new_url
        self.fetch_interval = new_interval
        if new_headers is not None:
            self.fetch_headers = new_headers
        if self.is_running:
            if self._fetch_task:
                self._fetch_task.cancel()
                try:
                    await self._fetch_task
                except asyncio.CancelledError:
                    pass
            self._fetch_task = asyncio.create_task(self._fetch_loop())

    async def trigger_fetch(self) -> int:
        if not self.fetch_url:
            logger.warning("No fetch URL configured")
            return 0
        try:
            logger.info(f"Triggering automated fetch from: {self.fetch_url}")
            headers = self.fetch_headers if self.fetch_headers else {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
            response = await asyncio.to_thread(
                requests.get,
                self.fetch_url,
                headers=headers,
                timeout=10
            )
            if response.status_code != 200:
                logger.error(f"Fetch failed with status code: {response.status_code}")
                return 0
            payload = response.json()
            draw_list = []
            if "data" in payload and isinstance(payload["data"], dict) and "list" in payload["data"]:
                draw_list = payload["data"]["list"]
            elif "list" in payload and isinstance(payload["list"], list):
                draw_list = payload["list"]
            elif isinstance(payload, list):
                draw_list = payload
            imported_count = 0
            for item in draw_list:
                if not isinstance(item, dict):
                    continue
                issue = str(item.get("issue") or "")
                digits = item.get("open_numbers_formatted") or []
                numbers = [int(x) for x in digits if str(x).isdigit()]
                if issue and len(numbers) == 5:
                    added = store.add_record(issue, numbers)
                    if added:
                        imported_count += 1
            logger.info(f"Fetch completed: imported {imported_count} new records")
            return imported_count
        except Exception as e:
            logger.error(f"Error during automated fetch: {str(e)}")
            return 0

    async def _fetch_loop(self):
        while self.is_running:
            if self.fetch_url:
                await self.trigger_fetch()
            # Cho den chu ky tiếp theo
            await asyncio.sleep(self.fetch_interval)

    async def _loop(self):
        retry_delay = 2.0
        max_delay = 60.0
        while self.is_running:
            try:
                logger.info(f"Connecting to target WebSocket: {self.ws_url}")
                async with websockets.connect(self.ws_url, ping_interval=20, ping_timeout=10) as ws:
                    logger.info("WebSocket connected successfully")
                    retry_delay = 2.0  # Reset delay
                    
                    async for message in ws:
                        if not self.is_running:
                            break
                        await self._process_message(message)
            except Exception as e:
                logger.error(f"WebSocket connection error or disconnected: {str(e)}")
                await self._run_fallback_simulation()
                
            logger.info(f"Waiting {retry_delay}s before reconnecting...")
            await asyncio.sleep(retry_delay)
            retry_delay = min(retry_delay * 2, max_delay)

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
