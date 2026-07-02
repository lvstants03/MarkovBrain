@echo off
cd /d "%~dp0.."
if not exist .venv (
    echo Moi truong ao .venv chua duoc khoi tao. Vui lau chay scripts/setup.bat truoc!
    pause
    exit /b 1
)
echo Dang chay unit tests bang Pytest...
set PYTHONPATH=.
call .venv\Scripts\activate.bat
python -m pytest
pause
