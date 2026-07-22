import os
from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from src.database.store import store
from src.core.scraper import scraper
from src.config import config

router = APIRouter()

class ConfigUrlRequest(BaseModel):
    url: str = Field(..., description="Duong dan WebSocket moi, vi du: wss://domain/ws")

@router.post("/config-url")
async def config_url(payload: ConfigUrlRequest):
    if not payload.url.startswith("ws://") and not payload.url.startswith("wss://"):
        raise HTTPException(status_code=400, detail="Duong dan phai bat dau bang ws:// hoac wss://")
    await scraper.update_url(payload.url)
    return {
        "status": "success",
        "message": f"Da cap nhat duong dan va khoi dong lai ket noi WebSocket toi: {payload.url}"
    }


class ConfigTokenRequest(BaseModel):
    token: str = Field(..., description="Token dang nhap moi cua he thong game")
    cf_auth_token: Optional[str] = Field(None, description="cf-auth-token dung cho HTTP requests")
    cookie: Optional[str] = Field(None, description="Cookie cua trinh duyet dung cho HTTP requests")

def update_env_ws_url(ws_url: str):
    import os
    env_path = ".env"
    lines = []
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
            
    ws_found = False
    new_lines = []
    for line in lines:
        if line.strip().startswith("TARGET_WS_URL="):
            new_lines.append(f"TARGET_WS_URL=\"{ws_url}\"\n")
            ws_found = True
        else:
            new_lines.append(line)
            
    if not ws_found:
        new_lines.append(f"TARGET_WS_URL=\"{ws_url}\"\n")
        
    with open(env_path, "w", encoding="utf-8") as f:
        f.writelines(new_lines)

@router.post("/config-token")
async def config_token(payload: ConfigTokenRequest):
    token = payload.token
    if "token=" in token:
        try:
            token = token.split("token=")[1].split("&")[0]
        except Exception:
            pass
    token = token.strip()
    
    new_url = f"wss://{config.TARGET_DOMAIN}/ws/?token={token}&x-device=pc"
    await scraper.update_url(new_url)
    
    try:
        update_env_ws_url(new_url)
    except Exception as e:
        pass
        
    # Luu HTTP headers va cookie neu co de dung cho fetch_user_balance
    if payload.cf_auth_token:
        store.update_http_headers(payload.cf_auth_token, payload.cookie)
        
    return {
        "status": "success",
        "message": f"Da cap nhat token moi va tai khoi dong ket noi WebSocket. Token: {token}"
    }


class ConfigFetcherRequest(BaseModel):
    url: str = Field(..., description="Duong dan HTTP API lay ket qua, vi du: https://domain/api/drawResult")
    interval: int = Field(default=60, ge=10, le=3600, description="Tan suat lay tu dong tinh bang giay (10s - 3600s)")
    headers: Optional[dict] = Field(default=None, description="HTTP Headers duoi dang JSON object (cookie, x-device, etc.)")

@router.post("/config-fetcher")
async def config_fetcher(payload: ConfigFetcherRequest):
    if not payload.url.startswith("http://") and not payload.url.startswith("https://"):
        raise HTTPException(status_code=400, detail="Duong dan phai bat dau bang http:// hoac https://")
    await scraper.update_fetch_config(payload.url, payload.interval, payload.headers)
    return {
        "status": "success",
        "message": f"Da cap nhat HTTP fetcher: URL={payload.url}, interval={payload.interval} giay va headers."
    }

@router.post("/trigger-fetch")
async def trigger_fetch():
    if not scraper.fetch_url and not scraper.ws_url:
        raise HTTPException(status_code=400, detail="Chua cau hinh URL de fetch hoac WebSocket URL")
    imported = await scraper.trigger_fetch()
    return {
        "status": "success",
        "message": f"Da dong bo xong tu dong. Da them moi {imported} ky quay vao store."
    }

@router.post("/reconnect")
async def trigger_reconnect():
    # Chu dong dong va ket noi lai WebSocket hien tai
    if scraper.is_running:
        await scraper.stop()
        await scraper.start()
        return {
            "status": "success",
            "message": "Da chu dong tai khoi dong lai ket noi WebSocket"
        }
    else:
        raise HTTPException(status_code=400, detail="Scraper hien dang khong chay")


class ConfigLotteryRequest(BaseModel):
    lottery_id: int = Field(..., description="ID cua xo so, vi du: 43 (45s), 44 (75s), 45 (5p)")
    lottery_code: str = Field(..., description="Code cua xo so, vi du: pmb45s, pmb75s, pmb5p")

def update_env_file(lottery_id: int, lottery_code: str):
    import os
    env_path = ".env"
    lines = []
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
            
    id_found = False
    code_found = False
    new_lines = []
    for line in lines:
        if line.strip().startswith("LOTTERY_ID="):
            new_lines.append(f"LOTTERY_ID={lottery_id}\n")
            id_found = True
        elif line.strip().startswith("LOTTERY_CODE="):
            new_lines.append(f"LOTTERY_CODE=\"{lottery_code}\"\n")
            code_found = True
        else:
            new_lines.append(line)
            
    if not id_found:
        new_lines.append(f"LOTTERY_ID={lottery_id}\n")
    if not code_found:
        new_lines.append(f"LOTTERY_CODE=\"{lottery_code}\"\n")
        
    with open(env_path, "w", encoding="utf-8") as f:
        f.writelines(new_lines)

@router.post("/config-lottery")
async def config_lottery(payload: ConfigLotteryRequest):
    config.LOTTERY_ID = payload.lottery_id
    config.LOTTERY_CODE = payload.lottery_code
    
    try:
        update_env_file(payload.lottery_id, payload.lottery_code)
    except Exception as e:
        pass
        
    store.clear()
    if scraper.is_running:
        await scraper.stop()
        await scraper.start()
        
    return {
        "status": "success",
        "message": f"Da chuyen sang game: ID={config.LOTTERY_ID}, Code={config.LOTTERY_CODE}. Da xoa bo nho dem de nap lai lich su."
    }


@router.get("/socket/history")
async def get_socket_history(limit: int = Query(default=100, ge=1, le=500)):
    logs = store.get_connection_logs(limit=limit)
    return {
        "status": "success",
        "data": logs
    }


class SavePresetRequest(BaseModel):
    preset_name: str = Field(default="standard", description="Ten cua bo tham so")
    parity_config: dict = Field(..., description="Bo tham so cho Keo Parity")
    size_config: dict = Field(..., description="Bo tham so cho Keo Size")

@router.get("/config")
async def get_config():
    """Lay cau hinh hien tai cua Bot (uu tien DB, day du 32 tham so)"""
    p_cfg = store.get_analyzer_config("parity")
    s_cfg = store.get_analyzer_config("size")

    return {
        "status": "success",
        "parity_config": p_cfg,
        "size_config": s_cfg
    }

@router.post("/config/save-preset")
async def save_preset_config(payload: SavePresetRequest):
    # Luu vinh vien vao CSDL Database (analyzer_configs) — day du 32 truong
    _ALL_FIELDS = [
        "n_sliding_min", "n_sliding_max", "n_sliding_ratio",
        "ar_window_min", "ar_window_max", "ar_window_ratio",
        "ar_threshold_multiplier", "ar_threshold_min", "ar_threshold_max",
        "n_recent_min", "n_recent_max", "n_recent_ratio",
        "streak_confidence_threshold", "streak_min_samples",
        "streak_safety_trap_multiplier", "streak_safety_trap_min",
        "saturation_percentile", "saturation_limit_min", "saturation_limit_max",
        "cooling_off_loss_limit", "win_streak_pause_limit",
        "buy_threshold_multiplier", "buy_threshold_min", "buy_threshold_max",
        "min_probability_threshold", "ma50_window", "ma50_filter_active",
        "win_rate_filter_window", "win_rate_filter_min_total", "win_rate_filter_threshold",
        "reversal_threshold", "volatility_penalty",
    ]
    try:
        from src.database.connection import get_db_session
        from src.database.models import AnalyzerConfig
        preset = payload.preset_name if hasattr(payload, "preset_name") and payload.preset_name else "default"

        # Validate backend
        for market, cfg_dict in [("parity", payload.parity_config), ("size", payload.size_config)]:
            if not isinstance(cfg_dict, dict): continue
            p_min = cfg_dict.get("buy_threshold_min")
            p_max = cfg_dict.get("buy_threshold_max")
            if p_min is not None and (p_min < 0.40 or p_min > 0.99):
                raise HTTPException(status_code=400, detail=f"buy_threshold_min ({market}) phai tu 0.40 den 0.99!")
            if p_min is not None and p_max is not None and p_min > p_max:
                raise HTTPException(status_code=400, detail=f"buy_threshold_min ({market}) khong duoc lon hon buy_threshold_max!")
            rev = cfg_dict.get("reversal_threshold")
            if rev is not None and (rev < 0.50 or rev > 0.99):
                raise HTTPException(status_code=400, detail=f"reversal_threshold ({market}) phai tu 0.50 den 0.99!")

        saved_ids = {}
        with get_db_session() as session:

            for market, cfg_dict in [("parity", payload.parity_config), ("size", payload.size_config)]:
                cfg = session.query(AnalyzerConfig).filter_by(
                    lottery_code=config.LOTTERY_CODE,
                    market_type=market,
                    preset_name=preset
                ).first()

                if not cfg:
                    cfg = AnalyzerConfig(
                        lottery_code=config.LOTTERY_CODE,
                        market_type=market,
                        preset_name=preset
                    )
                    session.add(cfg)
                    session.flush()

                for field in _ALL_FIELDS:
                    if field in cfg_dict:
                        setattr(cfg, field, cfg_dict[field])

                cfg.is_active = True
                session.flush()
                saved_ids[f"{market}_id"] = cfg.id

            session.commit()
        # Xoa cache de engine doc lai tham so moi ngay lap tuc
        store.invalidate_analyzer_config_cache()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Loi luu preset: {e}")

    return {
        "status": "success",
        "message": f"Da cap nhat vinh vien bo tham so preset='{preset}' vao Database!",
        "preset_name": preset,
        "ids": saved_ids,
        "parity_config": payload.parity_config,
        "size_config": payload.size_config
    }



@router.get("/config/presets")
async def list_config_presets():
    """Lay danh sach tat ca cac presets da luu trong Database"""
    presets = []
    try:
        from src.database.connection import get_db_session
        from src.database.models import AnalyzerConfig
        with get_db_session() as session:
            rows = session.query(AnalyzerConfig.preset_name, AnalyzerConfig.is_active).filter_by(
                lottery_code=config.LOTTERY_CODE
            ).distinct().all()
            
            seen = set()
            for r in rows:
                p_name = r.preset_name or "standard"
                if p_name not in seen:
                    seen.add(p_name)
                    presets.append({
                        "name": p_name,
                        "is_active": r.is_active
                    })
    except Exception:
        pass

    if not presets:
        presets = [{"name": "standard", "is_active": True}]

    return {
        "status": "success",
        "presets": presets
    }


@router.get("/config/presets/{preset_name}")
async def get_config_preset_detail(preset_name: str):
    """Lay chi tiet tham so cua 1 preset theo ten tu Database"""
    try:
        from src.database.connection import get_db_session
        from src.database.models import AnalyzerConfig
        parity_cfg = {}
        size_cfg = {}
        with get_db_session() as session:
            rows = session.query(AnalyzerConfig).filter_by(
                lottery_code=config.LOTTERY_CODE,
                preset_name=preset_name
            ).all()

            for r in rows:
                c_dict = {
                    col.name: getattr(r, col.name)
                    for col in r.__table__.columns
                    if col.name not in ["id", "lottery_code", "market_type", "preset_name", "updated_at"]
                }
                if r.market_type == "parity":
                    parity_cfg = c_dict
                elif r.market_type == "size":
                    size_cfg = c_dict

        if not parity_cfg and not size_cfg:
            # Fallback default dict
            parity_cfg = store.get_analyzer_config("parity")
            size_cfg = store.get_analyzer_config("size")

        return {
            "status": "success",
            "preset_name": preset_name,
            "parity_config": parity_cfg,
            "size_config": size_cfg
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Loi lay chi tiet preset: {e}")


@router.post("/config/presets/{preset_name}/activate")

async def activate_config_preset(preset_name: str):
    """Kich hoat mot preset lam cau hinh chinh cho Bot"""
    try:
        from src.database.connection import get_db_session
        from src.database.models import AnalyzerConfig
        with get_db_session() as session:
            # Shift all to inactive
            session.query(AnalyzerConfig).filter_by(
                lottery_code=config.LOTTERY_CODE
            ).update({"is_active": False})

            # Set target active
            session.query(AnalyzerConfig).filter_by(
                lottery_code=config.LOTTERY_CODE,
                preset_name=preset_name
            ).update({"is_active": True})
            session.commit()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Loi active preset: {e}")

    store.invalidate_analyzer_config_cache()
    return {
        "status": "success",
        "message": f"Da kich hoat bo tham so '{preset_name}' lam mac dinh trong CSDL!"
    }


@router.delete("/config/presets/{preset_name}")
async def delete_config_preset(preset_name: str):
    """Xoa bo mot preset cu ra khoi CSDL Database"""
    if preset_name == "standard":
        raise HTTPException(status_code=400, detail="Khong the xoa bo tham so 'standard' mac dinh!")

    deleted = 0
    try:
        from src.database.connection import get_db_session
        from src.database.models import AnalyzerConfig
        with get_db_session() as session:
            deleted = session.query(AnalyzerConfig).filter_by(
                lottery_code=config.LOTTERY_CODE,
                preset_name=preset_name
            ).delete()
            session.commit()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Loi xoa preset: {e}")

    store.invalidate_analyzer_config_cache()
    return {
        "status": "success",
        "message": f"Da xoa thanh cong bo tham so '{preset_name}' khoi CSDL ({deleted} ban ghi)!"
    }


