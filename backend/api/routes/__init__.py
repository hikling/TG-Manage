from fastapi import APIRouter

from backend.api.routes import (
    accounts,
    auth,
    bots,
    communications,
    config,
    logs,
    ops,
    telebox,
    user,
)

router = APIRouter()
router.include_router(auth.router, prefix="/auth", tags=["auth"])
router.include_router(user.router, prefix="/user", tags=["user"])
router.include_router(accounts.router, prefix="/accounts", tags=["accounts"])
router.include_router(communications.router, tags=["communications"])
router.include_router(bots.router, tags=["bots"])
router.include_router(telebox.router, tags=["telebox"])
# 旧 /sign-tasks 动作接口不再注册，历史文件保留供手工迁移。
router.include_router(logs.router, prefix="/logs", tags=["logs"])
router.include_router(config.router, prefix="/config", tags=["config"])
router.include_router(ops.router, prefix="/ops", tags=["ops"])
