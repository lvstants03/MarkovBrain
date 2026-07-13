import json
import time
import logging
import os
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

class PredictionsMixin:
    def add_prediction(self, issue: str, prediction_data: dict) -> bool:
        if not issue:
            return False

        engine_used = prediction_data.get("engine_used", {})
        engine_used_parity = engine_used.get("parity", "Heuristics")
        engine_used_size = engine_used.get("size", "Heuristics")

        record = {
            "issue": issue,
            "predicted_parity": prediction_data.get("predicted_parity", "Không có"),
            "predicted_size": prediction_data.get("predicted_size", "Không có"),
            "parity_confidence": prediction_data.get("parity_confidence"),
            "size_confidence": prediction_data.get("size_confidence"),
            "actual_parity": None,
            "actual_size": None,
            "status_parity": "pending",
            "status_size": "pending",
            "timestamp": time.time(),
            "time": time.strftime("%H:%M:%S %d/%m/%Y"),
            "engine": prediction_data.get("engine", "Heuristics (3-Layer)"),
            "parity_rationale": prediction_data.get("parity_rationale", ""),
            "size_rationale": prediction_data.get("size_rationale", ""),
            "total_records_at_prediction": prediction_data.get("total_records", 0),
            "engine_used_parity": engine_used_parity,
            "engine_used_size": engine_used_size,
        }

        added = False
        if self.use_redis:
            try:
                existing = self.redis_client.hget(self.key_predictions, issue)
                if not existing:
                    self.redis_client.hset(self.key_predictions, issue, json.dumps(record))
                    self.redis_client.lpush(self.key_prediction_issues, issue)
                    if self.redis_client.llen(self.key_prediction_issues) > 1000:
                        removed = self.redis_client.rpop(self.key_prediction_issues)
                        if removed:
                            self.redis_client.hdel(self.key_predictions, removed)
                    added = True
            except Exception as e:
                logger.error(f"Redis error in add_prediction: {e}")
        else:
            with self._lock:
                if not hasattr(self, "_predictions"):
                    self._predictions = {}
                if issue not in self._predictions:
                    self._predictions[issue] = record
                    if len(self._predictions) > 1000:
                        oldest_key = min(self._predictions.keys(), key=lambda k: self._predictions[k]["timestamp"])
                        self._predictions.pop(oldest_key, None)
                    added = True

        if added:
            bet_amt = self.get_balances()["demo_bet_amount"]
            pred_p = record.get("predicted_parity")
            if pred_p and pred_p != "Không có":
                dec_p = "MUA LẺ" if pred_p == "Le" else "MUA CHẴN"
                is_combined_p = (engine_used_parity == "Combined")
                self.place_demo_bet(
                    issue, "parity", dec_p, bet_amt, 
                    is_combined=is_combined_p, 
                    confidence=record.get("parity_confidence") or 0.0,
                    engine=engine_used_parity or "Heuristics"
                )
            pred_s = record.get("predicted_size")
            if pred_s and pred_s != "Không có":
                dec_s = "MUA TÀI" if pred_s == "Tai" else "MUA XỈU"
                is_combined_s = (engine_used_size == "Combined")
                self.place_demo_bet(
                    issue, "size", dec_s, bet_amt, 
                    is_combined=is_combined_s, 
                    confidence=record.get("size_confidence") or 0.0,
                    engine=engine_used_size or "Heuristics"
                )

        return added

    def resolve_prediction(self, issue: str, numbers: List[int]) -> bool:
        if not issue or not numbers or len(numbers) != 5:
            return False

        total = sum(numbers)
        actual_parity = "Le" if total % 2 != 0 else "Chan"
        actual_size = "Tai" if total > 22 else "Xiu"

        updated = False
        if self.use_redis:
            try:
                record_json = self.redis_client.hget(self.key_predictions, issue)
                if record_json:
                    record = json.loads(record_json)
                    if record.get("status_parity") == "pending" or record.get("status_size") == "pending":
                        record["actual_parity"] = actual_parity
                        record["actual_size"] = actual_size

                        pred_p = record.get("predicted_parity")
                        if pred_p and pred_p != "Không có":
                            record["status_parity"] = "win" if pred_p == actual_parity else "lose"
                        else:
                            record["status_parity"] = "ignored"

                        pred_s = record.get("predicted_size")
                        if pred_s and pred_s != "Không có":
                            record["status_size"] = "win" if pred_s == actual_size else "lose"
                        else:
                            record["status_size"] = "ignored"

                        self.redis_client.hset(self.key_predictions, issue, json.dumps(record))
                        updated = True
            except Exception as e:
                logger.error(f"Redis error in resolve_prediction: {e}")
        else:
            with self._lock:
                if hasattr(self, "_predictions") and issue in self._predictions:
                    record = self._predictions[issue]
                    if record.get("status_parity") == "pending" or record.get("status_size") == "pending":
                        record["actual_parity"] = actual_parity
                        record["actual_size"] = actual_size

                        pred_p = record.get("predicted_parity")
                        if pred_p and pred_p != "Không có":
                            record["status_parity"] = "win" if pred_p == actual_parity else "lose"
                        else:
                            record["status_parity"] = "ignored"

                        pred_s = record.get("predicted_size")
                        if pred_s and pred_s != "Không có":
                            record["status_size"] = "win" if pred_s == actual_size else "lose"
                        else:
                            record["status_size"] = "ignored"
                        updated = True

        if updated:
            self.resolve_demo_bets(issue, numbers)
            try:
                self.write_market_health_log()
            except Exception as e:
                logger.error(f"Error writing market health log: {e}")
        return updated

    def get_prediction(self, issue: str) -> Optional[Dict[str, Any]]:
        if self.use_redis:
            try:
                record_json = self.redis_client.hget(self.key_predictions, issue)
                if record_json:
                    return json.loads(record_json)
                return None
            except Exception as e:
                logger.error(f"Redis error in get_prediction: {e}")
                return None
        with self._lock:
            if hasattr(self, "_predictions") and issue in self._predictions:
                return self._predictions[issue]
            return None

    def get_prediction_history(self, limit: int = 100) -> List[Dict[str, Any]]:
        if self.use_redis:
            try:
                issues = self.redis_client.lrange(self.key_prediction_issues, 0, limit - 1)
                if not issues:
                    return []
                records_json = self.redis_client.hmget(self.key_predictions, issues)
                history = []
                for item in records_json:
                    if item:
                        history.append(json.loads(item))
                history.sort(key=lambda x: x["issue"], reverse=True)
                return history
            except Exception as e:
                logger.error(f"Redis error in get_prediction_history: {e}")

        with self._lock:
            if not hasattr(self, "_predictions"):
                return []
            preds = list(self._predictions.values())
            preds.sort(key=lambda x: x["issue"], reverse=True)
            return preds[:limit]

    def get_prediction_stats(self) -> dict:
        history = self.get_prediction_history(limit=1000)
        parity_wins = 0
        parity_losses = 0
        size_wins = 0
        size_losses = 0

        for item in history:
            sp = item.get("status_parity")
            ss = item.get("status_size")
            if sp == "win":
                parity_wins += 1
            elif sp == "lose":
                parity_losses += 1
            if ss == "win":
                size_wins += 1
            elif ss == "lose":
                size_losses += 1

        total_parity = parity_wins + parity_losses
        total_size = size_wins + size_losses
        return {
            "parity": {
                "wins": parity_wins,
                "losses": parity_losses,
                "total": total_parity,
                "win_rate": round(parity_wins / total_parity, 4) if total_parity > 0 else 0.0
            },
            "size": {
                "wins": size_wins,
                "losses": size_losses,
                "total": total_size,
                "win_rate": round(size_wins / total_size, 4) if total_size > 0 else 0.0
            },
            "overall_win_rate": round((parity_wins + size_wins) / (total_parity + total_size), 4) if (total_parity + total_size) > 0 else 0.0
        }

    def get_prediction_stats_recent(self, limit: int = 15) -> dict:
        history = self.get_prediction_history(limit=1000)
        parity_wins = 0
        parity_losses = 0
        parity_total = 0
        for item in history:
            sp = item.get("status_parity")
            if sp in ("win", "lose"):
                if sp == "win":
                    parity_wins += 1
                else:
                    parity_losses += 1
                parity_total += 1
                if parity_total >= limit:
                    break

        size_wins = 0
        size_losses = 0
        size_total = 0
        for item in history:
            ss = item.get("status_size")
            if ss in ("win", "lose"):
                if ss == "win":
                    size_wins += 1
                else:
                    size_losses += 1
                size_total += 1
                if size_total >= limit:
                    break

        return {
            "parity": {
                "wins": parity_wins,
                "losses": parity_losses,
                "total": parity_total,
                "win_rate": round(parity_wins / parity_total, 4) if parity_total > 0 else 0.0
            },
            "size": {
                "wins": size_wins,
                "losses": size_losses,
                "total": size_total,
                "win_rate": round(size_wins / size_total, 4) if size_total > 0 else 0.0
            }
        }

    def get_stats_by_engine(self, limit: int = 1000) -> Dict[str, Dict[str, Any]]:
        history = self.get_prediction_history(limit=limit)
        stats = {
            "Gemini": {"wins": 0, "losses": 0},
            "Heuristics": {"wins": 0, "losses": 0},
            "Combined": {"wins": 0, "losses": 0},
            "Conflict": {"wins": 0, "losses": 0},
        }
        for item in history:
            for market in ["parity", "size"]:
                engine_key = f"engine_used_{market}"
                status_key = f"status_{market}"
                engine = item.get(engine_key)
                status = item.get(status_key)
                if engine and status in ("win", "lose"):
                    stats[engine][status] += 1

        result = {}
        for engine, data in stats.items():
            total = data["wins"] + data["losses"]
            result[engine] = {
                "wins": data["wins"],
                "losses": data["losses"],
                "total": total,
                "win_rate": round(data["wins"] / total, 4) if total > 0 else 0.0
            }
        return result

    def is_market_stable(self) -> bool:
        history = self.get_prediction_history(limit=1000)
        resolved_items = []
        for item in history:
            sp = item.get("status_parity")
            ss = item.get("status_size")
            if sp in ("win", "lose") or ss in ("win", "lose"):
                resolved_items.append(item)
            if len(resolved_items) >= 30:
                break

        if len(resolved_items) < 30:
            return True

        total_bets = 0
        wins = 0
        for item in resolved_items:
            sp = item.get("status_parity")
            ss = item.get("status_size")
            if sp in ("win", "lose"):
                total_bets += 1
                if sp == "win":
                    wins += 1
            if ss in ("win", "lose"):
                total_bets += 1
                if ss == "win":
                    wins += 1

        win_rate_pct = (wins / total_bets * 100) if total_bets > 0 else 0.0
        return win_rate_pct >= 45.0

    def write_market_health_log(self) -> None:
        history = self.get_prediction_history(limit=1000)
        resolved_items = []
        for item in history:
            sp = item.get("status_parity")
            ss = item.get("status_size")
            if sp in ("win", "lose") or ss in ("win", "lose"):
                resolved_items.append(item)
            if len(resolved_items) >= 30:
                break

        log_file_path = os.path.join(os.getcwd(), "market_health_30.log")
        if len(resolved_items) < 30:
            header = (
                "Khối 30 kỳ gần nhất: -\n"
                "Hiệu suất thắng: -\n"
                "Phạm Vi Kỳ\tThời Gian\tSố Lượt Cược\tTỷ Lệ Thắng\tTrạng Thái\n"
            )
            content = header + "Chưa có đủ 30 kỳ để phân tích.\n"
            with open(log_file_path, "w", encoding="utf-8") as f:
                f.write(content)
            return

        end_issue = resolved_items[0]["issue"]
        start_issue = resolved_items[-1]["issue"]
        issue_range = f"{start_issue}-{end_issue}"

        total_bets = 0
        wins = 0
        for item in resolved_items:
            sp = item.get("status_parity")
            ss = item.get("status_size")
            if sp in ("win", "lose"):
                total_bets += 1
                if sp == "win":
                    wins += 1
            if ss in ("win", "lose"):
                total_bets += 1
                if ss == "win":
                    wins += 1

        win_rate_pct = (wins / total_bets * 100) if total_bets > 0 else 0.0
        status = "Ổn định" if win_rate_pct >= 53.0 else "Hỗn loạn"

        existing_rows = []
        if os.path.exists(log_file_path):
            try:
                with open(log_file_path, "r", encoding="utf-8") as f:
                    lines = f.readlines()
                for line in lines:
                    parts = line.strip().split("\t")
                    if len(parts) >= 5 and parts[0] != "Phạm Vi Kỳ":
                        existing_rows.append(line.strip())
            except Exception:
                pass

        current_time_str = time.strftime("%H:%M:%S %d/%m/%Y")
        new_row = f"{issue_range}\t{current_time_str}\t{total_bets}\t{win_rate_pct:.1f}%\t{status}"

        if not any(row.startswith(issue_range) for row in existing_rows):
            existing_rows.append(new_row)

        header = (
            f"Khối 30 kỳ gần nhất: {start_issue} - {end_issue}\n"
            f"Hiệu suất thắng: {wins}/{total_bets} ({win_rate_pct:.1f}%)\n"
            "Phạm Vi Kỳ\tThời Gian\tSố Lượt Cược\tTỷ Lệ Thắng\tTrạng Thái\n"
        )
        table_content = "\n".join(existing_rows[-100:]) + "\n"
        with open(log_file_path, "w", encoding="utf-8") as f:
            f.write(header + table_content)

    # ============================ SOCKET LOGS ============================

