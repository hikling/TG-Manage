"""Dashboard cover persistence and format validation."""
from io import BytesIO
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


def test_accepts_exactly_two_mebibytes(cover_workdir):
    content = b"\x89PNG\r\n\x1a\n" + b"x" * (appearance.MAX_HERO_UPLOAD_BYTES - 8)
    appearance.save_hero(content)
    assert appearance.read_hero() == (content, "image/png")


def test_rejects_oversized_image_without_replacing_existing_cover(cover_workdir):
    original = b"\x89PNG\r\n\x1a\noriginal"
    appearance.save_hero(original)
    oversized = b"\x89PNG\r\n\x1a\n" + b"x" * appearance.MAX_HERO_UPLOAD_BYTES
    with pytest.raises(ValueError, match="JPEG、PNG 或 WebP"):
        appearance.save_hero(oversized)
    assert appearance.read_hero() == (original, "image/png")


def test_accepts_jpeg_and_webp():
    assert appearance.image_media_type(b"\xff\xd8\xffrest") == "image/jpeg"
    assert appearance.image_media_type(b"RIFF\x00\x00\x00\x00WEBPmore") == "image/webp"


def test_existing_oversized_cover_is_ignored(cover_workdir):
    content = b"\x89PNG\r\n\x1a\n" + b"x" * appearance.MAX_HERO_UPLOAD_BYTES
    path = cover_workdir / "appearance" / "dashboard-hero.bin"
    path.parent.mkdir(parents=True)
    path.write_bytes(content)
    assert appearance.read_hero() is None


def test_cover_removed_between_stat_and_read_is_treated_as_missing(monkeypatch):
    appearance.save_hero(b"\x89PNG\r\n\x1a\noriginal")
    path = appearance.hero_path()

    def removed_cover(*_args, **_kwargs):
        raise FileNotFoundError('Cover was reset by another request')

    monkeypatch.setattr(type(path), 'open', removed_cover)
    assert appearance.read_hero() is None


def test_cover_growing_after_stat_is_read_with_a_size_bound(monkeypatch):
    appearance.save_hero(b"\x89PNG\r\n\x1a\noriginal")
    path = appearance.hero_path()
    read_sizes = []

    class GrowingCover(BytesIO):
        def read(self, size=-1):
            read_sizes.append(size)
            return super().read(size)

    stream = GrowingCover(b"\x89PNG\r\n\x1a\n" + b'x' * appearance.MAX_HERO_BYTES)
    monkeypatch.setattr(type(path), 'open', lambda *_args, **_kwargs: stream)
    assert appearance.read_hero() is None
    assert read_sizes == [appearance.MAX_HERO_BYTES + 1]
    assert stream.closed


def test_hero_position_round_trip_and_reset(monkeypatch):
    state = {"hero_position_x": 50.0, "hero_position_y": 50.0}

    class FakeConfig:
        def get_global_settings(self):
            return dict(state)

        def save_global_settings(self, values):
            state.update(values)
            return True

    monkeypatch.setattr(
        "backend.services.config.get_config_service",
        lambda: FakeConfig(),
    )

    appearance.save_hero_position(12.5, 87.25)
    assert appearance.get_hero_position() == (12.5, 87.25)
    appearance.save_hero_position(*appearance.DEFAULT_HERO_POSITION)
    assert appearance.get_hero_position() == appearance.DEFAULT_HERO_POSITION
    state.update({"hero_position_x": float("nan"), "hero_position_y": 200})
    assert appearance.get_hero_position() == (50.0, 100.0)
