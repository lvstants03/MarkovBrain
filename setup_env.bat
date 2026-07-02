@echo off
echo Dang khoi tao moi truong ao Python (venv)...

if not exist .venv (
    python -m venv .venv
    echo Da tao moi truong ao trong thu muc .venv
) else (
    echo Moi truong ao da ton tai
)

echo Dang kich hoat moi truong ao...
call .venv\Scripts\activate.bat

echo Dang cap nhat pip va cai dat dependencies tu requirements.txt...
python -m pip install --upgrade pip
pip install -r requirements.txt

echo Da hoan tat cai dat!
echo Dang khoi chay FastAPI Web Server bang Uvicorn...
set PYTHONPATH=.
python src/main.py

pause
