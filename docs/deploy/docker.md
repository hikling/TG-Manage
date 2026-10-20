# Docker 部署与升级

本文适用于 [TG Manage 源码仓库](https://github.com/hikling/TG-Manage) 的 `Dockerfile` 和 `docker-compose.yml`。Compose 使用 `build: .`，从当前源码构建镜像。

## 部署前准备

- Linux 主机安装 Docker Engine 24+、Docker Compose v2 和 Git；主机需能下载 Python/npm 依赖、Xray 官方发布文件并连接 Telegram。
- 私有仓库需要对应 GitHub 读取权限。
- 小型部署最低支持 1 vCPU / 1 GiB RAM；Compose 不设置固定 CPU 或内存上限。更大的实例可以按账号数量和实际负载扩容，每个运行中的 TeleBox 账号还会启动独立 Node 进程。
- 需要自己的 Telegram API ID/Hash 时，在未提交的 `.env` 中设置 `TG_MANAGE_TG_API_ID` 和 `TG_MANAGE_TG_API_HASH`。旧部署的 `SIGNPULSE_TG_API_*`、`TG_API_*` 仍可读取。

## 首次安装

```bash
git clone https://github.com/hikling/TG-Manage.git
cd TG-Manage
bash scripts/install.sh
```

安装脚本执行 `docker compose up -d --build`，等待 `/readyz` 就绪，并输出一次性管理员设置码。浏览器打开 `http://服务器IP:8080`，用设置码创建至少 12 位的管理员密码。已有管理员账号不会被重置。公网访问请配置 [HTTPS 反向代理](nginx.md)。

当前 Compose 的关键约定：

| 配置 | 作用 |
| --- | --- |
| `./data:/data` | 宿主机持久化目录。包含 SQLite、会话、订阅密钥与 Xray 运行配置、TeleBox 账号数据和自定义仪表盘封面（`.tg_manage/appearance/` 或旧版 `.signer/appearance/`）。 |
| `container_name: tg-manage` | 容器名称；使用 `docker stats tg-manage` 查看容器资源。 |
| `read_only: true` 与 `/tmp` 临时卷 | 根文件系统只读；`/data` 必须可写。 |
| `/readyz` 健康检查 | 确认服务启动完成。 |

首次启动自动创建 `data/.app_secret_key`。它用于解密账号凭据和 Bot Token，必须与数据库及会话一起保留。

## 机场订阅与 Xray

镜像内置 [Xray-core v26.3.27 官方正式版](https://github.com/XTLS/Xray-core/releases/tag/v26.3.27)，构建时分别校验 Linux amd64 和 arm64 归档的固定 SHA-256，安装于 `/usr/local/bin/xray`。构建无法下载归档或校验不符时会直接失败。Xray 由应用作为子进程管理，只在容器回环地址上开放账号使用的本地 SOCKS 入站；Compose 不映射这些端口。运行配置及订阅凭据写入可写的 `/data`，根文件系统仍为只读。

首次安装或从旧版 SOCKS5 方案升级后，先在「设置 → 机场订阅」填入 HTTPS 主订阅，可选填兜底订阅，再刷新并确认有可用节点。未配置过任何订阅时，账号网络处于「待配置」，不会使用旧 SOCKS5 地址或静默直连。订阅支持 Clash 兼容 YAML 的 `proxies` 列表及普通或 Base64 编码的节点 URI 列表；支持 VLESS、VMess、Trojan、Shadowsocks 的已实现 TCP/WS/gRPC、TLS/REALITY 组合。设置页的「已导入」是成功解析的去重节点数；「可用」是最近一次连接探测正常、未超延迟阈值且没有已知 IP 定位失败的节点数；「不可用/不支持」包括已导入但不可用的节点以及格式不支持或字段不完整的条目，同一已导入节点只计一次。订阅 URL 相当于凭据；设置页状态、普通 API 和日志不显示原始 URL 或节点密钥。

每个健康节点只分配给一个账号。账号先使用主订阅空闲节点，再使用兜底订阅空闲节点；两者都不足或全部不可用时，多出的账号在账号卡片上明确标为「直连」，直连账号可能共用服务器出口 IP。若其他账号仍有节点，设置页显示混合线路状态。已测得的重复公网出口 IP 会触发重新分配；出口 IP 查询尚未完成或失败时，先保证节点不共用。节点健康每 5 分钟检测一次；首次异常 1 分钟后复检，连续两次超出当前延迟阈值或连接失败后才切换。初始阈值为 800 ms，可在设置中调整。订阅文档每 60 分钟刷新，也可手动刷新；设置时区的每天 00:00 还会在账户检测前刷新，并在启用 Bot 通知时发送主、兜底订阅的节点可用数与不可用/不支持数。回到优先订阅前需连续两次健康检测。切换网络线路不会删除 Telegram 与 TeleBox 会话；仅经 Telegram 确认授权无效时才需要重新验证。

账号卡片的 IP 定位只显示当前线路测得的出口国家，下方显示公网出口 IP，标题旁标明主订阅、兜底订阅或直连。当前节点经两家定位服务仍取不到公网 IP 和国家时，应用立即切换到另一个空闲健康节点，原节点暂停分配 5 分钟；订阅节点耗尽后使用直连。直连定位失败只显示检测失败，不会反复切换。定位失败不会把节点服务器地址误当作出口 IP。直连时的公网 IP 是服务器出口 IP，请在部署前确认该行为符合使用预期。

升级 Xray 时，在 `Dockerfile` 同时修改发布标签、amd64/arm64 文件名和官方发布资产 SHA-256，重新构建两种架构并检查版本。不要只改下载地址、跳过校验或在运行容器内覆盖二进制文件。检查镜像内版本：

```bash
docker compose exec -T app /usr/local/bin/xray version
```

若 `./data` 的宿主机所有者为非 root，入口脚本会以该 UID/GID 运行应用和 Xray 子进程。避免把新建的数据目录设为 root 所有者；既有数据迁移前先备份并核对原属主。

## 无损升级与回退

先确认当前仓库使用的 `./data:/data` 挂载及实际数据目录。若自定义了数据目录或使用外部 PostgreSQL，分别确认挂载源与数据库备份方案。不要只备份 `db.sqlite`，也不要遗漏隐藏文件。

在原仓库目录执行：

```bash
bash scripts/update.sh
```

脚本会短暂停止应用，避免 SQLite 文件及 WAL 在备份期间继续写入。随后检查现有数据目录，调用 `scripts/backup.sh` 将**整个目录**归档到 `backups/tg-manage-data-<时间>.tar.gz`，再运行 `git pull --ff-only` 和 `scripts/install.sh`。备份或拉取失败时会尝试重启原有服务。旧备份不会自动删除；请检查磁盘余量。`git pull --ff-only` 遇到本地提交冲突时会停止，不会强行覆盖。更新后原有 `./data:/data` 挂载保持不变。

若手动升级，顺序相同：停服务、完整备份 `data/`、从本仓库更新代码、运行 `docker compose up -d --build`。`docker compose down` 会删除容器和网络，但不会删除绑定挂载的 `./data`；不可使用 `down -v` 来代替常规升级。

升级后核查：

```bash
docker compose ps
docker compose logs --tail=100 app
curl -fsS http://127.0.0.1:8080/readyz
docker stats --no-stream tg-manage
```

再用原管理员账号登录，检查账号列表、Telegram 会话、系统设置和各账号 TeleBox 状态。使用 `docker stats` 观察整个容器的资源占用。

需要回退时，先 `docker compose stop app`，切回升级前的代码提交，恢复备份中的**完整**数据目录（包括 `.app_secret_key`、`sessions/`、`telebox/` 和隐藏文件），再执行 `docker compose up -d --build`。归档由 `backup.sh` 在数据目录的父目录打包；解压前先用 `tar -tzf <备份文件>` 核对顶层目录，避免解压到错误层级。回退旧代码可能无法读取新版本写入的数据，因此优先使用升级前的整目录备份。使用 PostgreSQL 时还要恢复同一时间点的数据库备份。

## 常用命令

```bash
docker compose ps
docker compose logs --tail=200 app
docker compose stop app
docker compose start app
```

## 排查

| 现象 | 检查项 |
| --- | --- |
| 构建失败 | Docker 磁盘/内存、npm/PyPI 网络、Xray 官方发布归档下载或 SHA-256 校验、TeleBox 原生模块错误。 |
| `/readyz` 未就绪 | `docker compose ps`、应用日志及 `./data` 的可写权限。 |
| Telegram 登录失败 | API ID/Hash、验证码/2FA、机场订阅状态、当前线路及服务器网络。 |
| 已导入节点，但可用节点为 0 | 初次探测、连接超时、延迟过高、已知出口 IP 定位失败或 Xray 未就绪，都可能使已导入节点暂时计入「不可用/不支持」。数字在首次异常探测后就会更新；路由仍按连续两次连接/延迟异常才切换。点“立即刷新订阅”可重新检测现有节点；首次异常后 1 分钟复检，常规每 5 分钟检测，恢复需连续两次成功。IP 定位只针对已分配给账号的线路，未分配节点尚未验证出口 IP。 |
| 节点全不可用 | 查看设置中的主/兜底订阅状态、上次刷新时间、已导入/可用节点数与延迟阈值；系统将明确显示直连，节点恢复后自动回切。 |
| IP 定位待验证或检测失败 | IP 和国家由账户当前线路访问两家定位服务获取。两家均失败时，订阅节点会临时退出分配并立即切到下一空闲健康节点；切换期间显示“IP 待验证”。全部节点失败则直连，直连定位也失败才显示“IP 检测失败”。点击该账户的“检测状态”可重试当前线路；不会把节点服务器地址冒充出口 IP。 |
| TeleBox 内存不足 | 观察 `docker stats` 和应用服务日志；按实际负载调高内存或减少常驻账号。 |

真实 Telegram 授权、Bot API 和 TeleBox 远程插件安装需要在目标环境验证。
