"""Authenticated dashboard appearance endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response

from backend.core.auth import get_current_user
from backend.services import appearance

router = APIRouter(dependencies=[Depends(get_current_user)])
HEADERS = {"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"}


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
    return Response(status_code=204, headers=HEADERS)
