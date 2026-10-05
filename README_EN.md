# TG-SignPulse — Telegram management panel with integrated TeleBox

This is a modified version of [Silentely/TG-SignPulse](https://github.com/Silentely/TG-SignPulse). **Build from this repository's source.** The upstream public GHCR image does not include the new panel, chat center, or TeleBox integration. For the full change log, requirements, environment variables, local development commands, backups, and verification limits, see the [Chinese README](README.md).

## Changes

| Area | Current implementation |
| --- | --- |
| UI | Screenshot inspired sidebar, account cards, responsive layouts, light and dark themes. |
| Chats | Sidebar entry always visible. Its own switch defaults off, showing only official Telegram verification messages; when on, group dialogs, messages and avatars are displayed, with a 5 MB cache limit. |
| Workbench | Immediate sends and daily scheduled messages, with manual target entry while chat center is off. |
| Administration | Account proxies stay in account details; the separate proxy management card is removed. Bot API registration/profile/commands/messages remains. |
| TeleBox | Complete upstream 0.2.9 source pinned to the commit in [`telebox/UPSTREAM.json`](telebox/UPSTREAM.json); separate worker, data directory, status, logs and plugin controls per account. |
| Migration | The former Python task scheduler, actions and keyword monitor have been removed from the panel. TeleBox tasks select loaded commands per account; legacy task data is not executed or migrated automatically. |
| Development | Trellis specifications and task notes under [`.trellis/`](.trellis/), with Codex skills/hooks. |

## Requirements

- Docker Engine 24+ and Docker Compose v2, or a local Linux development environment.
- A Telegram account. TeleBox-enabled accounts enter their own API ID / API Hash from `my.telegram.org` at login. Ordinary accounts can log in without entering these values; the server can optionally supply private `SIGNPULSE_TG_API_ID/HASH` in `.env`.
- The Compose file allocates a 2 GiB container limit and 2 CPUs; building native TeleBox modules needs additional resources. Each running TeleBox account has its own Node process.
- Source development: Python >=3.10,<3.14, Node 22.23.1 for the Vue frontend, **separate Node 24.x** for TeleBox, and native Cairo/Pango/C++ dependencies (see [`Dockerfile`](Dockerfile)). The Docker runtime uses Python 3.11.

## Deploy from source

```bash
git clone https://github.com/hikling/TG-SignPulse-Private.git && cd TG-SignPulse-Private && bash scripts/install.sh
```

The private repository requires GitHub access. Docker Compose builds from source. The app secret is generated and persisted in `data/.app_secret_key`; the script prints a one-time setup token to set the admin password in the browser. Ordinary login uses the old built-in public Telegram application credentials when no private or legacy credentials are configured. For many accounts, consider setting your own `SIGNPULSE_TG_API_ID/HASH` in a private server `.env` to avoid sharing that application's limits.

Open `http://YOUR_SERVER_IP:8080`, enter the one-time setup token and choose an admin password. When adding an account, opt into TeleBox and enter that account's API ID/Hash, or leave it off for ordinary login without filling these fields. Verify by code or QR; TeleBox starts automatically for opted-in accounts. Supply Telegram 2FA in the extension page if requested. Test sends and changes with your own test chat first.

## Data and validation

`./data` is mounted at `/data` and holds SQLite, Telegram sessions, tasks, logs, and per-account TeleBox data. Back up all of `data/`, including `.app_secret_key` before rebuilding or migrating. Rebuild with `docker compose up -d --build`; do not pull the upstream image over this version.

The bundled TeleBox runtime contains its system plugins and the native Panel. Community plugins live in the separate [TeleBox-Plugins](https://github.com/TeleBoxOrg/TeleBox-Plugins) repository; use `.tpm install <name>` and `.tpm update` from Telegram Saved Messages. On upgrade, the core code is refreshed for existing accounts while their plugins and account data are preserved. Optional plugin settings can go in an account-local `data/telebox/<SHA-256 account name>/.env` (mode 600). Failed plugin actions are shown in the account's TeleBox logs.

Frontend typecheck/build/tests, targeted backend tests and TeleBox TypeScript checks passed during implementation. Real Telegram authorization, Bot API access, TPM remote installation and a full Docker build still need verification in the target environment. The [Docker guide](docs/deploy/docker.md) and [quick start](docs/guide/quick-start.md) cover this fork.

TeleBox retains its upstream LGPL-2.1-only [license](telebox/LICENSE); the rest of this project is covered by the root [license](LICENSE).
