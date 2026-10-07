# WebDAV 备份与恢复

系统设置提供配置 JSON 导出及完整备份。两者用途不同：配置 JSON 不含 Telegram 会话和加密根密钥；完整备份包含 SQLite、`sessions/`、`telebox/`、`.app_secret_key` 等关键路径。换机或无损升级应另存**整个 `data/` 目录**，包括所有隐藏文件。外部 PostgreSQL 需要单独备份。

## 设置 WebDAV

在“系统设置 → 数据管理 → 完整备份”填入 WebDAV URL、用户名、密码和远端目录。新配置的远端目录默认为 `tg-manage-backups`；旧部署保留已保存的目录值。先测试连接，再保存设置。

密码与 Bot Token 不会在设置页回显明文。密码框重新打开后为空，不代表原设置丢失。

## 手动与自动备份

点击“上传备份到 WebDAV”可手动创建归档并上传。自动备份则按设置的间隔运行；上传成功后按保留份数轮转远端备份，失败时本地副本会保留在 `data/backups/`。可在面板列出并下载远端 `.tar.gz` 文件。下载只获取归档，不会在线恢复。

备份包包含可恢复的账号会话与密钥，应限制远端目录和下载文件的访问。宿主机还可以用 `bash scripts/backup.sh` 备份整个数据目录；它不会自动删除旧备份，详见 [运维手册](../reference/ops.md#手动备份)。

## 恢复

面板没有在线热恢复。先停止服务并留存当前 `data/`，再确认归档的顶层路径：

```bash
docker compose stop app
tar -tzf <备份文件.tar.gz> | head
```

面板导出的完整备份，归档内是 `db.sqlite`、`sessions/` 等数据目录下的相对路径，应解压到 `./data`。`scripts/backup.sh` 的宿主机归档带数据目录顶层名称，应解压到该目录的**父目录**，避免出现 `data/data/`。恢复后确认目录可写，再执行 `docker compose start app`，用原管理员登录并检查账号和 TeleBox 状态。

若使用外部 PostgreSQL，需恢复同一时间点的数据库备份。若 `.app_secret_key` 未与账号数据一起恢复，已加密凭据和 Bot Token 将无法解密。

升级时优先使用 [无损升级脚本](../deploy/docker.md#无损升级与回退)：它会停应用并对整个 `data/` 做静态备份。
