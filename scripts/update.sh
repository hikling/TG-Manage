#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
DATA_DIR="${APP_DATA_DIR:-$PROJECT_ROOT/data}"

cd "$PROJECT_ROOT"
git rev-parse --is-inside-work-tree >/dev/null

if [ ! -d "$DATA_DIR" ]; then
    echo "错误: 找不到现有数据目录: $DATA_DIR" >&2
    echo '首次安装请使用 scripts/install.sh；升级前请先确认数据挂载位置。' >&2
    exit 1
fi

echo '备份现有数据…'
echo '暂停应用以确保 SQLite 数据库与会话文件在备份时保持一致…'
restore_on_error() {
    local status=$?
    trap - ERR
    echo '升级中断，尝试重新启动应用；请检查服务状态与备份文件。' >&2
    docker compose start app >&2 || true
    exit "$status"
}
trap restore_on_error ERR
docker compose stop app

bash "$SCRIPT_DIR/backup.sh"

echo '拉取最新代码（仅允许快进，避免覆盖本地修改）…'
git pull --ff-only

echo '重建并启动容器，继续挂载原有 ./data 目录…'
bash "$SCRIPT_DIR/install.sh"
trap - ERR

echo '升级完成。备份文件保留在 backups/，请验证账号、会话和设置后再自行管理旧备份。'
