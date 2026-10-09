"""Authenticated dashboard appearance endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field

from backend.core.auth import get_current_user
from backend.services import appearance

router = APIRouter(dependencies=[Depends(get_current_user)])
HEADERS = {"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"}


class HeroSettingsRequest(BaseModel):
    position_x: float = Field(default=50.0, ge=0.0, le=100.0)
    position_y: float = Field(default=50.0, ge=0.0, le=100.0)


class HeroSettingsResponse(BaseModel):
    present: bool
    position_x: float = Field(default=50.0, ge=0.0, le=100.0)
    position_y: float = Field(default=50.0, ge=0.0, le=100.0)


@router.get("/hero-image")
def get_hero_image():
    result = appearance.read_hero()
    if result is None:
        raise HTTPException(404, "未设置自定义封面")
    data, media_type = result
    return Response(data, media_type=media_type, headers=HEADERS)


@router.put("/hero-image", status_code=204)
async def put_hero_image(file: UploadFile = File(...)):
    try:
        data = await file.read(appearance.MAX_HERO_UPLOAD_BYTES + 1)
    finally:
        await file.close()
    try:
        appearance.save_hero(data)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return Response(status_code=204, headers=HEADERS)


@router.delete("/hero-image", status_code=204)
def delete_hero_image():
    appearance.delete_hero()
    appearance.save_hero_position(*appearance.DEFAULT_HERO_POSITION)
    return Response(status_code=204, headers=HEADERS)


@router.get("/hero-settings", response_model=HeroSettingsResponse)
def get_hero_settings():
    x, y = appearance.get_hero_position()
    return HeroSettingsResponse(
        present=appearance.read_hero() is not None,
        position_x=x,
        position_y=y,
    )


@router.put("/hero-settings", response_model=HeroSettingsResponse)
def put_hero_settings(request: HeroSettingsRequest):
    appearance.save_hero_position(request.position_x, request.position_y)
    return HeroSettingsResponse(
        present=appearance.read_hero() is not None,
        position_x=request.position_x,
        position_y=request.position_y,
    )
