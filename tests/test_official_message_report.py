"""Report-level completeness, eligibility, framing and temporary ownership."""
from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from backend.services import official_message_report as report
from backend.services.official_report_delivery import OfficialReportDeliveryError
from backend.services.telegram.official_report import (
    OfficialMedia,
    OfficialMessage,
    OfficialReadError,
)

END = datetime(2026, 10, 12, 16, tzinfo=timezone.utc)
START = END - timedelta(hours=24)


def message(identifier=1, *, epoch=None, text="official notice", **kwargs):
    return OfficialMessage(
        id=identifier, date_epoch=END.timestamp() - 1 if epoch is None else epoch,
        text=text, caption=kwargs.get("caption", ""), outgoing=kwargs.get("outgoing", False),
        media=kwargs.get("media"), unsupported_kind=kwargs.get("unsupported_kind"),
        content_details=kwargs.get("content_details", ""),
    )


def media(kind="document", size=17, name="notice.bin"):
    return OfficialMedia(kind, "source-file-reference", "stable-identity", size, name, "application/octet-stream")


@pytest.fixture
def report_env(monkeypatch):
    target = [("test-token", "123", 7)]
    service = SimpleNamespace(
        list_accounts=Mock(return_value=[{"name": "alpha"}]),
        check_account_status=AsyncMock(),
    )
    texts, uploads, paths = [], [], []

    async def send_text(text):
        texts.append(text)

    async def send_media(path, *, kind, filename, caption):
        paths.append(path)
        uploads.append({"data": path.read_bytes(), "kind": kind, "filename": filename, "caption": caption})

    delivery = SimpleNamespace(
        target_is_current=lambda: target[0] == ("test-token", "123", 7),
        send_text=AsyncMock(side_effect=send_text),
        send_media=AsyncMock(side_effect=send_media),
    )
    page = AsyncMock(return_value=[])
    refresh = AsyncMock(side_effect=lambda service, account, item, **kwargs: item)
    download = AsyncMock()
    persist = Mock()
    monkeypatch.setattr(report, "current_report_target", lambda: target[0])
    monkeypatch.setattr(report, "OfficialReportDelivery", lambda captured: delivery)
    monkeypatch.setattr(report, "get_telegram_service", lambda: service)
    monkeypatch.setattr(report, "read_official_page", page)
    monkeypatch.setattr(report, "refresh_official_message", refresh)
    monkeypatch.setattr(report, "download_official_part", download)
    monkeypatch.setattr("backend.utils.tg_session.set_account_status", persist)
    return SimpleNamespace(
        target=target, service=service, delivery=delivery, texts=texts, uploads=uploads,
        paths=paths, page=page, refresh=refresh, download=download, persist=persist,
    )


async def run(service=None):
    return await (service or report.OfficialMessageReportService()).run(
        start=START, end=END, timezone="Asia/Shanghai",
    )


def bodies(texts, label):
    return [text.split("\n\n", 1)[1] for text in texts if f"\n{label} · 分段 " in text]


@pytest.mark.asyncio
async def test_250_messages_include_short_middle_pages_and_exactly_once_overlap(report_env):
    env = report_env
    rows = [message(identifier, text=f"body-{identifier}") for identifier in range(250, 0, -1)]
    env.page.side_effect = [rows[:100], rows[99:117], rows[117:217], rows[217:], []]
    outcome = await run()
    assert outcome["messages"] == 250 and outcome["failed"] == 0
    assert bodies(env.texts, "文字") == [f"body-{identifier}" for identifier in range(250, 0, -1)]
    assert [item.kwargs["offset_id"] for item in env.page.await_args_list] == [0, 151, 134, 34, 1]
    assert all(item.kwargs["end"] == END for item in env.page.await_args_list)
    env.service.list_accounts.assert_called_once_with(force_refresh=True)
    env.service.check_account_status.assert_not_awaited()
    env.persist.assert_not_called()


@pytest.mark.asyncio
async def test_window_boundaries_and_outgoing_filter_precede_body_and_media(report_env):
    env = report_env
    env.page.side_effect = [[
        message(7, epoch=END.timestamp() + 1, text="future", media=media()),
        message(6, epoch=END.timestamp(), text="exact end", media=media()),
        message(5, outgoing=True, text="outgoing", media=media()),
        message(4, epoch=END.timestamp() - 1, text="last eligible"),
        message(3, epoch=START.timestamp(), text="first eligible"),
        message(2, epoch=START.timestamp() - 1, text="old", media=media()),
    ], AssertionError("must stop at verified lower bound")]
    outcome = await run()
    assert outcome["messages"] == 2 and outcome["empty"] == 0
    assert bodies(env.texts, "文字") == ["last eligible", "first eligible"]
    env.refresh.assert_not_awaited()
    env.download.assert_not_awaited()
    assert "2026-10-12 00:00:00 +0800" in env.texts[-1]
    assert all("账户：alpha" in text and "原消息时间：" in text for text in env.texts)


@pytest.mark.asyncio
async def test_no_daily_account_cap_and_duplicate_inventory_is_local_only(report_env):
    env = report_env
    names = [f"account-{i}" for i in range(225)]
    env.service.list_accounts.return_value = [{"name": name} for name in [*names, names[0], " "]]
    outcome = await run()
    assert outcome["accounts"] == outcome["empty"] == 225
    assert env.page.await_count == 225
    assert [item.args[1] for item in env.page.await_args_list] == names
    assert len(env.texts) == 225
    assert all("🟢 账户正常（最近24小时无官方消息）" in text for text in env.texts)


@pytest.mark.asyncio
@pytest.mark.parametrize("eligible_only", [[], [message(2, outgoing=True)], [message(1, epoch=START.timestamp() - 1)]])
async def test_exhausted_no_incoming_messages_gets_requested_normal(report_env, eligible_only):
    report_env.page.side_effect = [eligible_only, []]
    outcome = await run()
    assert outcome["empty"] == 1 and outcome["failed"] == 0
    assert "账户：alpha" in report_env.texts[0]
    assert "🟢 账户正常（最近24小时无官方消息）" in report_env.texts[0]


@pytest.mark.asyncio
@pytest.mark.parametrize("target", [None])
async def test_disabled_target_has_zero_inventory_history_media_or_sends(report_env, target):
    env = report_env
    env.target[0] = target
    outcome = await run()
    assert outcome["skipped"] is True
    env.service.list_accounts.assert_not_called()
    env.page.assert_not_awaited()
    env.download.assert_not_awaited()
    env.delivery.send_text.assert_not_awaited()


@pytest.mark.asyncio
async def test_complete_simultaneous_text_caption_details_with_whitespace_unicode(report_env):
    env = report_env
    raw_text = ("  前缀🙂\n\n\t尾部  \r\n" * 1200) + " \n"
    raw_caption = ("说明🌙 " * 500) + "\n\n末尾\t"
    details = "poll:\nquestion: 选择🙂\noption: A  "
    env.page.side_effect = [[message(text=raw_text, caption=raw_caption, content_details=details)], []]
    outcome = await run()
    assert outcome["failed"] == 0
    assert "".join(bodies(env.texts, "文字")) == raw_text
    assert "".join(bodies(env.texts, "原始说明")) == raw_caption
    assert "".join(bodies(env.texts, "官方消息详情")) == details
    assert all(report._units(text) <= report.MAX_CONTENT_UNITS for text in env.texts)
    assert all("账户：alpha" in text and "官方消息 #1" in text and "+0800" in text for text in env.texts)


@pytest.mark.asyncio
@pytest.mark.parametrize("failure_page", [0, 1])
async def test_failed_or_partial_history_is_red_and_other_accounts_continue(report_env, failure_page, caplog):
    env = report_env
    env.service.list_accounts.return_value = [{"name": "alpha"}, {"name": "beta"}]
    failure = RuntimeError("secret message and https://api.telegram.org/botSECRET/file")
    env.page.side_effect = ([failure] if failure_page == 0 else [[message()], failure]) + [[]]
    outcome = await run()
    assert outcome["accounts"] == 2 and outcome["failed"] == 1 and outcome["empty"] == 1
    alpha = [text for text in env.texts if "账户：alpha" in text]
    assert any("🔴 官方消息历史读取失败" in text for text in alpha)
    assert not any("账户正常" in text for text in alpha)
    assert "账户：beta" in env.texts[-1] and "账户正常" in env.texts[-1]
    assert "SECRET" not in caplog.text + "".join(env.texts)
    env.persist.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("page", [[message(10)], [message(11), message(10)]])
async def test_nonprogress_cursor_fails_without_repeating_content(report_env, page):
    env = report_env
    env.page.side_effect = [[message(10)], page]
    outcome = await run()
    assert outcome["failed"] == 1 and outcome["empty"] == 0
    assert bodies(env.texts, "文字") == ["official notice"]
    assert env.page.await_count == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("invalid", [message(epoch=float("nan")), message(0)])
async def test_unverifiable_history_is_not_normal(report_env, invalid):
    report_env.page.side_effect = [[invalid]]
    outcome = await run()
    assert outcome["failed"] == 1 and outcome["empty"] == 0
    assert all("账户正常" not in text for text in report_env.texts)


@pytest.mark.asyncio
async def test_unsupported_or_contentless_notice_counted_and_explicitly_failed(report_env):
    env = report_env
    env.page.side_effect = [[
        message(2, text="original text", content_details="payload: preserved", unsupported_kind="poll"),
        message(1, text=""),
    ], []]
    outcome = await run()
    assert outcome["messages"] == 2 and outcome["failed"] == 1 and outcome["empty"] == 0
    assert "original text" in "".join(env.texts) and "payload: preserved" in "".join(env.texts)
    assert sum("🔴" in text for text in env.texts) == 2


def setup_download(env, payload):
    async def download(service, account, item, destination, *, offset_bytes, length_bytes, **kwargs):
        assert not any(path.exists() for path in env.paths)
        env.paths.append(destination)
        destination.write_bytes(payload[offset_bytes:offset_bytes + length_bytes])
    env.download.side_effect = download


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["photo", "video", "document", "voice"])
async def test_actual_native_media_bytes_and_caption_preserved_then_cleaned(report_env, kind):
    env = report_env
    payload = b"original-media-123"
    caption = " long caption🙂\n" * 1000
    item = message(text="", caption=caption, media=media(kind, len(payload), "../../source.bin"))
    env.page.side_effect = [[item], []]
    setup_download(env, payload)
    outcome = await run()
    assert outcome["messages"] == 1 and outcome["failed"] == 0 and outcome["empty"] == 0
    assert "".join(bodies(env.texts, "原始说明")) == caption
    assert env.uploads[0]["data"] == payload
    assert env.uploads[0]["kind"] == kind
    assert env.uploads[0]["filename"] == "source.bin"
    assert "账户：alpha" in env.uploads[0]["caption"] and "#1" in env.uploads[0]["caption"]
    assert all(not path.exists() and not path.parent.exists() for path in env.paths)
    env.persist.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("size", [8, 9, 16, 17])
async def test_oversize_parts_reconstruct_every_byte_with_one_owned_part(report_env, monkeypatch, size):
    env = report_env
    monkeypatch.setattr(report, "MEDIA_PART_BYTES", 8)
    payload = bytes(range(size))
    env.page.side_effect = [[message(text="", media=media("video", size))], []]
    setup_download(env, payload)
    outcome = await run()
    count = (size + 7) // 8
    assert outcome["failed"] == 0 and len(env.uploads) == count
    assert b"".join(item["data"] for item in env.uploads) == payload
    for index, item in enumerate(env.uploads, 1):
        assert f"附件 {index}/{count}" in item["caption"]
        assert "账户：alpha" in item["caption"] and "原始文件名：notice.bin" in item["caption"]
        if count > 1:
            assert item["kind"] == "document"
            assert f"part{index:04d}-of-{count:04d}" in item["filename"]
    if count > 1:
        assert any("分卷不是压缩包" in text for text in env.texts)
        assert any(f"全部 {count} 个分卷已发送，共 {size} 字节" in text for text in env.texts)
    assert all(not path.exists() and not path.parent.exists() for path in env.paths)


@pytest.mark.asyncio
async def test_unknown_size_refreshes_and_all_parts_use_refreshed_identity(report_env, monkeypatch):
    env = report_env
    monkeypatch.setattr(report, "MEDIA_PART_BYTES", 8)
    original = message(text="", media=media(size=None))
    refreshed = replace(original, media=replace(original.media, file_size=17, file_id="fresh-reference"))
    env.refresh.return_value = refreshed
    env.refresh.side_effect = None
    env.page.side_effect = [[original], []]
    setup_download(env, bytes(range(17)))
    outcome = await run()
    assert outcome["failed"] == 0
    env.refresh.assert_awaited_once_with(env.service, "alpha", original, start=START, end=END)
    assert all(item.args[2] is refreshed for item in env.download.await_args_list)


@pytest.mark.asyncio
@pytest.mark.parametrize("size", [None, 0, -1])
async def test_unverifiable_media_size_explicit_failure_with_no_download(report_env, size):
    env = report_env
    env.page.side_effect = [[message(text="retained", media=media(size=size))], []]
    outcome = await run()
    assert outcome["messages"] == 1 and outcome["failed"] == 1 and outcome["empty"] == 0
    env.download.assert_not_awaited()
    assert bodies(env.texts, "文字") == ["retained"]
    assert any("🔴" in text for text in env.texts)


@pytest.mark.asyncio
async def test_short_download_never_sent_as_complete_and_cleans_part(report_env):
    env = report_env
    env.page.side_effect = [[message(text="", media=media(size=17))], []]
    setup_download(env, b"short")
    outcome = await run()
    assert outcome["failed"] == 1 and outcome["empty"] == 0
    env.delivery.send_media.assert_not_awaited()
    assert all(not path.exists() and not path.parent.exists() for path in env.paths)


@pytest.mark.asyncio
async def test_media_upload_error_preserves_text_and_cleans_paths(report_env):
    env = report_env
    env.page.side_effect = [[message(text="original message", media=media(size=17))], []]
    setup_download(env, bytes(range(17)))
    env.delivery.send_media.side_effect = OfficialReportDeliveryError("safe upload failure")
    outcome = await run()
    assert outcome["failed"] == 1 and outcome["empty"] == 0
    assert bodies(env.texts, "文字") == ["original message"]
    assert any("未完整转发" in text for text in env.texts)
    assert all(not path.exists() and not path.parent.exists() for path in env.paths)


@pytest.mark.asyncio
async def test_later_part_failure_marks_partial_and_continues_next_account(report_env, monkeypatch):
    env = report_env
    monkeypatch.setattr(report, "MEDIA_PART_BYTES", 8)
    env.service.list_accounts.return_value = [{"name": "alpha"}, {"name": "beta"}]
    env.page.side_effect = [[message(text="", media=media(size=17))], [], []]
    setup_download(env, bytes(range(17)))
    successful_download = env.download.side_effect

    async def download(*args, **kwargs):
        if kwargs["offset_bytes"] == 8:
            raise OfficialReadError("safe transfer failure")
        await successful_download(*args, **kwargs)
    env.download.side_effect = download
    outcome = await run()
    assert outcome["failed"] == 1 and outcome["empty"] == 1
    assert len(env.uploads) == 1
    assert not any("全部 3 个分卷已发送" in text for text in env.texts)
    assert any("账户：alpha" in text and "未完整转发" in text for text in env.texts)
    assert all(not path.exists() and not path.parent.exists() for path in env.paths)


@pytest.mark.asyncio
async def test_bot_send_failure_never_normal_and_unrelated_accounts_continue(report_env):
    env = report_env
    env.service.list_accounts.return_value = [{"name": "alpha"}, {"name": "beta"}]
    env.page.side_effect = [[message()], [], []]
    ordinary_send = env.delivery.send_text.side_effect

    async def send(text):
        if "文字 · 分段" in text:
            raise OfficialReportDeliveryError("safe rejected upload")
        await ordinary_send(text)
    env.delivery.send_text.side_effect = send
    outcome = await run()
    assert outcome["failed"] == 1 and outcome["empty"] == 1
    assert any("账户：alpha" in text and "🔴" in text for text in env.texts)
    assert not any("账户：alpha" in text and "账户正常" in text for text in env.texts)


@pytest.mark.asyncio
async def test_no_message_delivery_failure_still_continues_other_accounts(report_env):
    env = report_env
    env.service.list_accounts.return_value = [{"name": "alpha"}, {"name": "beta"}]
    ordinary_send = env.delivery.send_text.side_effect

    async def send(text):
        if "账户：alpha" in text:
            raise OfficialReportDeliveryError("safe rejection")
        await ordinary_send(text)
    env.delivery.send_text.side_effect = send
    outcome = await run()
    assert outcome["accounts"] == 2 and outcome["failed"] == 1 and outcome["empty"] == 1
    assert all("账户：beta" in text for text in env.texts)


@pytest.mark.asyncio
@pytest.mark.parametrize("phase", ["history", "text", "download"])
async def test_target_change_stops_remaining_reads_and_sends(report_env, phase):
    env = report_env
    env.service.list_accounts.return_value = [{"name": "alpha"}, {"name": "beta"}]
    item = message(text="" if phase == "download" else "notice", media=media() if phase == "download" else None)
    if phase == "history":
        async def page(*args, **kwargs):
            env.target[0] = None
            return [item]
        env.page.side_effect = page
    else:
        env.page.side_effect = [[item], []]
        if phase == "text":
            async def send(text):
                env.texts.append(text)
                env.target[0] = ("new-token", "999", None)
            env.delivery.send_text.side_effect = send
        else:
            setup_download(env, b"original-media-123")
            ordinary_download = env.download.side_effect

            async def download(*args, **kwargs):
                await ordinary_download(*args, **kwargs)
                env.target[0] = None
            env.download.side_effect = download
    outcome = await run()
    assert outcome["stopped"] is True and outcome["accounts"] == 1
    assert env.page.await_count == 1
    env.delivery.send_media.assert_not_awaited()
    if phase != "text":
        env.delivery.send_text.assert_not_awaited()
    assert all(not path.exists() and not path.parent.exists() for path in env.paths)


@pytest.mark.asyncio
@pytest.mark.parametrize("phase", ["history", "download", "upload"])
async def test_cancellation_releases_report_lock_and_all_temporary_paths(report_env, phase):
    env = report_env
    started = asyncio.Event()
    item = message(text="", media=media())
    env.page.side_effect = [[item], []]
    setup_download(env, b"original-media-123")

    async def wait(*args, **kwargs):
        started.set()
        await asyncio.Event().wait()
    if phase == "history":
        env.page.side_effect = wait
    elif phase == "download":
        normal_download = env.download.side_effect

        async def waiting_download(*args, **kwargs):
            await normal_download(*args, **kwargs)
            await wait()
        env.download.side_effect = waiting_download
    else:
        env.delivery.send_media.side_effect = wait
    service = report.OfficialMessageReportService()
    task = asyncio.create_task(run(service))
    try:
        await asyncio.wait_for(started.wait(), 1)
        assert (await run(service))["skipped"] is True
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert not service._running_lock.locked()
        assert all(not path.exists() and not path.parent.exists() for path in env.paths)
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
async def test_part_cleanup_failure_stops_next_allocation_and_is_explicit(report_env, monkeypatch, caplog):
    env = report_env
    monkeypatch.setattr(report, "MEDIA_PART_BYTES", 8)
    env.page.side_effect = [[message(text="", media=media(size=17))], []]
    setup_download(env, bytes(range(17)))
    actual_unlink = Path.unlink
    attempted = []

    def unlink(path, *args, **kwargs):
        if path.name == "payload-0":
            attempted.append(path)
            raise PermissionError("private source and token must not be logged")
        return actual_unlink(path, *args, **kwargs)
    monkeypatch.setattr(Path, "unlink", unlink)
    outcome = await run()
    assert outcome["failed"] == 1 and env.download.await_count == 1
    assert len(env.uploads) == 1
    assert all(not path.exists() and not path.parent.exists() for path in attempted)
    assert "PermissionError" in caplog.text
    assert "private source" not in caplog.text
    assert not any("附件全部" in text for text in env.texts)


@pytest.mark.asyncio
async def test_directory_cleanup_exception_does_not_replace_cancellation(report_env, monkeypatch, caplog):
    env = report_env
    actual_temporary = report.TemporaryDirectory

    class CleanupFailure:
        def __init__(self, **kwargs):
            self.owner = actual_temporary(**kwargs)
            self.name = self.owner.name

        def cleanup(self):
            self.owner.cleanup()
            raise PermissionError("secret source filename")

    monkeypatch.setattr(report, "TemporaryDirectory", CleanupFailure)
    env.page.side_effect = [[message(text="", media=media(size=17))], []]
    setup_download(env, bytes(range(17)))
    env.delivery.send_media.side_effect = asyncio.CancelledError
    service = report.OfficialMessageReportService()
    with pytest.raises(asyncio.CancelledError):
        await run(service)
    assert not service._running_lock.locked()
    assert all(not path.exists() and not path.parent.exists() for path in env.paths)
    assert "PermissionError" in caplog.text and "secret source" not in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize("start", [START.replace(tzinfo=None), START - timedelta(seconds=1), END])
async def test_bad_window_refused_before_history(report_env, start):
    with pytest.raises(ValueError):
        await report.OfficialMessageReportService().run(start=start, end=END, timezone="UTC")
    report_env.page.assert_not_awaited()
