"""The private bot entry must never authenticate another Telegram ID."""

import hashlib
import hmac
import json
import unittest
from unittest.mock import AsyncMock, patch
from urllib.parse import urlencode

from backend.services.bot_webapp import menu_url, sync_menu_button, validate_init_data


SETTINGS = {
    "telegram_bot_token": "123:secret",
    "telegram_bot_chat_id": "12345",
    "telegram_bot_web_url": "https://example.com",
}


def signed_data(user_id: int, auth_date: int = 1000) -> str:
    fields = {"auth_date": str(auth_date), "user": json.dumps({"id": user_id}, separators=(",", ":"))}
    check = "\n".join(f"{key}={value}" for key, value in sorted(fields.items()))
    secret = hmac.new(b"WebAppData", SETTINGS["telegram_bot_token"].encode(), hashlib.sha256).digest()
    fields["hash"] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    return urlencode(fields)


class BotWebAppTests(unittest.TestCase):
    def test_only_fresh_signed_target_can_login(self):
        valid = signed_data(12345)
        self.assertTrue(validate_init_data(valid, SETTINGS, now=1000))
        self.assertFalse(validate_init_data(signed_data(99999), SETTINGS, now=1000))
        self.assertFalse(validate_init_data(valid, SETTINGS, now=1121))
        self.assertFalse(validate_init_data(valid.replace("12345", "99999"), SETTINGS, now=1000))
        self.assertFalse(validate_init_data(valid + "&user=%7B%7D", SETTINGS, now=1000))
        self.assertFalse(validate_init_data(valid, {**SETTINGS, "telegram_bot_chat_id": "-100123"}, now=1000))
        self.assertFalse(validate_init_data(valid, {**SETTINGS, "telegram_bot_web_url": None}, now=1000))
        self.assertFalse(validate_init_data(valid, {**SETTINGS, "telegram_bot_token": "other:token"}, now=1000))

    def test_menu_requires_https_root(self):
        self.assertEqual(menu_url(SETTINGS), "https://example.com/bot")
        for raw in ("http://example.com", "https://example.com/other", "https://a@b.com", "https://example.com/?x=1"):
            with self.assertRaises(ValueError):
                menu_url({"telegram_bot_web_url": raw})


class BotMenuTests(unittest.IsolatedAsyncioTestCase):
    async def test_only_target_gets_web_button(self):
        with patch("backend.services.bot_webapp._set_button", new_callable=AsyncMock) as set_button:
            self.assertTrue(await sync_menu_button(SETTINGS))
        payloads = [call.args[2] for call in set_button.await_args_list]
        self.assertEqual(payloads, [
            {"menu_button": {"type": "commands"}},
            {"chat_id": 12345, "menu_button": {
                "type": "web_app", "text": "打开WEB", "web_app": {"url": "https://example.com/bot"},
            }},
        ])

    async def test_old_target_is_cleared_even_when_replaced(self):
        previous = {**SETTINGS, "telegram_bot_chat_id": "67890"}
        with patch("backend.services.bot_webapp._set_button", new_callable=AsyncMock) as set_button:
            self.assertTrue(await sync_menu_button(SETTINGS, previous))
        payloads = [call.args[2] for call in set_button.await_args_list]
        self.assertEqual(payloads[0], {"chat_id": 67890, "menu_button": {"type": "commands"}})
        self.assertEqual(payloads[-1]["chat_id"], 12345)

    async def test_cleanup_failure_does_not_skip_new_target(self):
        previous = {**SETTINGS, "telegram_bot_chat_id": "67890"}
        with patch("backend.services.bot_webapp._set_button", new_callable=AsyncMock) as set_button:
            set_button.side_effect = [RuntimeError("old target unavailable"), None, None]
            self.assertFalse(await sync_menu_button(SETTINGS, previous))
            self.assertEqual(set_button.await_count, 3)

    async def test_disabling_web_entry_removes_private_button(self):
        disabled = {**SETTINGS, "telegram_bot_web_url": None}
        with patch("backend.services.bot_webapp._set_button", new_callable=AsyncMock) as set_button:
            self.assertTrue(await sync_menu_button(disabled, SETTINGS))
        payloads = [call.args[2] for call in set_button.await_args_list]
        self.assertEqual(payloads, [
            {"chat_id": 12345, "menu_button": {"type": "commands"}},
            {"menu_button": {"type": "commands"}},
        ])
