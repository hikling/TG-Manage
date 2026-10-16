"""Focused tests for subscription parsing, route hysteresis and Xray isolation."""
from __future__ import annotations

import asyncio
import base64
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from backend.services.account_routes import AccountRouteService, RouteSetupRequired
from backend.services.subscription_import import (
    SubscriptionError,
    fetch_subscription,
    parse_subscription,
)
from backend.services.xray_runtime import (
    XrayRuntime,
    XrayRuntimeError,
    build_xray_config,
)


class _Process:
    returncode = None

    def terminate(self):
        self.returncode = 0

    def kill(self):
        self.returncode = -9

    async def wait(self):
        self.returncode = self.returncode or 0
        return self.returncode


class _Generation:
    number = 101
    process = _Process()


class _Runtime:
    def __init__(self) -> None:
        self.active = _Generation()
        self.ports: dict[str, int] = {}

    def port_for(self, key: str, generation_number: int | None = None) -> int | None:
        return self.ports.get(key)

    async def replace(self, nodes, accept=None):
        ports = {f"{node.source}:{node.node_id}": 21000 + index for index, node in enumerate(nodes)}
        if accept is not None and not await accept(ports):
            raise XrayRuntimeError("XRAY_CANDIDATE_UNHEALTHY")
        self.ports = ports
        return True

    async def shutdown(self):
        pass


class SubscriptionImportTests(unittest.TestCase):
    def test_uri_and_clash_import_are_bounded_and_deduplicated(self):
        url = "vless://00000000-0000-0000-0000-000000000001@example.com:443?security=tls&type=ws&path=%2Fpath#node"
        encoded = base64.b64encode((url + "\n" + url + "\nunknown://host").encode())
        imported = parse_subscription(encoded, "primary")
        self.assertEqual(len(imported.nodes), 1)
        self.assertEqual(imported.unsupported_count, 1)
        self.assertEqual(imported.nodes[0].outbound["streamSettings"]["wsSettings"]["path"], "/path")
        clash = parse_subscription(b"proxies:\n  - name: safe\n    type: trojan\n    server: example.org\n    port: 443\n    password: secret\n    tls: true\n", "fallback")
        self.assertEqual(len(clash.nodes), 1)
        self.assertEqual(clash.nodes[0].outbound["protocol"], "trojan")
        self.assertNotIn("secret", clash.nodes[0].label)

    def test_yaml_alias_and_oversize_are_rejected(self):
        with self.assertRaises(SubscriptionError):
            parse_subscription(b"proxies: &p []\ncopy: *p", "primary")
        with self.assertRaises(SubscriptionError):
            parse_subscription(b"x" * (1024 * 1024 + 1), "primary")

    def test_xray_config_has_no_default_direct_exit(self):
        node = parse_subscription(b"trojan://secret@example.org:443?security=tls", "primary").nodes[0]
        config = build_xray_config([node], [23456])
        self.assertEqual(config["inbounds"][0]["listen"], "127.0.0.1")
        self.assertEqual(config["outbounds"][0]["protocol"], "blackhole")
        self.assertEqual(config["routing"]["rules"][0]["outboundTag"], "node-0")


class AccountRouteTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.runtime = _Runtime()
        self.service = AccountRouteService(Path(self.temp.name), self.runtime)
        self.service._schedule_geo_for_accounts = lambda accounts: None
        self.service._all_accounts = lambda: {"one", "two"}
        self.names = patch("backend.services.account_routes.list_account_names", return_value=["one", "two"])
        self.names.start()
        primary = parse_subscription(b"trojan://secret@example.org:443?security=tls", "primary").nodes[0]
        second_primary = parse_subscription(b"trojan://secret2@example.com:443?security=tls", "primary").nodes[0]
        fallback = parse_subscription(b"trojan://backup@example.net:443?security=tls", "fallback").nodes[0]
        self.primary, self.second_primary, self.fallback = primary, second_primary, fallback
        self.service._secret["nodes"] = {
            "primary": [primary.__dict__, second_primary.__dict__], "fallback": [fallback.__dict__],
        }
        self.runtime.ports = {
            self.service._key(primary): 21001,
            self.service._key(second_primary): 21003,
            self.service._key(fallback): 21002,
        }

    async def asyncTearDown(self):
        self.names.stop()
        await self.service.shutdown()
        self.temp.cleanup()

    async def test_setup_required_then_distinct_and_direct_when_nodes_run_out(self):
        with self.assertRaises(RouteSetupRequired):
            self.service.resolve_account_route("one")
        self.service._secret["ever_configured"] = True
        self.service._record_sample(self.service._key(self.primary), 100)
        self.service._record_sample(self.service._key(self.second_primary), 110)
        self.service._record_sample(self.service._key(self.fallback), 120)
        self.service._reconcile()
        self.assertNotEqual(self.service.account_route_status("one")["node_label"], None)
        self.assertNotEqual(self.service.resolve_account_route("one")["port"], self.service.resolve_account_route("two")["port"])
        self.assertEqual(self.service.account_route_status("one")["route_mode"], "primary")
        self.assertEqual(self.service.account_route_status("two")["route_mode"], "primary")
        self.service._state["health"][self.service._key(self.fallback)]["healthy"] = False
        self.service._state["health"][self.service._key(self.second_primary)]["healthy"] = False
        self.service._state["assignments"].clear()
        self.service._reconcile()
        self.assertEqual(self.service.resolve_account_route("one")["port"], 21001)
        self.assertIsNone(self.service.resolve_account_route("two"))
        self.assertFalse(self.service.account_route_status("one")["shared_node"])
        self.assertFalse(self.service.account_route_status("two")["shared_node"])

    async def test_two_failures_switch_to_fallback_then_two_successes_recover(self):
        self.service._all_accounts = lambda: {"one"}
        self.service._secret["ever_configured"] = True
        p = self.service._key(self.primary)
        f = self.service._key(self.fallback)
        self.service._record_sample(p, 100)
        self.service._record_sample(p, 100)
        self.service._record_sample(f, 110)
        self.service._record_sample(f, 110)
        self.service._reconcile()
        self.assertEqual(self.service.account_route_status("one")["route_mode"], "primary")
        self.service._record_sample(p, None)
        self.service._reconcile()
        self.assertEqual(self.service.account_route_status("one")["route_mode"], "primary")
        self.service._record_sample(p, None)
        self.service._reconcile()
        self.assertEqual(self.service.account_route_status("one")["route_mode"], "fallback")
        self.service._record_sample(p, 100)
        self.service._reconcile()
        self.assertEqual(self.service.account_route_status("one")["route_mode"], "fallback")
        self.service._record_sample(p, 100)
        self.service._reconcile()
        self.assertEqual(self.service.account_route_status("one")["route_mode"], "primary")

    async def test_legacy_shared_route_moves_second_account_to_free_fallback(self):
        self.service._secret["ever_configured"] = True
        primary_key = self.service._key(self.primary)
        fallback_key = self.service._key(self.fallback)
        self.service._record_sample(primary_key, 90)
        self.service._record_sample(fallback_key, 110)
        self.service._assign("one", self.primary)
        self.service._assign("two", self.primary)

        self.service._reconcile()

        self.assertEqual(self.service.resolve_account_route("one")["port"], 21001)
        self.assertEqual(self.service.resolve_account_route("two")["port"], 21002)
        self.assertFalse(self.service.account_route_status("one")["shared_node"])
        self.assertFalse(self.service.account_route_status("two")["shared_node"])

    async def test_same_verified_exit_ip_does_not_serve_two_accounts(self):
        self.service._secret["ever_configured"] = True
        for node in (self.primary, self.second_primary, self.fallback):
            self.service._record_sample(self.service._key(node), 90)
        self.service._geo_cache[self.service._key(self.primary)] = (time.monotonic(), {"ip": "8.8.8.8"})
        self.service._geo_cache[self.service._key(self.second_primary)] = (time.monotonic(), {"ip": "8.8.8.8"})
        self.service._geo_cache[self.service._key(self.fallback)] = (time.monotonic(), {"ip": "1.1.1.1"})

        self.service._reconcile()

        self.assertEqual(self.service.account_route_status("one")["route_mode"], "primary")
        self.assertEqual(self.service.account_route_status("two")["route_mode"], "fallback")

    async def test_primary_then_fallback_then_direct_without_reuse(self):
        self.service._all_accounts = lambda: {"one", "two", "three", "four"}
        self.service._secret["ever_configured"] = True
        self.service._state["health"].clear()
        self.service._record_sample(self.service._key(self.primary), 90)
        self.service._record_sample(self.service._key(self.fallback), 100)

        self.service._reconcile()

        modes = [self.service.account_route_status(name)["route_mode"] for name in ("one", "two", "three", "four")]
        self.assertEqual(modes.count("primary"), 1)
        self.assertEqual(modes.count("fallback"), 1)
        self.assertEqual(modes.count("direct"), 2)

    async def test_geo_worker_count_stays_bounded_for_large_account_list(self):
        release = asyncio.Event()
        started = set()

        async def verify(account):
            started.add(account)
            await release.wait()

        self.service._schedule_geo_for_accounts = AccountRouteService._schedule_geo_for_accounts.__get__(self.service)
        self.service._verify_exit = verify
        self.service._schedule_geo_for_accounts({f"account-{index}" for index in range(1000)})
        await asyncio.sleep(0)
        self.assertEqual(len(self.service._geo_tasks), 6)
        self.assertEqual(len(started), 6)
        release.set()
        await asyncio.gather(*self.service._geo_tasks)
        self.assertFalse(self.service._geo_pending)

    async def test_duplicate_exit_discovered_after_assignment_moves_second_account(self):
        self.service._secret["ever_configured"] = True
        for node in (self.primary, self.second_primary, self.fallback):
            self.service._record_sample(self.service._key(node), 90)
        self.service._reconcile()

        class GeoClient:
            def __init__(self, **_kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *_args):
                pass

            async def get(self, _url):
                return SimpleNamespace(raise_for_status=lambda: None, json=lambda: {
                    "ip": "8.8.8.8", "country": "US", "region": "", "success": True,
                })

        with patch("backend.services.account_routes.httpx.AsyncClient", GeoClient):
            await self.service._verify_exit("one")
            await self.service._verify_exit("two")

        self.assertEqual(self.service.account_route_status("one")["route_mode"], "primary")
        self.assertEqual(self.service.account_route_status("two")["route_mode"], "fallback")

    async def test_stale_geo_result_does_not_restore_old_ip(self):
        self.service._secret["ever_configured"] = True
        p = self.service._key(self.primary)
        self.service._record_sample(p, 100)
        self.service._reconcile()
        self.service._state["assignments"]["one"]["exit_ip"] = "1.2.3.4"
        self.service._assign("one", self.fallback)
        self.assertIsNone(self.service.account_route_status("one")["exit_ip"])
        self.service.delete_account_route("one")
        self.assertNotIn("one", self.service._state["assignments"])

    async def test_direct_geo_request_is_coalesced_and_stale_result_rejected(self):
        self.service._secret["ever_configured"] = True
        self.service._record_sample(self.service._key(self.primary), 90)
        self.service._reconcile()
        self.assertEqual(self.service.account_route_status("two")["route_mode"], "direct")
        entered, release = asyncio.Event(), asyncio.Event()
        calls = 0

        class GeoClient:
            def __init__(self, **_kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *_args):
                pass

            async def get(self, _url):
                nonlocal calls
                calls += 1
                entered.set()
                await release.wait()
                return SimpleNamespace(raise_for_status=lambda: None, json=lambda: {
                    "ip": "8.8.8.8", "country": "US", "region": "California", "success": True,
                })

        with patch("backend.services.account_routes.httpx.AsyncClient", GeoClient):
            first = asyncio.create_task(self.service._verify_exit("one"))
            second = asyncio.create_task(self.service._verify_exit("two"))
            await asyncio.wait_for(entered.wait(), timeout=1)
            self.service._assign("two", self.fallback)
            release.set()
            await asyncio.gather(first, second)

        self.assertEqual(calls, 2)
        self.assertEqual(self.service.account_route_status("one")["exit_ip"], "8.8.8.8")
        self.assertIsNone(self.service.account_route_status("two")["exit_ip"])

    async def test_manual_batch_probes_distinct_routes(self):
        self.service._secret["ever_configured"] = True
        self.service._record_sample(self.service._key(self.primary), 90)
        self.service._reconcile()
        calls = 0

        class GeoClient:
            def __init__(self, **_kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *_args):
                pass

            async def get(self, _url):
                nonlocal calls
                calls += 1
                return SimpleNamespace(raise_for_status=lambda: None, json=lambda: {
                    "ip": "8.8.8.8", "country": "US", "region": "California", "success": True,
                })

        started = time.monotonic()
        with patch("backend.services.account_routes.httpx.AsyncClient", GeoClient):
            one = await self.service.refresh_account_exit("one", fresh_after=started)
            two = await self.service.refresh_account_exit("two", fresh_after=started)
        self.assertEqual(calls, 2)
        self.assertEqual(one["exit_ip"], "8.8.8.8")
        self.assertEqual(two["exit_ip"], "8.8.8.8")

    async def test_failed_refresh_preserves_working_nodes_and_redacts_url(self):
        self.service._secret["ever_configured"] = True
        self.service._secret["primary_url"] = "https://example.org/sub?token=hidden"
        self.service._record_sample(self.service._key(self.primary), 100)
        before = self.service._secret["nodes"]["primary"]
        with patch("backend.services.account_routes.fetch_subscription", side_effect=SubscriptionError("SUBSCRIPTION_FETCH_FAILED")), patch(
            "backend.services.account_routes._probe_socks_port", return_value=None
        ):
            await self.service.refresh_subscriptions()
        self.assertEqual(self.service._secret["nodes"]["primary"], before)
        projection = await self.service.get_subscription_settings()
        self.assertTrue(projection["primary"]["configured"])
        self.assertNotIn("hidden", repr(projection))
        self.assertEqual(projection["primary"]["status"], "SUBSCRIPTION_FETCH_FAILED")

    async def test_unchanged_subscription_refresh_rechecks_nodes_with_recovery_hysteresis(self):
        self.service._secret["ever_configured"] = True
        self.service._secret["primary_url"] = "https://example.org/primary"
        key = self.service._key(self.primary)
        self.service._record_sample(key, None)
        self.service._record_sample(key, None)
        document = b"trojan://secret@example.org:443?security=tls\ntrojan://secret2@example.com:443?security=tls"
        with patch("backend.services.account_routes.fetch_subscription", return_value=document), patch(
            "backend.services.account_routes._probe_socks_port", return_value=90
        ) as probe:
            await self.service.refresh_subscriptions()
            self.assertGreaterEqual(probe.await_count, 2)
            self.assertEqual(self.service._settings_projection()["primary"]["imported_count"], 2)
            self.assertFalse(self.service._state["health"][key]["healthy"])
            await self.service.refresh_subscriptions()
        self.assertTrue(self.service._state["health"][key]["healthy"])
        self.assertGreaterEqual(self.service._settings_projection()["primary"]["usable_count"], 1)

    async def test_geo_falls_back_through_same_route_and_rotates_after_both_providers_fail(self):
        self.service._all_accounts = lambda: {"one"}
        self.service._secret["ever_configured"] = True
        key = self.service._key(self.primary)
        self.service._record_sample(key, 90)
        self.service._record_sample(self.service._key(self.fallback), 90)
        self.service._reconcile()
        requested = []
        proxies = []

        class GeoClient:
            def __init__(self, **kwargs):
                proxies.append(kwargs.get("proxy"))

            async def __aenter__(self):
                return self

            async def __aexit__(self, *_args):
                pass

            async def get(self, url):
                requested.append(url)
                if url.endswith("ipwho.is/"):
                    return SimpleNamespace(raise_for_status=lambda: None, json=lambda: {"success": False})
                return SimpleNamespace(raise_for_status=lambda: None, json=lambda: {
                    "ip": "8.8.8.8", "country_name": "United States", "region": "California",
                })

        with patch("backend.services.account_routes.httpx.AsyncClient", GeoClient):
            result = await self.service.refresh_account_exit("one")
        self.assertEqual(result["exit_ip"], "8.8.8.8")
        self.assertEqual(result["exit_country"], "United States")
        self.assertEqual(result["exit_lookup_status"], "verified")
        self.assertEqual(len(requested), 2)
        self.assertEqual(proxies, ["socks5://127.0.0.1:21001"])

        class FailingGeoClient(GeoClient):
            async def get(self, url):
                return SimpleNamespace(raise_for_status=lambda: None, json=lambda: {"success": False})

        with patch("backend.services.account_routes.httpx.AsyncClient", FailingGeoClient):
            result = await self.service.refresh_account_exit("one")
        self.assertEqual(result["route_mode"], "fallback")
        self.assertEqual(result["exit_lookup_status"], "pending")
        self.assertGreater(self.service._state["health"][key]["geo_failed_until"], time.time())
        self.assertEqual(self.service._settings_projection()["primary"]["usable_count"], 0)

        with patch("backend.services.account_routes.httpx.AsyncClient", GeoClient):
            result = await self.service.refresh_account_exit("one")
        self.assertEqual(result["route_mode"], "fallback")
        self.assertEqual(result["exit_lookup_status"], "verified")

        with patch("backend.services.account_routes.httpx.AsyncClient", FailingGeoClient):
            result = await self.service.refresh_account_exit("one")
            self.assertEqual(result["route_mode"], "direct")
            result = await self.service.refresh_account_exit("one")
        self.assertEqual(result["exit_lookup_status"], "failed")
        self.assertIsNone(result["exit_ip"])

    async def test_missing_country_rotates_node_and_quarantine_prevents_immediate_reuse(self):
        self.service._all_accounts = lambda: {"one"}
        self.service._secret["ever_configured"] = True
        primary_key = self.service._key(self.primary)
        fallback_key = self.service._key(self.fallback)
        for key in (primary_key, fallback_key):
            self.service._record_sample(key, 90)
            self.service._record_sample(key, 90)
        self.service._reconcile()

        class NoCountryGeoClient:
            def __init__(self, **_kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *_args):
                pass

            async def get(self, _url):
                return SimpleNamespace(raise_for_status=lambda: None, json=lambda: {"ip": "8.8.8.8"})

        with patch("backend.services.account_routes.httpx.AsyncClient", NoCountryGeoClient):
            result = await self.service.refresh_account_exit("one")
        self.assertEqual(result["route_mode"], "fallback")
        self.assertEqual(self.service._state["assignments"]["one"]["key"], fallback_key)
        self.service._reconcile()
        self.assertEqual(self.service.account_route_status("one")["route_mode"], "fallback")

    async def test_refresh_accepts_unreachable_primary_and_selects_healthy_fallback(self):
        self.service._secret["ever_configured"] = True
        self.service._secret["primary_url"] = "https://example.org/primary"
        self.service._secret["fallback_url"] = "https://example.org/fallback"
        self.service._secret["nodes"] = {"primary": [], "fallback": []}
        self.runtime.ports.clear()

        async def fetch(url):
            return (b"trojan://secret@example.org:443?security=tls" if url.endswith("primary")
                    else b"trojan://backup@example.net:443?security=tls")

        async def probe(port):
            return None if port == 21000 else 120

        with patch("backend.services.account_routes.fetch_subscription", side_effect=fetch), patch(
            "backend.services.account_routes._probe_socks_port", side_effect=probe
        ):
            await self.service.refresh_subscriptions()

        self.assertEqual(self.service.account_route_status("one")["route_mode"], "fallback")
        self.assertEqual(self.service.account_route_status("two")["route_mode"], "direct")
        self.assertEqual(self.service.resolve_account_route("one")["port"], 21001)

    async def test_refresh_keeps_working_pool_when_new_exits_all_fail(self):
        self.service._secret["ever_configured"] = True
        self.service._secret["primary_url"] = "https://example.org/primary"
        old_key = self.service._key(self.primary)
        self.service._record_sample(old_key, 100)
        old_nodes = list(self.service._secret["nodes"]["primary"])
        old_ports = dict(self.runtime.ports)
        with patch("backend.services.account_routes.fetch_subscription", return_value=b"trojan://new@example.com:443"), patch(
            "backend.services.account_routes._probe_socks_port", return_value=None
        ):
            await self.service.refresh_subscriptions()

        self.assertEqual(self.service._secret["nodes"]["primary"], old_nodes)
        self.assertEqual(self.runtime.ports, old_ports)
        self.assertEqual(self.service.account_route_status("one")["route_mode"], "primary")

    async def test_unhealthy_node_needs_two_good_samples_before_reuse(self):
        self.service._secret["ever_configured"] = True
        key = self.service._key(self.primary)
        self.service._record_sample(key, None)
        self.service._record_sample(key, None)
        self.assertIs(self.service._state["health"][key]["healthy"], False)
        self.service._record_sample(key, 90)
        self.assertIs(self.service._state["health"][key]["healthy"], False)
        self.service._record_sample(key, 90)
        self.assertIs(self.service._state["health"][key]["healthy"], True)

    async def test_redirect_cannot_pivot_to_private_address(self):
        with patch("backend.services.subscription_import._validate_public_url", side_effect=[[(2, "93.184.215.14")], SubscriptionError("SUBSCRIPTION_URL_FORBIDDEN")]), patch("backend.services.subscription_import._request_https", return_value=(302, {"location": "https://127.0.0.1/private"}, b"")):
            with self.assertRaisesRegex(SubscriptionError, "SUBSCRIPTION_URL_FORBIDDEN"):
                await fetch_subscription("https://example.org/sub?token=hidden")


class XrayRuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def test_rejected_candidate_keeps_previous_generation(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = XrayRuntime(Path(directory), binary="fake-xray")
            one = parse_subscription(b"trojan://one@example.org:443", "primary").nodes[0]
            two = parse_subscription(b"trojan://two@example.net:443", "fallback").nodes[0]
            with patch.object(runtime, "_validate", new=AsyncMock()), patch.object(runtime, "_ready", new=AsyncMock()), patch("backend.services.xray_runtime.asyncio.create_subprocess_exec", side_effect=[_Process(), _Process()]):
                await runtime.replace([one])
                first = runtime.active

                async def reject(_ports):
                    return False

                with self.assertRaisesRegex(XrayRuntimeError, "XRAY_CANDIDATE_UNHEALTHY"):
                    await runtime.replace([two], accept=reject)
                self.assertIs(runtime.active, first)
                self.assertIsNotNone(runtime.port_for(runtime.key(one)))
                await runtime.shutdown()


if __name__ == "__main__":
    unittest.main()
