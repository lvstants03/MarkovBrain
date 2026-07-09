@echo off
cd /d "%~dp0.."

echo Dang tat va xoa sach container cu neu co...
docker compose down

echo Dang khoi chay va build Docker container...
docker compose up -d --build
echo Hoan tat!
pause
