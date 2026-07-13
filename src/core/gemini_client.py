import pandas as pd
import json
import time
import logging
import requests
from src.config import config

logger = logging.getLogger(__name__)


class GeminiClient:
    """Xu ly tat ca logic goi Gemini API: cache, rate-limit, retry."""
    _gemini_cache = {}
    _last_call_time = 0
    _consecutive_failures = 0
    _cache_ttl = 300

    @staticmethod
    def call_with_retry(df: pd.DataFrame, stats_context: dict, max_retries: int = 3) -> dict:
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

        pred_le = stats_context.get("markov", {}).get("pred_le", 0.5)
        pred_tai = stats_context.get("markov", {}).get("pred_tai", 0.5)

        prompt = (
            "Ban la chuyen gia phan tich chuoi so va du doan xac suat xo so chuyen nghiep.\n"
            "Nhiem vu cua ban la phan tich du lieu lich su cac ky quay so gan nhat va dua ra khuyen nghi thong minh "
            "(Du doan ky quay tiep theo) cho 2 thi truong: Chan/Le (Parity) va Tai/Xiu (Size).\n\n"
            f"Du lieu lich su 100 ky gan nhat (tu cu den moi nhat):\n{json.dumps(draws_list, ensure_ascii=False, indent=2)}\n\n"
            "Boi canh thong ke hien tai cua he thong:\n"
            f"- Chuoi bet hien tai:\n"
            f"  + Chan/Le: {json.dumps(stats_context.get('streaks', {}).get('le_streak', {}), ensure_ascii=False)}\n"
            f"  + Tai/Xiu: {json.dumps(stats_context.get('streaks', {}).get('tai_streak', {}), ensure_ascii=False)}\n"
            f"- Du doan xac suat Markov ky tiep theo:\n"
            f"  + Parity (Le): {pred_le * 100:.1f}% | (Chan): {(1 - pred_le) * 100:.1f}%\n"
            f"  + Size (Tai): {pred_tai * 100:.1f}% | (Xiu): {(1 - pred_tai) * 100:.1f}%\n\n"
            "HAY DUA RA DU DOAN KY QUAY TIEP THEO (Issue tiep theo).\n"
            'Quy tac:\n'
            '1. Ban co the du doan: "MUA LE", "MUA CHAN", hoac "BO QUA" cho Parity.\n'
            '2. Ban co the du doan: "MUA TAI", "MUA XIU", hoac "BO QUA" cho Size.\n'
            '3. Chi khuyen nghi MUA khi ban phat hien tin hieu xu huong lap lai phi tuyen tinh cuc ky ro rang.\n'
            '4. Do tin cay (confidence) phai la so nguyen tu 0 den 100. Neu quyet dinh la "BO QUA", confidence nen o muc 50%.\n'
            '5. Rationale: Giai thich bang tieng Viet ngan gon (toi da 2 dong).\n\n'
            'Ban BAT BUOC phai tra ve JSON theo schema:\n'
            '{\n'
            '  "parity": {"decision": "MUA LE | MUA CHAN | BO QUA", "confidence": 50, "rationale": "..."},\n'
            '  "size": {"decision": "MUA TAI | MUA XIU | BO QUA", "confidence": 50, "rationale": "..."}\n'
            '}'
        )
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"responseMimeType": "application/json"}
        }
        headers = {"Content-Type": "application/json"}

        base_delay = 2
        for attempt in range(max_retries):
            try:
                logger.info(f"[Gemini] Attempt {attempt+1}/{max_retries}")
                response = requests.post(url, json=payload, headers=headers, timeout=10)
                if response.status_code == 429:
                    delay = base_delay * (2 ** attempt)
                    logger.warning(f"[Gemini] Rate limit (429). Retry in {delay}s")
                    time.sleep(delay)
                    continue
                response.raise_for_status()
                data = response.json()
                text = data["candidates"][0]["content"]["parts"][0]["text"]
                return json.loads(text)
            except requests.exceptions.RequestException as e:
                logger.warning(f"[Gemini] Request error: {e}")
                if attempt < max_retries - 1:
                    time.sleep(1)
                continue
            except (KeyError, json.JSONDecodeError) as e:
                logger.error(f"[Gemini] Parse error: {e}")
                break
        raise Exception("Gemini API failed after retries")
