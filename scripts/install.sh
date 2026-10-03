#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
if ! command -v docker >/dev/null || ! docker compose version >/dev/null 2>&1; then
  echo '需要 Docker Engine 和 Docker Compose v2。' >&2
  exit 1
fi

docker compose up -d --build
echo '等待面板启动…'
for attempt in $(seq 1 60); do
  if docker compose exec -T app python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/readyz', timeout=2)" >/dev/null 2>&1; then
    break
  fi
  sleep 2
done
if ! docker compose exec -T app python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/readyz', timeout=2)" >/dev/null 2>&1; then
  echo '启动超时；查看 docker compose logs --tail=200 app' >&2
  exit 1
fi

echo '面板地址：http://服务器IP:8080'
if docker compose exec -T app test -f /data/.admin_setup_token; then
  echo '首次设置码（在网页设置管理员密码后失效）：'
  docker compose exec -T app cat /data/.admin_setup_token
else
  echo '已有管理员，请用原账号和密码登录。'
fi
