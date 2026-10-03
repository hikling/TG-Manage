"""拆分包 import 健康检查。

防止再出现：
1. `import *` 漏掉下划线私有名（accounts NameError）
2. core 子模块 star-import 残缺导致 import 即 NameError
"""
from __future__ import annotations

import importlib
import pkgutil

import pytest

CRITICAL_MODULES = [
    "backend.main",
    "backend.api.routes.accounts",
    "backend.api.routes.accounts_schemas",
    "backend.api.routes.logs",
    "backend.api.routes.telebox_tasks",
    "backend.services.telebox_tasks",
    "backend.services.telegram",
    "tg_signer.core",
    "tg_signer.core.client",
]


@pytest.mark.parametrize("module_name", CRITICAL_MODULES)
def test_critical_module_imports(module_name: str):
    importlib.import_module(module_name)


def test_core_package_reexports_client_identity():
    """账号客户端包级导出与实现保持同一对象。"""
    client = importlib.import_module("tg_signer.core.client")
    core = importlib.import_module("tg_signer.core")
    assert core.Client is client.Client
    assert core.get_client is client.get_client


def test_backend_and_tg_signer_package_walk_imports():
    """全量 walk import：任一子模块 import 失败即视为带病。"""
    failed: list[str] = []
    for pkg_name in ("backend", "tg_signer"):
        pkg = importlib.import_module(pkg_name)
        if not hasattr(pkg, "__path__"):
            continue
        for info in pkgutil.walk_packages(pkg.__path__, prefix=pkg_name + "."):
            try:
                importlib.import_module(info.name)
            except Exception as exc:  # noqa: BLE001 — 收集全部失败再断言
                failed.append(f"{info.name}: {type(exc).__name__}: {exc}")

    assert not failed, "import failed:\n" + "\n".join(failed)
