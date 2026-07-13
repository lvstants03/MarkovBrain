import json
import time
import logging
from typing import List, Dict, Any, Optional
from src.core.money_management import MoneyManager

logger = logging.getLogger(__name__)

class BetsMixin:
    def get_balances(self) -> Dict[str, Any]:
        if self.use_redis:
            try:
                real = self.redis_client.get(self.key_real_balance)
                demo = self.redis_client.get(self.key_demo_balance)
                peak = self.redis_client.get(self.key_peak_demo_balance)
                bet_amt = self.redis_client.get(self.key_demo_bet_amount)
                strategy = self.redis_client.get(self.key_demo_bet_strategy)
                strategy_str = "fixed"
                if strategy:
                    try:
                        strategy_str = strategy.decode('utf-8')
                    except AttributeError:
                        strategy_str = str(strategy)
                return {
                    "real_balance": float(real) if real else 0.0,
                    "demo_balance": float(demo) if demo else 10000000.0,
                    "peak_demo_balance": float(peak) if peak else 10000000.0,
                    "demo_bet_amount": float(bet_amt) if bet_amt else 100000.0,
                    "demo_bet_strategy": strategy_str
                }
            except Exception as e:
                logger.error(f"Redis error in get_balances: {e}")

        with self._lock:
            return {
                "real_balance": self._real_balance,
                "demo_balance": self._demo_balance,
                "peak_demo_balance": self._peak_demo_balance,
                "demo_bet_amount": self._demo_bet_amount,
                "demo_bet_strategy": self._demo_bet_strategy
            }

    def update_demo_balance(self, balance: float):
        if self.use_redis:
            try:
                self.redis_client.set(self.key_demo_balance, balance)
                self.redis_client.set(self.key_peak_demo_balance, balance)
                return True
            except Exception as e:
                logger.error(f"Redis error in update_demo_balance: {e}")
        with self._lock:
            self._demo_balance = balance
            self._peak_demo_balance = balance
            self._save_local_store()
        return True

    def set_demo_bet_strategy(self, strategy: str):
        if self.use_redis:
            try:
                self.redis_client.set(self.key_demo_bet_strategy, strategy)
                return True
            except Exception as e:
                logger.error(f"Redis error in set_demo_bet_strategy: {e}")
        with self._lock:
            self._demo_bet_strategy = strategy
            self._save_local_store()
        return True

    def get_loss_streaks(self) -> Dict[str, int]:
        if self.use_redis:
            try:
                p_streak = self.redis_client.get(self.key_parity_loss_streak)
                s_streak = self.redis_client.get(self.key_size_loss_streak)
                return {
                    "parity": int(p_streak) if p_streak else 0,
                    "size": int(s_streak) if s_streak else 0
                }
            except Exception as e:
                logger.error(f"Redis error in get_loss_streaks: {e}")
        with self._lock:
            return {
                "parity": self._parity_loss_streak,
                "size": self._size_loss_streak
            }

    def update_loss_streak(self, market_type: str, is_win: bool):
        if self.use_redis:
            try:
                streak_key = self.key_parity_loss_streak if market_type == "parity" else self.key_size_loss_streak
                daily_key = self.key_parity_daily_loss_count if market_type == "parity" else self.key_size_daily_loss_count
                if is_win:
                    self.redis_client.set(streak_key, 0)
                else:
                    self.redis_client.incr(streak_key)
                    self.redis_client.incr(daily_key)
                return True
            except Exception as e:
                logger.error(f"Redis error in update_loss_streak: {e}")
        with self._lock:
            if market_type == "parity":
                if is_win:
                    self._parity_loss_streak = 0
                else:
                    self._parity_loss_streak += 1
                    self._parity_daily_loss_count += 1
            else:
                if is_win:
                    self._size_loss_streak = 0
                else:
                    self._size_loss_streak += 1
                    self._size_daily_loss_count += 1
            self._save_local_store()
        return True

    def update_real_balance(self, balance: float):
        if self.use_redis:
            try:
                self.redis_client.set(self.key_real_balance, balance)
                return True
            except Exception as e:
                logger.error(f"Redis error in update_real_balance: {e}")
        with self._lock:
            self._real_balance = balance
        return True

    def reset_demo_balance(self):
        if self.use_redis:
            try:
                self.redis_client.set(self.key_demo_balance, 10000000.0)
                self.redis_client.set(self.key_peak_demo_balance, 10000000.0)
                self.redis_client.delete(
                    self.key_demo_bets, self.key_demo_bets_list, self.key_capital_collapses,
                    self.key_parity_daily_loss_count, self.key_size_daily_loss_count,
                    self.key_parity_pause_until, self.key_size_pause_until
                )
                self.redis_client.set(self.key_parity_loss_streak, 0)
                self.redis_client.set(self.key_size_loss_streak, 0)
                self.redis_client.set(self.key_initial_phase_remaining, 10)
                return True
            except Exception as e:
                logger.error(f"Redis error in reset_demo_balance: {e}")
        with self._lock:
            self._demo_balance = 10000000.0
            self._peak_demo_balance = 10000000.0
            self._demo_bets.clear()
            self._capital_collapses.clear()
            self._parity_loss_streak = 0
            self._size_loss_streak = 0
            self._parity_daily_loss_count = 0
            self._size_daily_loss_count = 0
            self._parity_pause_until = None
            self._size_pause_until = None
            self._initial_phase_remaining = 10
            self._save_local_store()
        return True

    def clear_demo_bets(self):
        if self.use_redis:
            try:
                demo_bal = float(self.redis_client.get(self.key_demo_balance) or 10000000.0)
                self.redis_client.set(self.key_peak_demo_balance, demo_bal)
                self.redis_client.delete(
                    self.key_demo_bets, self.key_demo_bets_list, self.key_capital_collapses,
                    self.key_parity_daily_loss_count, self.key_size_daily_loss_count,
                    self.key_parity_pause_until, self.key_size_pause_until
                )
                self.redis_client.set(self.key_parity_loss_streak, 0)
                self.redis_client.set(self.key_size_loss_streak, 0)
                self.redis_client.set(self.key_initial_phase_remaining, 10)
                return True
            except Exception as e:
                logger.error(f"Redis error in clear_demo_bets: {e}")
        with self._lock:
            self._peak_demo_balance = self._demo_balance
            self._demo_bets.clear()
            self._capital_collapses.clear()
            self._parity_loss_streak = 0
            self._size_loss_streak = 0
            self._parity_daily_loss_count = 0
            self._size_daily_loss_count = 0
            self._parity_pause_until = None
            self._size_pause_until = None
            self._initial_phase_remaining = 10
            self._save_local_store()
        return True

    def set_demo_bet_amount(self, amount: float):
        if self.use_redis:
            try:
                self.redis_client.set(self.key_demo_bet_amount, amount)
                return True
            except Exception as e:
                logger.error(f"Redis error in set_demo_bet_amount: {e}")
        with self._lock:
            self._demo_bet_amount = amount
            self._save_local_store()
        return True

    def get_demo_bets(self, limit: int = 50) -> List[Dict[str, Any]]:
        if self.use_redis:
            try:
                issues = self.redis_client.lrange(self.key_demo_bets_list, 0, limit - 1)
                if not issues:
                    return []
                bets_json = self.redis_client.hmget(self.key_demo_bets, issues)
                all_bets = []
                for x in bets_json:
                    if x:
                        all_bets.extend(json.loads(x))
                all_bets.sort(key=lambda x: x["issue"], reverse=True)
                return all_bets[:limit]
            except Exception as e:
                logger.error(f"Redis error in get_demo_bets: {e}")
        with self._lock:
            flat_bets = []
            for issue, bets in self._demo_bets.items():
                flat_bets.extend(bets)
            flat_bets.sort(key=lambda x: x["issue"], reverse=True)
            return flat_bets[:limit]

    def get_bet_summary(self, since_ts: float = None, until_ts: float = None) -> Dict[str, Any]:
        """Tong hop nhat ky cuoc theo khoang thoi gian. since_ts, until_ts la Unix timestamp."""
        all_bets_raw = self.get_demo_bets(limit=10000)

        filtered = []
        for b in all_bets_raw:
            ts = b.get("timestamp", 0)
            if since_ts is not None and ts < since_ts:
                continue
            if until_ts is not None and ts > until_ts:
                continue
            filtered.append(b)

        total_placed = 0.0
        total_win_returned = 0.0
        total_lost = 0.0
        win_count = 0
        lose_count = 0
        pending_count = 0
        parity_win = parity_lose = 0
        size_win = size_lose = 0

        for b in filtered:
            status = b.get("status", "pending")
            amt = b.get("amount", 0.0)
            win_amt = b.get("win_amount", 0.0)
            mtype = b.get("market_type", "")

            if status == "win":
                total_placed += amt
                total_win_returned += win_amt
                win_count += 1
                if mtype == "parity":
                    parity_win += 1
                else:
                    size_win += 1
            elif status == "lose":
                total_placed += amt
                total_lost += amt
                lose_count += 1
                if mtype == "parity":
                    parity_lose += 1
                else:
                    size_lose += 1
            else:
                pending_count += 1

        net_profit = total_win_returned - total_placed
        total_resolved = win_count + lose_count
        win_rate = (win_count / total_resolved * 100) if total_resolved > 0 else 0.0

        return {
            "period": {
                "since_ts": since_ts,
                "until_ts": until_ts,
                "since_str": time.strftime("%H:%M:%S %d/%m/%Y", time.localtime(since_ts)) if since_ts else None,
                "until_str": time.strftime("%H:%M:%S %d/%m/%Y", time.localtime(until_ts)) if until_ts else None,
            },
            "summary": {
                "total_bets": total_resolved,
                "pending": pending_count,
                "win_count": win_count,
                "lose_count": lose_count,
                "win_rate_pct": round(win_rate, 2),
                "total_placed": round(total_placed, 2),
                "total_win_returned": round(total_win_returned, 2),
                "total_lost": round(total_lost, 2),
                "net_profit": round(net_profit, 2),
            },
            "by_market": {
                "parity": {"win": parity_win, "lose": parity_lose},
                "size": {"win": size_win, "lose": size_lose},
            },
            "bets": filtered[:200]
        }

    def get_daily_loss_info(self) -> Dict[str, Any]:
        now = time.time()
        if self.use_redis:
            try:
                p_daily = self.redis_client.get(self.key_parity_daily_loss_count)
                s_daily = self.redis_client.get(self.key_size_daily_loss_count)
                p_pause = self.redis_client.get(self.key_parity_pause_until)
                s_pause = self.redis_client.get(self.key_size_pause_until)

                p_daily_val = int(p_daily) if p_daily else 0
                s_daily_val = int(s_daily) if s_daily else 0
                p_pause_val = float(p_pause) if p_pause else None
                s_pause_val = float(s_pause) if s_pause else None

                p_expired = p_pause_val is not None and now >= p_pause_val
                s_expired = s_pause_val is not None and now >= s_pause_val

                if p_expired or s_expired:
                    current_demo = float(self.redis_client.get(self.key_demo_balance) or 10000000.0)
                    self.redis_client.set(self.key_peak_demo_balance, current_demo)

                if p_expired:
                    self.redis_client.set(self.key_parity_daily_loss_count, 0)
                    self.redis_client.delete(self.key_parity_pause_until)
                    p_daily_val = 0
                    p_pause_val = None

                if s_expired:
                    self.redis_client.set(self.key_size_daily_loss_count, 0)
                    self.redis_client.delete(self.key_size_pause_until)
                    s_daily_val = 0
                    s_pause_val = None

                return {
                    "parity_daily_loss_count": p_daily_val,
                    "size_daily_loss_count": s_daily_val,
                    "parity_pause_until": p_pause_val,
                    "size_pause_until": s_pause_val,
                }
            except Exception as e:
                logger.error(f"Redis error in get_daily_loss_info: {e}")

        with self._lock:
            p_expired = self._parity_pause_until is not None and now >= self._parity_pause_until
            s_expired = self._size_pause_until is not None and now >= self._size_pause_until

            if p_expired or s_expired:
                self._peak_demo_balance = self._demo_balance

            if p_expired:
                self._parity_daily_loss_count = 0
                self._parity_pause_until = None

            if s_expired:
                self._size_daily_loss_count = 0
                self._size_pause_until = None

            if p_expired or s_expired:
                self._save_local_store()

            return {
                "parity_daily_loss_count": self._parity_daily_loss_count,
                "size_daily_loss_count": self._size_daily_loss_count,
                "parity_pause_until": self._parity_pause_until,
                "size_pause_until": self._size_pause_until,
            }

    # ============================ SỬA HÀM place_demo_bet ============================
    def place_demo_bet(self, issue: str, market_type: str, prediction: str, amount: float, is_combined: bool = False):
        if not issue or not prediction or prediction in ("Khong co", "BO QUA", "Không có", "Bỏ QUA"):
            return False

        balances = self.get_balances()
        base_amount = balances["demo_bet_amount"]
        strategy = balances["demo_bet_strategy"]
        current_balance = balances["demo_balance"]

        loss_streaks = self.get_loss_streaks()
        streak = loss_streaks.get(market_type, 0)

        daily_info = self.get_daily_loss_info()
        daily_loss_count = daily_info.get(f"{market_type}_daily_loss_count", 0)
        pause_until = daily_info.get(f"{market_type}_pause_until", None)

        is_stable = self.is_market_stable()
        prediction_stats_recent = self.get_prediction_stats_recent(15)
        win_rate = __import__("src.core.money_management", fromlist=["get_effective_win_rate"]).get_effective_win_rate(
            prediction_stats_recent, market_type
        )

        is_initial_phase = (self._initial_phase_remaining > 0)

        # === THÊM BỘ LỌC AN TOÀN CHO SIZE ===
        # Nếu là Size và win_rate < 50%, tự động bỏ qua để bảo vệ vốn
        if market_type == "size" and win_rate < 0.50:
            logger.info(f"[place_demo_bet] Bo qua Size do win_rate 15 ky {win_rate*100:.1f}% < 50%.")
            return "paused"

        # Truyền is_combined và market_type vào calculate_bet
        final_amount = MoneyManager.calculate_bet(
            strategy=strategy,
            base_amount=base_amount,
            current_balance=current_balance,
            loss_streak=streak,
            daily_loss_count=daily_loss_count,
            pause_until=pause_until,
            win_rate=win_rate,
            is_stable=is_stable,
            is_initial_phase=is_initial_phase,
            initial_phase_remaining=self._initial_phase_remaining,
            is_combined=is_combined,
            market_type=market_type,  # <--- THÊM DÒNG NÀY
        )

        if final_amount == 0.0:
            logger.info(f"[place_demo_bet] Ky {issue} ({market_type}): bi tam dung hoac het gioi han. Bo qua.")
            return "paused"

        if is_initial_phase and final_amount > 0:
            self._initial_phase_remaining -= 1
            self._save_local_store()
            logger.info(f"[INITIAL PHASE] Remaining: {self._initial_phase_remaining}, bet: {final_amount}")

        current_balance = balances["demo_balance"]
        if final_amount > current_balance:
            logger.warning(f"[OVERDRAFT] Skipping {market_type} bet for {issue}: required {final_amount} > balance {current_balance}")
            self.log_capital_collapse(
                issue=issue,
                market_type=market_type,
                loss_streak=streak,
                amount_required=final_amount,
                balance_current=current_balance,
                base_amount=base_amount,
                strategy=strategy
            )
            return "insufficient_balance"

        bet = {
            "issue": issue,
            "timestamp": time.time(),
            "time": time.strftime("%H:%M:%S %d/%m/%Y"),
            "market_type": market_type,
            "prediction": prediction,
            "amount": final_amount,
            "status": "pending",
            "win_amount": 0.0,
            "balance_after": 0.0
        }

        if self.use_redis:
            try:
                current_demo = float(self.redis_client.get(self.key_demo_balance) or 10000000.0)
                if final_amount > current_demo:
                    logger.warning(f"[OVERDRAFT][Redis] Skipping bet for {issue}, insufficient balance.")
                    self.log_capital_collapse(
                        issue=issue,
                        market_type=market_type,
                        loss_streak=streak,
                        amount_required=final_amount,
                        balance_current=current_demo,
                        base_amount=base_amount,
                        strategy=strategy
                    )
                    return "insufficient_balance"
                new_demo = current_demo - final_amount
                self.redis_client.set(self.key_demo_balance, new_demo)

                existing_json = self.redis_client.hget(self.key_demo_bets, issue)
                existing_bets = json.loads(existing_json) if existing_json else []
                bet["balance_after"] = new_demo
                existing_bets.append(bet)

                self.redis_client.hset(self.key_demo_bets, issue, json.dumps(existing_bets))
                if not existing_json:
                    self.redis_client.lpush(self.key_demo_bets_list, issue)
                return True
            except Exception as e:
                logger.error(f"Redis error in place_demo_bet: {e}")

        with self._lock:
            self._demo_balance = self._demo_balance - final_amount
            bet["balance_after"] = self._demo_balance
            if issue not in self._demo_bets:
                self._demo_bets[issue] = []
            self._demo_bets[issue].append(bet)
            self._save_local_store()
        return True

    def resolve_demo_bets(self, issue: str, numbers: List[int]):
        if not issue or not numbers or len(numbers) != 5:
            return False

        total = sum(numbers)
        actual_parity = "MUA LẺ" if total % 2 != 0 else "MUA CHẴN"
        actual_size = "MUA TÀI" if total > 22 else "MUA XỈU"

        updated = False
        if self.use_redis:
            try:
                existing_json = self.redis_client.hget(self.key_demo_bets, issue)
                if existing_json:
                    existing_bets = json.loads(existing_json)
                    current_demo = float(self.redis_client.get(self.key_demo_balance) or 10000000.0)
                    peak_demo = float(self.redis_client.get(self.key_peak_demo_balance) or current_demo)

                    for bet in existing_bets:
                        if bet.get("status") == "pending":
                            actual = actual_parity if bet["market_type"] == "parity" else actual_size
                            is_win = (bet["prediction"] == actual)
                            if is_win:
                                bet["status"] = "win"
                                bet["win_amount"] = bet["amount"] * 1.95
                                current_demo += bet["win_amount"]
                            else:
                                bet["status"] = "lose"
                                bet["win_amount"] = 0.0

                            self.update_loss_streak(bet["market_type"], is_win)
                            bet["balance_after"] = current_demo
                            updated = True

                    if updated:
                        if current_demo > peak_demo:
                            peak_demo = current_demo
                            self.redis_client.set(self.key_peak_demo_balance, peak_demo)

                        if current_demo <= peak_demo * 0.75:
                            pause_ts = time.time() + 10 * 60
                            self.redis_client.set(self.key_parity_pause_until, pause_ts)
                            self.redis_client.set(self.key_size_pause_until, pause_ts)
                            logger.warning(f"[DRAWDOWN] Demo balance {current_demo} dropped by 25% or more from peak {peak_demo}. Pausing both markets for 10m.")

                        self.redis_client.set(self.key_demo_balance, current_demo)
                        self.redis_client.hset(self.key_demo_bets, issue, json.dumps(existing_bets))
                return updated
            except Exception as e:
                logger.error(f"Redis error in resolve_demo_bets: {e}")

        with self._lock:
            if issue in self._demo_bets:
                for bet in self._demo_bets[issue]:
                    if bet.get("status") == "pending":
                        actual = actual_parity if bet["market_type"] == "parity" else actual_size
                        is_win = (bet["prediction"] == actual)
                        if is_win:
                            bet["status"] = "win"
                            bet["win_amount"] = bet["amount"] * 1.95
                            self._demo_balance += bet["win_amount"]
                        else:
                            bet["status"] = "lose"
                            bet["win_amount"] = 0.0

                        self.update_loss_streak(bet["market_type"], is_win)
                        bet["balance_after"] = self._demo_balance
                        updated = True
                if updated:
                    if self._demo_balance > self._peak_demo_balance:
                        self._peak_demo_balance = self._demo_balance

                    if self._demo_balance <= self._peak_demo_balance * 0.75:
                        pause_ts = time.time() + 10 * 60
                        self._parity_pause_until = pause_ts
                        self._size_pause_until = pause_ts
                        logger.warning(f"[DRAWDOWN] Demo balance {self._demo_balance} dropped by 25% or more from peak {self._peak_demo_balance}. Pausing both markets for 10m.")

                    self._save_local_store()
        return updated

    # ============================ HTTP HEADERS ============================
    def update_http_headers(self, cf_auth_token: str, cookie: Optional[str] = None):
        if self.use_redis:
            try:
                self.redis_client.set(self.key_http_cf_auth_token, cf_auth_token)
                if cookie:
                    self.redis_client.set(self.key_http_cookie, cookie)
                return True
            except Exception as e:
                logger.error(f"Redis error in update_http_headers: {e}")
        with self._lock:
            self._http_cf_auth_token = cf_auth_token
            if cookie:
                self._http_cookie = cookie
        return True

    def get_http_headers(self) -> Dict[str, str]:
        if self.use_redis:
            try:
                cf_auth = self.redis_client.get(self.key_http_cf_auth_token)
                cookie = self.redis_client.get(self.key_http_cookie)
                return {
                    "cf_auth_token": cf_auth or "",
                    "cookie": cookie or ""
                }
            except Exception as e:
                logger.error(f"Redis error in get_http_headers: {e}")
        with self._lock:
            return {
                "cf_auth_token": self._http_cf_auth_token,
                "cookie": self._http_cookie
            }

    # ============================ SCRIPT COMMAND ============================
    def set_script_command(self, cmd: str):
        if self.use_redis:
            try:
                self.redis_client.set(f"lottery:{config.LOTTERY_CODE}:script_command", cmd)
                return True
            except Exception as e:
                logger.error(f"Redis error in set_script_command: {e}")
        with self._lock:
            self._script_command = cmd
        return True

    def get_script_command(self) -> str:
        if self.use_redis:
            try:
                key = f"lottery:{config.LOTTERY_CODE}:script_command"
                cmd = self.redis_client.get(key)
                if cmd:
                    cmd_str = cmd.decode('utf-8') if hasattr(cmd, 'decode') else str(cmd)
                    self.redis_client.set(key, "none")
                    return cmd_str
                return "none"
            except Exception as e:
                logger.error(f"Redis error in get_script_command: {e}")
        with self._lock:
            cmd = self._script_command
            self._script_command = "none"
            return cmd

    # ============================ CAPITAL COLLAPSES ============================
    def log_capital_collapse(self, issue: str, market_type: str, loss_streak: int, amount_required: float, balance_current: float, base_amount: float, strategy: str):
        collapse = {
            "timestamp": time.time(),
            "time": time.strftime("%H:%M:%S %d/%m/%Y"),
            "issue": issue,
            "market_type": market_type,
            "loss_streak": loss_streak,
            "amount_required": amount_required,
            "balance_current": balance_current,
            "base_amount": base_amount,
            "strategy": strategy
        }
        if self.use_redis:
            try:
                self.redis_client.lpush(self.key_capital_collapses, json.dumps(collapse))
                self.redis_client.ltrim(self.key_capital_collapses, 0, 49)
                return True
            except Exception as e:
                logger.error(f"Redis error in log_capital_collapse: {e}")
        with self._lock:
            self._capital_collapses.insert(0, collapse)
            self._capital_collapses = self._capital_collapses[:50]
            self._save_local_store()
        return True

    def get_capital_collapses(self, limit: int = 50) -> List[Dict[str, Any]]:
        if self.use_redis:
            try:
                collapses = self.redis_client.lrange(self.key_capital_collapses, 0, limit - 1)
                return [json.loads(c) for c in collapses if c]
            except Exception as e:
                logger.error(f"Redis error in get_capital_collapses: {e}")
                return []
        with self._lock:
            return self._capital_collapses[:limit]

    def clear_capital_collapses(self):
        if self.use_redis:
            try:
                self.redis_client.delete(self.key_capital_collapses)
                return True
            except Exception as e:
                logger.error(f"Redis error in clear_capital_collapses: {e}")
        with self._lock:
            self._capital_collapses.clear()
            self._save_local_store()
        return True

