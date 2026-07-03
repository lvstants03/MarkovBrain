@echo off
cd /d "%~dp0.."

echo Dang kiem tra trang thai cac container Docker...
docker compose ps | findstr /i "markov_brain" >nul
if %errorlevel% equ 0 (
    echo Docker container dang chay. Dang ha container xuong truoc...
    docker compose down
) else (
    echo Docker container chua chay.
)

echo Dang khoi chay va build Docker container...
docker compose up -d --build
echo Hoan tat!
pause
