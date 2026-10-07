"""Dashboard cover persistence and format validation."""
from types import SimpleNamespace

import pytest

from backend.services import appearance


@pytest.fixture(autouse=True)
def cover_workdir(tmp_path, monkeypatch):
    monkeypatch.setattr(
        appearance,
        "get_settings",
        lambda: SimpleNamespace(resolve_workdir=lambda: tmp_path),
    )
    return tmp_path


def test_cover_round_trip_and_delete(cover_workdir):
    image = b"\x89PNG\r\n\x1a\n" + b"picture"
    appearance.save_hero(image)
    assert appearance.read_hero() == (image, "image/png")
    assert (cover_workdir / "appearance" / "dashboard-hero.bin").is_file()
    appearance.delete_hero()
    assert appearance.read_hero() is None


@pytest.mark.parametrize(
    "content",
    [b"", b"<svg></svg>", b"not an image"],
)
def test_rejects_invalid_or_large_upload(content):
    with pytest.raises(ValueError, match="JPEG、PNG 或 WebP"):
        appearance.save_hero(content)


def test_rejects_oversized_image():
    content = b"\x89PNG\r\n\x1a\n" + b"x" * appearance.MAX_HERO_BYTES
    with pytest.raises(ValueError, match="JPEG、PNG 或 WebP"):
        appearance.save_hero(content)


def test_accepts_jpeg_and_webp():
    assert appearance.image_media_type(b"\xff\xd8\xffrest") == "image/jpeg"
    assert appearance.image_media_type(b"RIFF\x00\x00\x00\x00WEBPmore") == "image/webp"
