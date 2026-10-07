[根目录](../CLAUDE.md) > **docs**

# TG Manage 文档模块

`docs/` 包含 VitePress 页面、公开静态文档与自托管部署说明。当前产品源码位于 [hikling/TG-Manage](https://github.com/hikling/TG-Manage)；上游来源见根目录 README。

## 入口

| 页面 | 用途 |
| --- | --- |
| `index.md`、`README.md`、`features.md` | 站点首页、文档目录和当前功能。 |
| `guide/` | 账号、聊天、备份及历史功能迁移说明。 |
| `deploy/` | Docker 安装、无损升级、Nginx 示例。 |
| `reference/` | 配置、架构、开发和运维参考。 |
| `public/` | 静态发现文件和公开 API 认证说明。 |

VitePress 配置位于 `.vitepress/config.mts`。本地构建运行仓库根目录的 `npm run docs:build`；它会先生成 Agent 发现资源，再构建站点。

## 维护约定

- 部署说明以 `docker-compose.yml`、`scripts/install.sh`、`scripts/update.sh` 和 `scripts/backup.sh` 为准。Compose 将 `./data` 挂载到 `/data`，无损升级必须保留完整目录。
- 当前界面包含仪表盘、账号管理、聊天中心、日志和系统设置；机器人中心位于系统设置。旧签到、关键词监听与 AI 动作已退出运行链路。
- Python 包名为 `tg_manage`。旧数据路径和环境变量兼容规则须与代码同步核对，不能仅按新品牌名推测磁盘迁移。
- 所有“本项目源码”“编辑此页”“GitHub”入口指向 hikling 仓库；上游地址仅用于来源或许可证说明。旧文档站域名的归属未确认，不应写成当前正式入口。
- 编辑文档后检查相对链接、示例命令和 VitePress 构建。历史迁移文档要明确哪些内容仍运行，哪些仅保留供备份。
