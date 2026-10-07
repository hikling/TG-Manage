# 数据与数据库规范

数据库入口是 `backend/core/database.py`：`init_engine()` 根据 Settings 建立 SQLAlchemy Engine；SQLite 设置 `check_same_thread=False`、30 秒连接超时和 WAL；`get_db()` yield Session，并在 `finally` 关闭。ORM 模型继承同一 `Base`。

```python
# backend/services/users.py 的已有模式
first_user = db.query(User).first()
if not first_user:
    db.add(User(username=username, password_hash=hash_password(password)))
    db.commit()
```

`backend/models/user.py`、`account.py`、`login_log.py` 显式定义列、索引和表名；时间默认值用 `backend/utils/time.py` 的 UTC helper。启动时 `backend/main.py` 调用 `Base.metadata.create_all(bind=get_engine())`；代码里没有独立的 Alembic 迁移体系。`create_all` 不会替已有表自动增删列，变更现有模式必须查明已有升级逻辑和旧库兼容路径，不可只修改 ORM 声明。

账号 session、Telegram 客户端工作目录及 TeleBox 状态并非全部存于 ORM：`backend/utils/tg_session.py`、`backend/core/config.py::resolve_workdir`、`backend/services/telebox.py` 分别处理这些文件。现有 `.signer` 工作目录优先于新 `.tg_manage` 目录，升级时不可删除旧目录。私有数据写入需沿用锁、原子替换、限制权限与账号隔离；不要把 Telegram 凭据暴露到 API 响应。
