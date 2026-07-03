#!/bin/bash
# Chuyen den thu muc goc cua du an
cd "$(dirname "$0")/.."

echo "Dang kiem tra trang thai cac container Docker..."
if docker compose ps | grep -E "markov_brain_app|markov_brain_redis" > /dev/null 2>&1; then
    echo "Docker container dang chay. Dang ha (down) container xuong truoc..."
    docker compose down
else
    echo "Docker container chua chay."
fi

echo "Dang khoi chay va build Docker container (up)..."
docker compose up -d --build
echo "Hoan tat!"
