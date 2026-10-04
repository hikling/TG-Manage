"""Authenticated management of the per-account TeleBox processes."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, constr

from backend.core.auth import get_current_user
from backend.services.telebox import get_telebox_service
from backend.services.telebox_catalog import catalog as get_plugin_catalog

router = APIRouter(prefix="/telebox", dependencies=[Depends(get_current_user)])


class PasswordInput(BaseModel):
    password: constr(min_length=1, max_length=1024)


class PluginInput(BaseModel):
    action: constr(regex=r"^(install|uninstall|update|reload)$")
    name: constr(regex=r"^[A-Za-z0-9_-]{1,80}$") | None = None


def _error(exc: ValueError) -> HTTPException:
    detail = str(exc)
    return HTTPException(400 if "不存在" not in detail else 404, detail)


@router.get("")
def overview():
    return get_telebox_service().overview()


@router.get("/catalog")
async def catalog():
    try:
        return await get_plugin_catalog()
    except ValueError as exc:
        raise HTTPException(503, str(exc)) from None


@router.get("/{account}")
def status(account: str):
    try:
        return get_telebox_service().status(account)
    except ValueError as exc:
        raise _error(exc) from None


@router.post("/{account}/start")
async def start(account: str):
    try:
        return await get_telebox_service().start(account)
    except ValueError as exc:
        raise _error(exc) from None


@router.post("/{account}/stop")
async def stop(account: str):
    try:
        return await get_telebox_service().stop(account)
    except ValueError as exc:
        raise _error(exc) from None


@router.post("/{account}/restart")
async def restart(account: str):
    try:
        return await get_telebox_service().restart(account)
    except ValueError as exc:
        raise _error(exc) from None


@router.post("/{account}/password")
async def password(account: str, body: PasswordInput):
    try:
        return await get_telebox_service().password(account, body.password)
    except ValueError as exc:
        raise _error(exc) from None


@router.get("/{account}/logs")
def logs(account: str):
    try:
        return get_telebox_service().log_items(account)
    except ValueError as exc:
        raise _error(exc) from None


@router.post("/{account}/plugins")
async def plugin(account: str, body: PluginInput):
    try:
        return await get_telebox_service().plugins(account, body.action, body.name)
    except ValueError as exc:
        raise _error(exc) from None
