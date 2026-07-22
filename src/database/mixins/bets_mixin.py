import json
import time
import logging
from typing import List, Dict, Any, Optional
from src.core.money import MoneyManager, get_effective_win_rate, ALL_STRATEGIES
from src.config import config

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
                strategy_str = "dkm_adaptive_pro"
                if strategy:
                    try:
                        strategy_str = strategy.decode('utf-8')
                    except AttributeError:
                        strategy_str = str(strategy)
                if strategy_str not in ALL_STRATEGIES:
                    strategy_str = "dkm_adaptive_pro"
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
                current_peak = float(self.redis_client.get(self.key_peak_demo_balance) or balance)
                if balance > current_peak:
                    self.redis_client.set(self.key_peak_demo_balance, balance)
                return True
            except Exception as e:
                logger.error(f"Redis error in update_demo_balance: {e}")
        with self._lock:
            self._demo_balance = balance
            if balance > self._peak_demo_balance:
                self._peak_demo_balance = balance
            self._save_local_store()
        self._sync_user_balance_to_db()
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

        # Delete triet de khoi CSDL PostgreSQL
        try:
            from src.database.connection import get_db_session
            from src.database.models import Bet, Prediction
            from src.database.models.system import MarketHealthLog
            with get_db_session() as session:
                session.query(Bet).filter_by(lottery_code=config.LOTTERY_CODE).delete()
                session.query(Prediction).filter_by(lottery_code=config.LOTTERY_CODE).delete()
                session.query(MarketHealthLog).filter_by(lottery_code=config.LOTTERY_CODE).delete()
                session.commit()
                logger.info("[DB] Cleared all bets, predictions, and market_health_logs from PostgreSQL")
        except Exception as ex:
            logger.error(f"[DB] Error clearing PostgreSQL records: {ex}")
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

    def get_demo_bets(self, limit: int = 100) -> List[Dict[str, Any]]:
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
            if not flat_bets:
                try:
                    from src.database.connection import get_db_session
                    from src.database.models import Bet
                    with get_db_session() as session:
                        rows = session.query(Bet).filter_by(
                            lottery_code=config.LOTTERY_CODE
                        ).order_by(Bet.id.desc()).limit(limit).all()
                        for r in rows:
                            flat_bets.append({
                                "id": r.id,
                                "issue": r.issue,
                                "market_type": r.market_type,
                                "bet_choice": r.bet_choice,
                                "amount": r.amount,
                                "win_amount": r.win_amount,
                                "status": r.status,
                                "time": r.created_at.strftime("%H:%M:%S %d/%m/%Y") if r.created_at else "-"
                            })
                        return flat_bets
                except Exception as ex:
                    logger.warning(f"[DB] get_demo_bets DB fallback warning: {ex}")
            flat_bets.sort(key=lambda x: x["issue"], reverse=True)
            return flat_bets[:limit]

    def get_demo_bets_paginated(self, page: int = 1, limit: int = 10) -> Dict[str, Any]:
        start = (page - 1) * limit
        end = start + limit
        all_bets = []
        if self.use_redis:
            try:
                issues = self.redis_client.lrange(self.key_demo_bets_list, 0, -1)
                if issues:
                    bets_json = self.redis_client.hmget(self.key_demo_bets, issues)
                    for x in bets_json:
                        if x:
                            all_bets.extend(json.loads(x))
            except Exception as e:
                logger.error(f"Redis error in get_demo_bets_paginated: {e}")
        else:
            with self._lock:
                for issue, bets in self._demo_bets.items():
                    all_bets.extend(bets)
        all_bets.sort(key=lambda x: x.get("timestamp", 0), reverse=True)
        total = len(all_bets)
        return {
            "bets": all_bets[start:end],
            "total": total
        }

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
    def place_demo_bet(self, issue: str, market_type: str, prediction: str, amount: float, is_combined: bool = False, confidence: float = 0.0, engine: str = "Heuristics"):
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

        # Reset neu da het han pause
        if pause_until is not None and time.time() >= pause_until:
            with self._lock:
                if self.use_redis:
                    self.redis_client.delete(self.key_parity_pause_until if market_type == "parity" else self.key_size_pause_until)
                else:
                    if market_type == "parity":
                        self._parity_pause_until = None
                    else:
                        self._size_pause_until = None
                    self._save_local_store()
            pause_until = None

        is_stable = self.is_market_stable()
        prediction_stats_recent = self.get_prediction_stats_recent(15)
        win_rate = get_effective_win_rate(
            prediction_stats_recent, market_type
        )

        if self.use_redis:
            try:
                val = self.redis_client.get(self.key_initial_phase_remaining)
                initial_remaining = int(val) if val is not None else 10
            except Exception:
                initial_remaining = self._initial_phase_remaining
        else:
            with self._lock:
                initial_remaining = self._initial_phase_remaining

        is_initial_phase = (initial_remaining > 0)

        # === CIRCUIT BREAKER: WR < 45% THÌ PAUSE 10 PHÚT ===
        if not is_stable:
            if pause_until is None:
                pause_ts = time.time() + 10 * 60
                with self._lock:
                    if self.use_redis:
                        self.redis_client.set(self.key_parity_pause_until if market_type == "parity" else self.key_size_pause_until, pause_ts)
                    else:
                        if market_type == "parity":
                            self._parity_pause_until = pause_ts
                        else:
                            self._size_pause_until = pause_ts
                        self._save_local_store()
                logger.warning(f"[CIRCUIT BREAKER] {market_type} Win Rate < 45%. Pausing for 10m.")
                return "paused"

        # === THÊM BỘ LỌC AN TOÀN CHO SIZE ===
        # Nếu là Size và win_rate < 50%, tự động bỏ qua tối đa 3 kỳ để bảo vệ vốn rồi thử lại
        if market_type == "size" and win_rate < 0.50:
            recent_preds = self.get_prediction_history(limit=3)
            consecutive_ignored = sum(1 for p in recent_preds if p.get("status_size") == "ignored")
            if consecutive_ignored < 3:
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
            initial_phase_remaining=initial_remaining,
            is_combined=is_combined,
            market_type=market_type,  
            confidence=confidence,
        )

        if final_amount == 0.0:
            logger.info(f"[place_demo_bet] Ky {issue} ({market_type}): bi tam dung hoac het gioi han. Bo qua.")
            return "paused"

        if is_initial_phase and final_amount > 0:
            if self.use_redis:
                try:
                    self.redis_client.decr(self.key_initial_phase_remaining)
                except Exception as e:
                    logger.error(f"Redis error decrementing initial_phase_remaining: {e}")
            with self._lock:
                self._initial_phase_remaining = max(0, self._initial_phase_remaining - 1)
                self._save_local_store()
            logger.info(f"[INITIAL PHASE] Remaining decreased, bet: {final_amount}")

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
            "balance_after": 0.0,
            "engine": engine
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
                    if self.redis_client.llen(self.key_demo_bets_list) > 100:
                        removed = self.redis_client.rpop(self.key_demo_bets_list)
                        if removed:
                            self.redis_client.hdel(self.key_demo_bets, removed)
                self._persist_bet_to_db(bet, balances["demo_bet_strategy"])
                return True
            except Exception as e:
                logger.error(f"Redis error in place_demo_bet: {e}")

        with self._lock:
            self._demo_balance = self._demo_balance - final_amount
            bet["balance_after"] = self._demo_balance
            if issue not in self._demo_bets:
                self._demo_bets[issue] = []
            self._demo_bets[issue].append(bet)
            if len(self._demo_bets) > 100:
                oldest_key = min(self._demo_bets.keys(), key=lambda k: self._demo_bets[k][0]["timestamp"] if self._demo_bets[k] else 0)
                self._demo_bets.pop(oldest_key, None)
            self._save_local_store()
        self._persist_bet_to_db(bet, balances["demo_bet_strategy"])
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
        if updated:
            self._resolve_bets_in_db(issue)
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
                self._persist_capital_collapse_to_db(collapse)
                return True
            except Exception as e:
                logger.error(f"Redis error in log_capital_collapse: {e}")
        with self._lock:
            self._capital_collapses.insert(0, collapse)
            self._capital_collapses = self._capital_collapses[:50]
            self._save_local_store()
        self._persist_capital_collapse_to_db(collapse)
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

    # ============================ DB PERSISTENCE HELPERS ============================

    def _persist_bet_to_db(self, bet: dict, strategy: str) -> None:
        """Ghi cuoc dat vao bang bets trong CSDL (Dual-Write)."""
        try:
            from src.database.connection import get_db_session
            from src.database.models.bet import Bet
            with get_db_session() as session:
                # Dung (lottery_code, issue, market_type) lam key chong trung
                existing = session.query(Bet).filter_by(
                    lottery_code=config.LOTTERY_CODE,
                    issue=bet["issue"],
                    market_type=bet["market_type"]
                ).first()
                if not existing:
                    db_bet = Bet(
                        user_id=1,
                        lottery_code=config.LOTTERY_CODE,
                        issue=bet["issue"],
                        is_demo=True,
                        market_type=bet["market_type"],
                        prediction=bet["prediction"],
                        amount=bet["amount"],
                        strategy=strategy,
                        status="pending",
                        win_amount=0.0,
                        balance_after=bet.get("balance_after", 0.0),
                    )
                    session.add(db_bet)
                    logger.info(f"[DB] Saved bet: {bet['issue']} {bet['market_type']}")
        except Exception as ex:
            logger.warning(f"[DB] bet persist warning ({bet.get('issue')}): {ex}")

    def _resolve_bets_in_db(self, issue: str) -> None:
        """Cap nhat trang thai thang/thua cho cac cuoc cua 1 ky vao CSDL."""
        try:
            from datetime import datetime
            from src.database.connection import get_db_session
            from src.database.models.bet import Bet
            all_bets_ram = self.get_demo_bets(limit=200)
            resolved_map = {
                (b["issue"], b["market_type"]): b
                for b in all_bets_ram
                if b.get("issue") == issue and b.get("status") in ("win", "lose")
            }
            if not resolved_map:
                return
            with get_db_session() as session:
                db_bets = session.query(Bet).filter(
                    Bet.lottery_code == config.LOTTERY_CODE,
                    Bet.issue == issue,
                    Bet.status == "pending"
                ).all()
                for db_bet in db_bets:
                    key = (issue, db_bet.market_type)
                    ram_bet = resolved_map.get(key)
                    if ram_bet:
                        db_bet.status = ram_bet["status"]
                        db_bet.win_amount = ram_bet.get("win_amount", 0.0)
                        db_bet.balance_after = ram_bet.get("balance_after", 0.0)
                        db_bet.resolved_at = datetime.utcnow()
                        logger.info(f"[DB] Resolved bet: {issue} {db_bet.market_type} -> {db_bet.status}")
        except Exception as ex:
            logger.warning(f"[DB] bet resolve warning ({issue}): {ex}")

    def _sync_user_balance_to_db(self) -> None:
        """Dong bo so du demo vao bang user_balances trong CSDL."""
        try:
            from src.database.connection import get_db_session
            from src.database.models.bet import UserBalance
            balances = self.get_balances()
            with get_db_session() as session:
                ub = session.query(UserBalance).filter_by(
                    user_id=1,
                    lottery_code=config.LOTTERY_CODE
                ).first()
                if ub:
                    ub.demo_balance = balances["demo_balance"]
                    ub.peak_demo_balance = balances["peak_demo_balance"]
                    ub.demo_bet_amount = balances["demo_bet_amount"]
                    ub.demo_bet_strategy = balances["demo_bet_strategy"]
                    logger.info(f"[DB] Synced user_balance: demo={balances['demo_balance']}")
                else:
                    ub = UserBalance(
                        user_id=1,
                        lottery_code=config.LOTTERY_CODE,
                        demo_balance=balances["demo_balance"],
                        peak_demo_balance=balances["peak_demo_balance"],
                        demo_bet_amount=balances["demo_bet_amount"],
                        demo_bet_strategy=balances["demo_bet_strategy"],
                    )
                    session.add(ub)
                    logger.info(f"[DB] Created user_balance record")
        except Exception as ex:
            logger.warning(f"[DB] user_balance sync warning: {ex}")

    def _persist_capital_collapse_to_db(self, collapse: dict) -> None:
        """Ghi su kien vo von vao bang capital_collapses trong CSDL."""
        try:
            from src.database.connection import get_db_session
            from src.database.models.bet import CapitalCollapse
            with get_db_session() as session:
                db_collapse = CapitalCollapse(
                    lottery_code=config.LOTTERY_CODE,
                    issue=collapse["issue"],
                    market_type=collapse["market_type"],
                    loss_streak=collapse["loss_streak"],
                    amount_required=collapse["amount_required"],
                    balance_current=collapse["balance_current"],
                    strategy=collapse["strategy"],
                )
                session.add(db_collapse)
                logger.info(f"[DB] Saved capital_collapse: {collapse['issue']} {collapse['market_type']}")
        except Exception as ex:
            logger.warning(f"[DB] capital_collapse persist warning: {ex}")
