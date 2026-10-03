# Trellis bootstrap 进度与搭建记录

日期：2026-10-03（北京时间）
仓库：TG-SignPulse，分支 `feat/telebox-management-panel`

## 当前状态

- [x] 读取 `trellis-start/SKILL.md` 与 `00-bootstrap-guidelines/prd.md`。
- [x] 对照现有 `CLAUDE.md`、Python/Vue 源码及测试目录确定规范来源。
- [x] 填写后端规范与真实代码示例。
- [x] 填写前端规范与真实代码示例。
- [x] 校验链接、文件路径与 Trellis 任务状态。

## 搭建与变更流水

1. 当前仓库已有 `.trellis/scripts/` 和正在进行的 `10-02-telebox-panel`，但缺少 `.agents/skills/trellis-start/`、`.trellis/spec/` 和 `00-bootstrap-guidelines`。
2. 从先前的空白 Trellis 工作区读取启动技能、bootstrap 任务模板、索引和通用思考指南，复制到当前有实际源码的仓库；不会以空白工作区代替项目源码。
3. 执行 `python3 .trellis/scripts/init_developer.py hi`，建立本仓库的本地 Trellis 开发者身份。
4. 从现有项目代码提取团队已经采用的规则，填写 11 份后端/前端规范。模板里的通用占位语已被实际文件路径和例子替换。
5. 填写 `.trellis/spec/backend/` 的索引和 5 份规范，覆盖路由/服务边界、SQLAlchemy 与文件数据、错误状态、敏感日志、Ruff/pytest；实例来自 `communications.py`、`bots.py`、`telebox.py`、`database.py`、`users.py` 等。
6. 填写 `.trellis/spec/frontend/` 的索引和 6 份规范，覆盖 Vue 组件、composable、Pinia、接口类型及可访问性；实例来自 `Chats.vue`、`Layout.vue`、`useConfirm.ts`、`stores/accounts.ts`、`lib/api/core.ts` 等。
7. 将完整 `.agents/skills/` 与根 `AGENTS.md` 引入本仓库，供以后 `/trellis` 任务直接读取；加入 `.trellis/.gitignore`，让开发者身份与 session 指针留在本地。保留通用思考指南，不再使用空白 backend/frontend 模板。
8. 加入 `.codex/hooks.json`、`.codex/hooks/` 和 `.codex/agents/`，让 Codex 的任务状态注入及 Trellis agent 配置与现有工作流配套。

## 本地启动命令

```bash
cd TG-SignPulse
python3 .trellis/scripts/get_context.py
python3 .trellis/scripts/get_context.py --mode phase
python3 .trellis/scripts/get_context.py --mode packages
```

本记录在每一阶段完成后更新；最终补充验证结果和未验证事项。

## 校验结果

- `TRELLIS_CONTEXT_ID=bootstrap-guidelines python3 .trellis/scripts/task.py start 00-bootstrap-guidelines --allow-empty-context`：成功，任务状态 `in_progress`，没有覆盖另一个 `10-02-telebox-panel` 任务。
- `python3 .trellis/scripts/get_context.py --mode packages`：识别到 backend、frontend 两层规范。
- 规范和通用指南共 16 份 Markdown；检查 11 份具体规范与 2 份索引，没有未填写占位语，内部相对链接无失效，抽查的实际源文件路径均存在。
- `python3 -m compileall -q .codex/hooks .trellis/scripts`：通过。
- `task.py validate 00-bootstrap-guidelines`：通过；该任务没有 `implement.jsonl`/`check.jsonl`，工具提示跳过这两个可选清单。后续开发任务按需配置上下文。
- `.trellis/.developer` 与 `.trellis/.runtime/` 已由 `.trellis/.gitignore` 排除；没有把本地身份或会话指针列入版本控制。
- 本次只修改文档和 Trellis/Codex 配置，未运行业务测试，也未进行真实 Telegram 登录。若未来启动 hooks，需要在新 Codex 会话里重新加载仓库配置。

## 修改文件索引

| 位置 | 内容 |
| --- | --- |
| `.agents/skills/`, `AGENTS.md` | Trellis 启动、开发前检查、质量检查和收尾技能入口 |
| `.codex/hooks.json`, `.codex/hooks/`, `.codex/agents/` | Codex 提示与子任务上下文注入配置 |
| `.trellis/.gitignore` | 忽略本地身份、session 和临时状态 |
| `.trellis/spec/backend/` | 索引及 5 份按实际代码写的规范 |
| `.trellis/spec/frontend/` | 索引及 6 份按实际代码写的规范 |
| `.trellis/spec/guides/` | 通用代码复用和跨层思考指南 |
| `.trellis/tasks/00-bootstrap-guidelines/` | 任务状态、需求清单、本进度与搭建记录 |

## 注意

根和模块 `CLAUDE.md` 有早期插件系统的历史描述。已以当前代码及路由为准记录 TeleBox 和聊天中心，未把已删除的 Python 插件或频道管理页写入开发规范。此任务只改 Trellis 文档与入口，没有修改 Telegram 业务代码，也没有连接真实 Telegram。
