from fastapi import APIRouter
from src.database.store import store

router = APIRouter()

@router.post("/script/reload")
async def trigger_script_reload():
    store.set_script_command("reload")
    return {
        "status": "success",
        "message": "Đã gửi lệnh yêu cầu tải lại trang game. Tampermonkey sẽ thực hiện tải lại sau tối đa 2 giây."
    }

@router.get("/script/command")
async def get_script_command():
    cmd = store.get_script_command()
    return {
        "command": cmd
    }

