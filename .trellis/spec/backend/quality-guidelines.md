# 后端质量规范

Python 支持 3.10–3.13；依赖及 Ruff 规则以 `pyproject.toml` 为准：`E4/E7/E9/F/I/B/W/C4`，历史上忽略 `E501/B008/C901/W191/B019/B904`，不要凭空宣称全项目遵循未配置的格式工具。Pydantic 版本锁定 v1；新路由可参考 `backend/api/routes/communications.py` 的 `BaseModel`、`Field` 和 validator。

测试在 `tests/test_*.py`，对外部 Telegram/Bot API 使用 mock 或隔离 fixture，测试鉴权、非法参数、跨账号访问和敏感输出。前后端协同时核对路径、JSON 字段与 string 类型的 Telegram chat ID；不要将超过 JS 安全整数范围的 ID 转成 number。

```bash
python3 -m ruff check backend tg_manage tests
python3 -m pytest -q tests/test_telebox_tasks.py tests/test_chat_center_settings.py
```

检查时区、旧数据兼容和服务停止后的资源释放。没有登录过真实 Telegram 账号时不得把模拟测试表述为端到端验证。

## Docker 依赖锁文件

Dockerfile 中使用 `npm ci` 的每个构建阶段必须同时提交 package.json 与 package-lock.json。不能依靠本地被忽略的锁文件；检查 `git ls-files` 和子目录 `.gitignore`。COPY 应显式写出两份文件，让缺失在构建前期暴露。新建临时目录复制这两份文件后执行 npm ci dry-run 可验证依赖图；这不能代替原生模块编译和完整镜像验收。
