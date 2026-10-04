"""Sample a running 2 CPU / 2 GiB Compose container during account capacity tests.

Run through stdin so the production image need not contain this file:
  docker compose exec -T app python -u - --phase off --accounts 5 \
    --expected-workers 0 < tools/capacity_probe.py | tee off-5.jsonl

Only aggregate resource counters are emitted. This does not log in accounts,
contact Telegram, change TeleBox state, or print session data.
"""

from __future__ import annotations

import argparse
import json
import math
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

CGROUP = Path("/sys/fs/cgroup")
MIB = 1024 * 1024


def number(path: str) -> int:
    return int((CGROUP / path).read_text().strip())


def fields(path: str) -> dict[str, int]:
    return {
        key: int(value)
        for key, value in (line.split() for line in (CGROUP / path).read_text().splitlines())
    }


def worker_count() -> int:
    count = 0
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        try:
            command = (entry / "cmdline").read_bytes().replace(b"\x00", b" ")
        except (OSError, ProcessLookupError):
            continue
        if b"panel/worker.ts" in command and b"node" in command:
            count += 1
    return count


def ready(port: int) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/readyz", timeout=3) as response:
            return response.status == 200
    except (OSError, urllib.error.URLError):
        return False


def snapshot(port: int) -> dict:
    memory = number("memory.current")
    memory_stat = fields("memory.stat")
    return {
        "at": datetime.now(timezone.utc).isoformat(),
        "memory_mib": round(memory / MIB, 1),
        "working_set_mib": round(max(0, memory - memory_stat.get("inactive_file", 0)) / MIB, 1),
        "anon_mib": round(memory_stat.get("anon", 0) / MIB, 1),
        "cpu_usage_usec": fields("cpu.stat")["usage_usec"],
        "oom_kill": fields("memory.events").get("oom_kill", 0),
        "pids": number("pids.current"),
        "telebox_workers": worker_count(),
        "ready": ready(port),
    }


def percentile(values: list[float], fraction: float) -> float:
    sorted_values = sorted(values)
    return sorted_values[max(0, math.ceil(len(sorted_values) * fraction) - 1)]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=("off", "on"), required=True)
    parser.add_argument("--accounts", type=int, required=True, help="Real, authorized accounts logged into the panel")
    parser.add_argument("--expected-workers", type=int, required=True, help="TeleBox workers expected to be running")
    parser.add_argument("--duration", type=int, default=300, help="Measured seconds after warmup")
    parser.add_argument("--warmup", type=int, default=60)
    parser.add_argument("--interval", type=float, default=5.0)
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--allow-other-limit", action="store_true", help="For local dry runs only")
    args = parser.parse_args()
    if args.accounts < 0 or args.expected_workers < 0 or args.duration < 2 or args.warmup < 0 or args.interval <= 0:
        parser.error("counts and warmup must be nonnegative; duration >= 2; interval > 0")
    if args.phase == "off" and args.expected_workers != 0:
        parser.error("off phase requires --expected-workers 0")
    if args.phase == "on" and args.expected_workers != args.accounts:
        parser.error("on phase requires one TeleBox worker per account")

    try:
        memory_limit = number("memory.max")
        quota_text, period_text = (CGROUP / "cpu.max").read_text().split()
        cpu_limit = int(quota_text) / int(period_text)
    except (FileNotFoundError, ValueError) as exc:
        parser.error(f"cgroup v2 memory.max/cpu.max unavailable: {exc}")
    if not args.allow_other_limit and (not 1900 <= memory_limit / MIB <= 2150 or not 1.95 <= cpu_limit <= 2.05):
        parser.error(f"expected 2 CPU / 2 GiB cgroup; observed {cpu_limit:g} CPU / {memory_limit / MIB:.0f} MiB")

    print(json.dumps({"type": "config", "phase": args.phase, "accounts": args.accounts,
                      "expected_workers": args.expected_workers, "duration_s": args.duration,
                      "memory_limit_mib": round(memory_limit / MIB), "cpu_limit": cpu_limit}), flush=True)
    if args.warmup:
        time.sleep(args.warmup)
    deadline = time.monotonic() + args.duration
    previous_at = time.monotonic()
    previous = snapshot(args.port)
    previous_initial_oom = previous["oom_kill"]
    samples: list[dict] = []
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        time.sleep(min(args.interval, remaining))
        now = time.monotonic()
        current = snapshot(args.port)
        current["cpu_cores"] = round(max(0, current["cpu_usage_usec"] - previous["cpu_usage_usec"])
                                     / 1_000_000 / (now - previous_at), 3)
        current["type"] = "sample"
        current["phase"] = args.phase
        current["accounts"] = args.accounts
        samples.append(current)
        print(json.dumps(current, ensure_ascii=False), flush=True)
        previous, previous_at = current, now

    if not samples:
        parser.error("no samples collected; reduce --interval or extend --duration")
    summary = {
        "type": "summary", "phase": args.phase, "accounts": args.accounts,
        "expected_workers": args.expected_workers, "samples": len(samples),
        "memory_peak_mib": max(sample["memory_mib"] for sample in samples),
        "working_set_peak_mib": max(sample["working_set_mib"] for sample in samples),
        "anon_peak_mib": max(sample["anon_mib"] for sample in samples),
        "cpu_p95_cores": round(percentile([sample["cpu_cores"] for sample in samples], .95), 3),
        "oom_kill_delta": samples[-1]["oom_kill"] - previous_initial_oom,
        "ready_all": all(sample["ready"] for sample in samples),
        "workers_all_expected": all(sample["telebox_workers"] == args.expected_workers for sample in samples),
        "memory_limit_mib": round(memory_limit / MIB),
        "cpu_limit": cpu_limit,
    }
    print(json.dumps(summary, ensure_ascii=False), flush=True)
    return 0 if summary["ready_all"] and summary["workers_all_expected"] and summary["oom_kill_delta"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
