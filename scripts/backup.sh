#!/usr/bin/env bash
set -euo pipefail

# 解析脚本所在目录的绝对路径，确保从任意工作目录执行都能正确定位
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
DATA_DIR="${APP_DATA_DIR:-$PROJECT_ROOT/data}"

# 验证 data 目录存在
if [ ! -d "$DATA_DIR" ]; then
    echo "错误: 数据目录不存在: $DATA_DIR" >&2
    exit 1
fi

# 解析为绝对路径，确保 APP_DATA_DIR 指向项目外目录时也能正确备份
DATA_DIR="$(cd "$DATA_DIR" && pwd)"

backup_dir="${BACKUP_DIR:-$PROJECT_ROOT/backups}"
mkdir -p "$backup_dir"

ts="$(date +%Y%m%d-%H%M%S)"
backup_path="$backup_dir/tg-manage-data-$ts.tar.gz"
if [ -e "$backup_path" ]; then
    echo "错误: 备份文件已存在，避免覆盖: $backup_path" >&2
    exit 1
fi

# 先写入临时文件，完整校验后才公开为正式备份。
backup_tmp="$(mktemp "$backup_dir/.tg-manage-data-$ts.XXXXXX.tmp")"
trap 'rm -f -- "$backup_tmp"' EXIT
tar -czf "$backup_tmp" \
    -C "$(dirname "$DATA_DIR")" \
    "$(basename "$DATA_DIR")"
tar -tzf "$backup_tmp" >/dev/null
mv -- "$backup_tmp" "$backup_path"
trap - EXIT

echo "备份完成: $backup_path"
echo '旧备份不会由此脚本自动删除，请按自己的保留策略定期检查磁盘空间。'
