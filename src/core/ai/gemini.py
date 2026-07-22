import pandas as pd
import json
import time
import logging
import requests
from src.config import config

logger = logging.getLogger(__name__)

class GeminiClient:
    """Xử lý tất cả logic gọi Gemini API: cache, rate-limit, retry."""
    _gemini_cache = {}
    _last_call_time = 0
    _consecutive_failures = 0
    _cache_ttl = 300
    _rate_limit_until = 0.0

    @staticmethod
    def call_with_retry(df: pd.DataFrame, stats_context: dict, max_retries: int = 3) -> dict:
        current_time = time.time()
        if current_time < GeminiClient._rate_limit_until:
            wait_rem = int(GeminiClient._rate_limit_until - current_time)
            logger.warning(f"[Gemini] Rate limit active. Fast-falling back to local AI (Heuristics). Wait {wait_rem}s more.")
            raise ValueError(f"Gemini API is temporarily blocked due to Rate Limit (cooling down, {wait_rem}s remaining)")

        api_key = getattr(config, "GEMINI_API_KEY", "")
        if not api_key:
            logger.error("GEMINI_API_KEY is not set in config.")
            raise ValueError("GEMINI_API_KEY is not set")

        model = getattr(config, "GEMINI_MODEL", "gemini-2.5-flash")
        version = getattr(config, "GEMINI_API_VERSION", "v1beta")
        url = f"https://generativelanguage.googleapis.com/{version}/models/{model}:generateContent?key={api_key}"

        history_subset = df.head(100)
        draws_list = []
        for _, row in history_subset.iterrows():
            draws_list.append({
                "issue": str(row.get("issue")),
                "numbers": list(row.get("numbers") or []),
                "total": int(row.get("total")),
                "parity": "Le" if row.get("is_le") else "Chan",
                "size": "Tai" if row.get("is_tai") else "Xiu"
            })
        draws_list.reverse()

        markov_data = stats_context.get("markov", {})
        pred_le = markov_data.get("pred_le", 0.5)
        pred_tai = markov_data.get("pred_tai", 0.5)

        prompt = (
            "Ban la chuyen gia phan tich chuoi so va du doan xac suat xo so chuyen nghiep.\n"
            "Nhiem vu cua ban la phan tich du lieu lich su cac ky quay so gan nhat va dua ra khuyen nghi thong minh "
            "(Du doan ky quay tiep theo) cho 2 thi truong: Chan/Le (Parity) va Tai/Xiu (Size).\n\n"
            f"Du lieu lich su 100 ky gan nhat (tu cu den moi nhat):\n{json.dumps(draws_list, ensure_ascii=False, indent=2)}\n\n"
            "Bao cao thong ke nang cao tu Heuristics cung cap:\n"
            f"1. Trang thai bet hien tai:\n"
            f"  - Chan/Le: Dang bet {'Le' if stats_context.get('active_le_state') else 'Chan'} tiep tuc {stats_context.get('active_le_len')} ky (Max bet lich su: {stats_context.get('max_le_streak')} ky).\n"
            f"  - Tai/Xiu: Dang bet {'Tai' if stats_context.get('active_tai_state') else 'Xiu'} tiep tuc {stats_context.get('active_tai_len')} ky (Max bet lich su: {stats_context.get('max_tai_streak')} ky).\n"
            f"2. Chi so dao chieu Ping-Pong (AR vs Nguong):\n"
            f"  - Parity: AR hien tai {stats_context.get('ar_smooth_parity', 0.0)*100:.1f}% | Nguong chieu: {stats_context.get('ar_threshold_parity', 0.0)*100:.1f}%\n"
            f"  - Size: AR hien tai {stats_context.get('ar_smooth_size', 0.0)*100:.1f}% | Nguong chieu: {stats_context.get('ar_threshold_size', 0.0)*100:.1f}%\n"
            f"3. Xac suat truot (Sliding Window) & Nguong bao hoa:\n"
            f"  - Parity (Le): {stats_context.get('prob_le_sliding', 0.5)*100:.1f}% | (Chan): {stats_context.get('prob_chan_sliding', 0.5)*100:.1f}% (Nguong bao hoa Le/Chan: {stats_context.get('T_sat_le', 0.5)*100:.1f}% / {stats_context.get('T_sat_chan', 0.5)*100:.1f}%)\n"
            f"  - Size (Tai): {stats_context.get('prob_tai_sliding', 0.5)*100:.1f}% | (Xiu): {stats_context.get('prob_xiu_sliding', 0.5)*100:.1f}% (Nguong bao hoa Tai/Xiu: {stats_context.get('T_sat_tai', 0.5)*100:.1f}% / {stats_context.get('T_sat_xiu', 0.5)*100:.1f}%)\n"
            f"4. Nguong mua dong cua Heuristics (Phan tich Standard Deviation):\n"
            f"  - Parity: {stats_context.get('buy_threshold_parity', 0.5)*100:.1f}%\n"
            f"  - Size: {stats_context.get('buy_threshold_size', 0.5)*100:.1f}%\n"
            f"5. Xac suat du doan Markov ky quay ke tiep:\n"
            f"  - Parity (Le): {pred_le * 100:.1f}% | (Chan): {(1 - pred_le) * 100:.1f}%\n"
            f"  - Size (Tai): {pred_tai * 100:.1f}% | (Xiu): {(1 - pred_tai) * 100:.1f}%\n\n"
            "HAY DUA RA DU DOAN KY QUAY TIEP THEO (Issue tiep theo).\n"
            'Quy tac:\n'
            '1. Ban BAT BUOC phai du doan: "MUA LE" hoac "MUA CHAN" cho Parity. KHONG DUOC PHEP DU DOAN "BO QUA".\n'
            '2. Ban BAT BUOC phai du doan: "MUA TAI" hoac "MUA XIU" cho Size. KHONG DUOC PHEP DU DOAN "BO QUA".\n'
            '3. Khuyen nghi dua tren phan tich lech xac suat va tin hieu xu huong.\n'
            '4. Do tin cay (confidence) phai la so nguyen tu 0 den 100.\n'
            '5. Rationale: Giai thich bang tieng Viet ngan gon (toi da 2 dong).\n\n'
            'Ban BAT BUOC phai tra ve JSON theo schema:\n'
            '{\n'
            '  "parity": {"decision": "MUA LE | MUA CHAN", "confidence": 70, "rationale": "..."},\n'
            '  "size": {"decision": "MUA TAI | MUA XIU", "confidence": 70, "rationale": "..."}\n'
            '}'
        )
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"responseMimeType": "application/json"}
        }
        headers = {"Content-Type": "application/json"}

        for attempt in range(max_retries):
            t_start = time.time()
            try:
                logger.info(f"[Gemini] Attempt {attempt+1}/{max_retries}")
                response = requests.post(url, json=payload, headers=headers, timeout=10)
                latency = round(time.time() - t_start, 3)
                if response.status_code in (429, 403):
                    GeminiClient._rate_limit_until = time.time() + 300
                    logger.warning(f"[Gemini] Rate Limit / Quota Exceeded ({response.status_code}). Blocked for 5 minutes. Fallback to Local Heuristics.")
                    GeminiClient._save_ai_audit_log(
                        issue="unknown", prompt_payload=json.dumps(payload, ensure_ascii=False)[:2000],
                        response_raw=f"HTTP {response.status_code}", latency=latency, is_success=False
                    )
                    raise ValueError(f"Gemini API rate limited: {response.status_code}")
                response.raise_for_status()
                data = response.json()
                text = data["candidates"][0]["content"]["parts"][0]["text"]
                result = json.loads(text)
                GeminiClient._save_ai_audit_log(
                    issue="unknown", prompt_payload=json.dumps(payload, ensure_ascii=False)[:2000],
                    response_raw=text[:2000], latency=latency, is_success=True
                )
                return result
            except requests.exceptions.RequestException as e:
                latency = round(time.time() - t_start, 3)
                logger.warning(f"[Gemini] Request error: {e}")
                if hasattr(e, 'response') and e.response is not None:
                    if e.response.status_code in (429, 403):
                        GeminiClient._rate_limit_until = time.time() + 300
                        GeminiClient._save_ai_audit_log(
                            issue="unknown", prompt_payload=json.dumps(payload, ensure_ascii=False)[:2000],
                            response_raw=str(e), latency=latency, is_success=False
                        )
                        raise ValueError(f"Gemini API rate limited: {e.response.status_code}")
                if attempt < max_retries - 1:
                    time.sleep(1)
                continue
            except (KeyError, json.JSONDecodeError) as e:
                logger.error(f"[Gemini] Parse error: {e}")
                break
        raise Exception("Gemini API failed after retries")

    @staticmethod
    def _save_ai_audit_log(issue: str, prompt_payload: str, response_raw: str, latency: float, is_success: bool) -> None:
        """Ghi ket qua goi Gemini API vao bang ai_audit_logs trong CSDL."""
        try:
            from src.database.connection import get_db_session
            from src.database.models.prediction import AIAuditLog
            with get_db_session() as session:
                db_log = AIAuditLog(
                    lottery_code=config.LOTTERY_CODE,
                    issue=issue,
                    model_name=getattr(config, "GEMINI_MODEL", "gemini-2.5-flash"),
                    prompt_payload=prompt_payload,
                    response_raw=response_raw,
                    latency_seconds=latency,
                    is_success=is_success,
                )
                session.add(db_log)
                logger.info(f"[DB] Saved ai_audit_log: success={is_success} latency={latency}s")
        except Exception as ex:
            logger.warning(f"[DB] ai_audit_log persist warning: {ex}")
