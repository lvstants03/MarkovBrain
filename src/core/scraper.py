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
            logger.info("No fetch URL configured. Falling back to dynamic fetch_latest_info.")
            return await self.fetch_latest_info()
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
    async def fetch_latest_info(self) -> int:
        from urllib.parse import urlparse, parse_qs
        
        domain = "vip.ee8833.me"
        token = ""
        try:
            parsed = urlparse(self.ws_url)
            if parsed.netloc:
                domain = parsed.netloc
            query_params = parse_qs(parsed.query)
            if "token" in query_params:
                token = query_params["token"][0]
        except Exception as e:
            logger.error(f"Error parsing ws_url: {e}")

        # Fetch tu ca lich su (drawResult) va ky hien tai (getCurrentLotteryInfo)
        url_draw = f"https://{domain}/server/lottery/drawResult?lottery_id=45&page=1&limit=50"
        url_info = f"https://{domain}/server/lottery/getCurrentLotteryInfo?lottery_id=45"
        if token:
            url_draw += f"&token={token}"
            url_info += f"&token={token}"
        urls = [url_draw, url_info]
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json, text/plain, */*"
        }
        if token:
            headers["token"] = token
            headers["Authorization"] = f"Bearer {token}"
            
        imported_count = 0
        
        def extract_records(data) -> list:
            records = []
            if isinstance(data, list):
                for item in data:
                    records.extend(extract_records(item))
            elif isinstance(data, dict):
                last_issue = str(data.get("last_issue") or "")
                issue = str(data.get("issue") or "")
                digits = data.get("open_numbers_formatted") or data.get("openNumbers") or []
                if isinstance(digits, str):
                    digits = digits.split(",")
                numbers = [int(x) for x in digits if str(x).strip().isdigit()]
                
                if len(numbers) == 5:
                    # Neu co last_issue (completed), thi open_numbers_formatted thuoc ve no, tranh lech 1 ky.
                    target_issue = last_issue if last_issue else issue
                    if target_issue:
                        records.append((target_issue, numbers))
                
                for k, v in data.items():
                    if k not in ("issue", "last_issue", "open_numbers_formatted", "openNumbers"):
                        records.extend(extract_records(v))
            return records

        for url in urls:
            try:
                logger.info(f"Auto-fetching from: {url}")
                response = await asyncio.to_thread(
                    requests.get,
                    url,
                    headers=headers,
                    timeout=3
                )
                if response.status_code != 200:
                    logger.warning(f"Fetch failed for {url} with status code: {response.status_code}")
                    continue
                    
                payload = response.json()
                extracted = extract_records(payload)
                for issue, numbers in extracted:
                    added = store.add_record(issue, numbers)
                    if added:
                        logger.info(f"Auto-imported draw result: {issue} -> {numbers}")
                        imported_count += 1
                
                # Trích xuất dữ liệu lịch sử thống kê Tài/Xỉu, Chẵn/Lẻ từ statisticsInfo
                try:
                    total_sum = payload.get("data", {}).get("statisticsInfo", {}).get("total_sum", {})
                    if not total_sum:
                        total_sum = payload.get("statisticsInfo", {}).get("total_sum", {})
                    if total_sum:
                        data_list = total_sum.get("statisticDataList", {})
                        big_small_list = data_list.get("bigSmall", [])
                        odd_even_list = data_list.get("oddEven", [])
                        
                        issue_data = {}
                        for item in big_small_list:
                            iss = item.get("issue")
                            res = item.get("result")
                            if iss and res:
                                issue_data[iss] = {"is_tai": res == "big"}
                        for item in odd_even_list:
                            iss = item.get("issue")
                            res = item.get("result")
                            if iss and res:
                                if iss in issue_data:
                                    issue_data[iss]["is_le"] = res == "odd"
                                else:
                                    issue_data[iss] = {"is_le": res == "odd", "is_tai": False}
                        
                        for iss, info in issue_data.items():
                            if "is_tai" in info and "is_le" in info:
                                added = store.add_calculated_record(iss, info["is_tai"], info["is_le"])
                                if added:
                                    imported_count += 1
                except Exception as ex:
                    logger.error(f"Error parsing statisticsInfo: {ex}")
            except Exception as e:
                logger.error(f"Error fetching from {url}: {e}")
                
        return imported_count

    async def _run_fallback_simulation(self):
        # Che do gia lap da bi tat theo yeu cau. Chi log thong bao.
        logger.info("Simulation mode is disabled. No simulated data will be generated.")

scraper = WebSocketScraper()
