import asyncio
import json
import logging
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
        self.last_received_time = time.time()
        self.connection_status = "disconnected"

        self._reconnect_attempts = 0
        self._max_reconnect_attempts = 3

    async def start(self):
        self.is_running = True
        self._task = asyncio.create_task(self._loop())
        self._fetch_task = asyncio.create_task(self._fetch_loop())
        logger.info("Scraper worker started")
        store.log_connection_event("reconnecting", "Khởi chạy hệ thống quét bot...")
        asyncio.create_task(self._bootstrap_history())

    async def _bootstrap_history(self):
        try:
            imported = await self.fetch_latest_info()
            if imported > 0:
                logger.info(f"[{config.LOTTERY_CODE}] Bootstrap: da nap {imported} ky quay tu lich su API.")
        except Exception as e:
            logger.warning(f"Bootstrap fetch error: {e}")

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
        store.log_connection_event("disconnected", "Dừng hệ thống quét bot...")

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
            max_added_issue = None
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
                        if not max_added_issue or issue > max_added_issue:
                            max_added_issue = issue
            
            if max_added_issue:
                try:
                    from src.api.routers.core import get_next_issue_code
                    next_issue = get_next_issue_code(max_added_issue)
                    if next_issue:
                        asyncio.create_task(asyncio.to_thread(store.generate_and_save_prediction, next_issue))
                except Exception as ex:
                    logger.error(f"Error triggering auto prediction in trigger_fetch: {ex}")

            logger.info(f"Fetch completed: imported {imported_count} new records")
            return imported_count
        except Exception as e:
            logger.error(f"Error during automated fetch: {str(e)}")
            return 0

    def _get_api_auth(self):
        from urllib.parse import urlparse, parse_qs
        domain = config.TARGET_DOMAIN
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
        return domain, token

    async def fetch_user_balance(self) -> float:
        domain, token = self._get_api_auth()
        if not token:
            return 0.0

        url = f"https://{domain}/server/user/getBalance?refresh=1"
        origin_url = f"https://{domain}"

        stored_http = store.get_http_headers()
        cf_auth_token = stored_http.get("cf_auth_token") or f"Bearer.{token}"
        cookie = stored_http.get("cookie")

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
            "Origin": origin_url,
            "Referer": f"{origin_url}/",
            "token": token,
            "Authorization": f"Bearer {token}",
            "cf-auth-token": cf_auth_token,
            "x-device": "pc",
            "x-lang": "vi"
        }
        if cookie:
            headers["cookie"] = cookie

        try:
            response = await asyncio.to_thread(
                requests.get,
                url,
                headers=headers,
                timeout=10
            )
            if response.status_code == 200:
                payload = response.json()
                if isinstance(payload, dict):
                    if payload.get("code") == 1:
                        data = payload.get("data")
                        if isinstance(data, dict):
                            val = data.get("total_money") or data.get("total_asset") or data.get("money") or data.get("balance") or 0.0
                            if str(val).strip() == "":
                                val = 0.0
                            balance = float(val)
                            store.update_real_balance(balance)
                            logger.info(f"[{config.LOTTERY_CODE}] Successfully fetched real balance: {balance} VND")
                            return balance
                        elif data is not None and str(data).strip() != "":
                            balance = float(data)
                            store.update_real_balance(balance)
                            logger.info(f"[{config.LOTTERY_CODE}] Successfully fetched real balance: {balance} VND")
                            return balance
                    elif payload.get("code") in (1004, 1005) or "hết hạn" in str(payload.get("msg", "")).lower():
                        logger.warning(f"[{config.LOTTERY_CODE}] Session expired (code {payload.get('code')}). Sending reload command.")
                        store.set_script_command("reload")
                        return 0.0
            logger.warning(f"Failed to fetch balance, status code: {response.status_code}, response: {response.text[:200]}")
        except Exception as e:
            logger.error(f"Error fetching user balance: {e}")
        return 0.0

    async def _fetch_loop(self):
        while self.is_running:
            if self.fetch_url:
                await self.trigger_fetch()
            await self.fetch_user_balance()
            await asyncio.sleep(self.fetch_interval)

    async def _ping_loop(self, ws):
        try:
            await asyncio.sleep(15)
            while self.is_running and self.connection_status == "connected":
                logger.info("Sending heartbeat ping '{\"type\":\"ping\"}' to WebSocket")
                try:
                    await ws.send(json.dumps({"type": "ping"}))
                except websockets.ConnectionClosed as e:
                    logger.warning(f"Ping failed: connection closed ({e})")
                    break
                except Exception as e:
                    logger.warning(f"Ping failed: {e}")
                    break
                await asyncio.sleep(15)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.warning(f"Error in ping loop: {e}")

    async def _monitor_loop(self, ws):
        try:
            while self.is_running and self.connection_status == "connected":
                if time.time() - self.last_received_time > 120:
                    logger.warning("No WebSocket messages received for 120 seconds. Resetting monitor but keeping connection.")
                    store.log_connection_event("disconnected", "Không nhận được gói tin nào từ WebSocket trong 120 giây, giữ kết nối và chờ...")
                    self.last_received_time = time.time()
                await asyncio.sleep(5)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.warning(f"Error in monitor loop: {e}")

    async def _loop(self):
        retry_delay = 2.0
        max_delay = 60.0
        conn_start_time = 0
        while self.is_running:
            self.connection_status = "connecting"
            try:
                logger.info(f"Connecting to target WebSocket: {self.ws_url}")
                origin = f"https://{config.TARGET_DOMAIN}"
                try:
                    from urllib.parse import urlparse
                    parsed = urlparse(self.ws_url)
                    if parsed.netloc:
                        origin = f"https://{parsed.netloc}"
                except:
                    pass

                import inspect
                sig = inspect.signature(websockets.connect)

                connect_kwargs = {
                    "ping_interval": 20,
                    "ping_timeout": 10
                }

                headers_dict = {
                    "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
                    "Cache-Control": "no-cache",
                    "Pragma": "no-cache"
                }
                user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

                if "additional_headers" in sig.parameters:
                    connect_kwargs["additional_headers"] = headers_dict
                    if "user_agent_header" in sig.parameters:
                        connect_kwargs["user_agent_header"] = user_agent
                    else:
                        headers_dict["User-Agent"] = user_agent

                    if "origin" in sig.parameters:
                        connect_kwargs["origin"] = origin
                    else:
                        headers_dict["Origin"] = origin
                else:
                    fallback_headers = headers_dict.copy()
                    fallback_headers["User-Agent"] = user_agent
                    fallback_headers["Origin"] = origin
                    connect_kwargs["extra_headers"] = fallback_headers

                async with websockets.connect(self.ws_url, **connect_kwargs) as ws:
                    self._reconnect_attempts = 0
                    logger.info("WebSocket connected successfully")
                    clean_url = self.ws_url.split('/ws/')[0] if '/ws/' in self.ws_url else self.ws_url
                    store.log_connection_event("connected", f"Kết nối thành công đến WebSocket: {clean_url}")
                    self.connection_status = "connected"
                    self.last_received_time = time.time()
                    conn_start_time = time.time()

                    ping_task = asyncio.create_task(self._ping_loop(ws))
                    monitor_task = asyncio.create_task(self._monitor_loop(ws))

                    try:
                        async for message in ws:
                            if not self.is_running:
                                break
                            self.last_received_time = time.time()
                            if message != "h":
                                await self._process_message(message)
                    finally:
                        self.connection_status = "disconnected"
                        ping_task.cancel()
                        monitor_task.cancel()
                        try:
                            await asyncio.gather(ping_task, monitor_task, return_exceptions=True)
                        except Exception:
                            pass
            except Exception as e:
                self.connection_status = "disconnected"
                err_msg = str(e) or "Không có phản hồi từ máy chủ."
                logger.error(f"WebSocket connection error or disconnected: {err_msg}")
                store.log_connection_event("disconnected", f"Mất kết nối hoặc lỗi: {err_msg}")

                self._reconnect_attempts += 1
                if self._reconnect_attempts > self._max_reconnect_attempts:
                    logger.warning(f"Reconnect failed {self._reconnect_attempts} times. Sending reload command to browser.")
                    store.set_script_command("reload")
                    self._reconnect_attempts = 0
                else:
                    logger.info(f"Reconnect attempt {self._reconnect_attempts} failed, will retry.")

                await self._run_fallback_simulation()

            is_stable = conn_start_time > 0 and (time.time() - conn_start_time > 15)
            if is_stable:
                retry_delay = 2.0
            else:
                retry_delay = min(retry_delay * 2, max_delay)

            logger.info(f"Waiting {retry_delay}s before reconnecting...")
            store.log_connection_event("reconnecting", f"Đang thử kết nối lại sau {retry_delay} giây...")
            await asyncio.sleep(retry_delay)

    async def _process_message(self, message: str):
        try:
            data = json.loads(message)
            msg_type = data.get("type")

            if msg_type == "lottery_result":
                lottery = data.get("data", {}).get("lottery", {})
                if lottery.get("id") == config.LOTTERY_ID or lottery.get("code") == config.LOTTERY_CODE:
                    last_issue = str(lottery.get("last_issue") or "")
                    issue = str(lottery.get("issue") or "")
                    target_issue = last_issue if last_issue else issue
                    digits = lottery.get("open_numbers_formatted") or []
                    numbers = [int(x) for x in digits if str(x).isdigit()]
                    if len(numbers) >= 5:
                        numbers = numbers[-5:]
                    if target_issue and len(numbers) == 5:
                        added = store.add_record(target_issue, numbers)
                        if added:
                            logger.info(f"[{config.LOTTERY_CODE}] Received new real issue {target_issue}: {numbers}")
                            asyncio.create_task(self.fetch_user_balance())
                            try:
                                from src.api.routers.core import get_next_issue_code
                                next_issue = get_next_issue_code(target_issue)
                                if next_issue:
                                    asyncio.create_task(asyncio.to_thread(store.generate_and_save_prediction, next_issue))
                            except Exception as ex:
                                logger.error(f"Error triggering auto prediction in websocket: {ex}")
            else:
                data_field = data.get("data") or {}
                if isinstance(data_field, dict):
                    for key, val in data_field.items():
                        if isinstance(val, list):
                            for item in val:
                                if isinstance(item, dict):
                                    if item.get("id") == config.LOTTERY_ID or item.get("code") == config.LOTTERY_CODE:
                                        last_issue = str(item.get("last_issue") or "")
                                        issue = str(item.get("issue") or "")
                                        target_issue = last_issue if last_issue else issue
                                        digits = item.get("open_numbers_formatted") or []
                                        numbers = [int(x) for x in digits if str(x).isdigit()]
                                        if len(numbers) >= 5:
                                            numbers = numbers[-5:]
                                        if target_issue and len(numbers) == 5:
                                            added = store.add_record(target_issue, numbers)
                                            if added:
                                                logger.info(f"[{config.LOTTERY_CODE}] Received new real issue {target_issue}: {numbers}")
                                                asyncio.create_task(self.fetch_user_balance())
                                                try:
                                                    from src.api.routers.core import get_next_issue_code
                                                    next_issue = get_next_issue_code(target_issue)
                                                    if next_issue:
                                                        asyncio.create_task(asyncio.to_thread(store.generate_and_save_prediction, next_issue))
                                                except Exception as ex:
                                                    logger.error(f"Error triggering auto prediction in websocket: {ex}")
        except Exception as e:
            logger.error(f"Failed to process websocket message: {str(e)}. Raw: {message[:200]}")

    async def fetch_latest_info(self) -> int:
        from urllib.parse import urlparse, parse_qs

        domain = config.TARGET_DOMAIN
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

        url_draw = f"https://{domain}/server/lottery/drawResult?lottery_id={config.LOTTERY_ID}&page=1&limit=100"
        url_info = f"https://{domain}/server/lottery/getCurrentLotteryInfo?lottery_id={config.LOTTERY_ID}"
        if token:
            url_draw += f"&token={token}"
        urls = [url_info, url_draw]

        origin_url = f"https://{domain}" if domain else f"https://{config.TARGET_DOMAIN}"
        
        stored_http = store.get_http_headers()
        cf_auth_token = stored_http.get("cf_auth_token") or (f"Bearer.{token}" if token else "")
        cookie = stored_http.get("cookie")

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
            "Origin": origin_url,
            "Referer": f"{origin_url}/",
            "Sec-Ch-Ua": '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"Windows"',
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin"
        }
        if token:
            headers["token"] = token
            headers["Authorization"] = f"Bearer {token}"
        if cf_auth_token:
            headers["cf-auth-token"] = cf_auth_token
        if cookie:
            headers["cookie"] = cookie

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
                if len(numbers) >= 5:
                    numbers = numbers[-5:]

                if len(numbers) == 5:
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
                req_headers = headers.copy()
                if "drawResult" not in url:
                    req_headers.pop("token", None)
                    req_headers.pop("Authorization", None)

                response = await asyncio.to_thread(
                    requests.get,
                    url,
                    headers=req_headers,
                    timeout=10
                )
                if response.status_code != 200:
                    logger.warning(f"Fetch failed for {url} with status code: {response.status_code}")
                    continue

                payload = response.json()
                extracted = extract_records(payload)
                for issue, numbers in extracted:
                    added = store.add_record(issue, numbers)
                    if added:
                        logger.info(f"[{config.LOTTERY_CODE}] Auto-imported draw result: {issue} -> {numbers}")
                        imported_count += 1

                try:
                    statistics_info = {}
                    if isinstance(payload, dict):
                        data_obj = payload.get("data")
                        if isinstance(data_obj, dict):
                            statistics_info = data_obj.get("statisticsInfo") or {}
                        else:
                            statistics_info = payload.get("statisticsInfo") or {}

                    if isinstance(statistics_info, dict) and statistics_info:
                        total_sum = statistics_info.get("total_sum")
                        if isinstance(total_sum, dict):
                            data_list = total_sum.get("statisticDataList")
                            if isinstance(data_list, dict):
                                big_small_list = data_list.get("bigSmall", [])
                                odd_even_list = data_list.get("oddEven", [])
                                logger.info(f"[{config.LOTTERY_CODE}] statisticsInfo found: {len(big_small_list)} bigSmall, {len(odd_even_list)} oddEven entries")

                                issue_data = {}
                                for item in big_small_list:
                                    if isinstance(item, dict):
                                        iss = item.get("issue")
                                        res = item.get("result")
                                        if iss and res:
                                            issue_data[iss] = {"is_tai": res == "big"}
                                for item in odd_even_list:
                                    if isinstance(item, dict):
                                        iss = item.get("issue")
                                        res = item.get("result")
                                        if iss and res:
                                            if iss in issue_data:
                                                issue_data[iss]["is_le"] = res == "odd"
                                            else:
                                                issue_data[iss] = {"is_le": res == "odd", "is_tai": False}

                                stats_imported = 0
                                for iss, info in issue_data.items():
                                    if "is_tai" in info and "is_le" in info:
                                        added = store.add_calculated_record(iss, info["is_tai"], info["is_le"])
                                        if added:
                                            stats_imported += 1
                                            imported_count += 1
                                if stats_imported > 0:
                                    logger.info(f"[{config.LOTTERY_CODE}] Bootstrap from statisticsInfo: imported {stats_imported} calculated records")
                            else:
                                logger.warning(f"statisticDataList is not dict: {type(data_list)}")
                        else:
                            logger.warning(f"total_sum is not dict: {type(total_sum)}")
                except Exception as ex:
                    logger.error(f"Error parsing statisticsInfo: {ex}")
            except Exception as e:
                logger.error(f"Error fetching from {url}: {e}")

        return imported_count

    async def _run_fallback_simulation(self):
        logger.info("Simulation mode is disabled. No simulated data will be generated.")

scraper = WebSocketScraper()
