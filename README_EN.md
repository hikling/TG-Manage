# TG Manage — Telegram account management with integrated TeleBox

TG Manage is based on [Silentely/TG-SignPulse](https://github.com/Silentely/TG-SignPulse); its current source is [hikling/TG-SignPulse-Private](https://github.com/hikling/TG-SignPulse-Private). Build from this repository. For requirements, configuration, development, and verification details, see the [Chinese README](README.md).

## Changes

| Area | Current implementation |
| --- | --- |
| UI | Screenshot inspired sidebar, account cards, responsive layouts, light and dark themes. |
| Chats | Sidebar entry always visible. Its own switch defaults off, showing only official Telegram verification messages; when on, group dialogs, messages and avatars are displayed, with a 5 MB cache limit. |
| Administration | Account proxies stay in account details. Bot registration, profile, commands, and messaging are under System Settings. |
| TeleBox | Complete upstream 0.2.9 source pinned to the commit in [`telebox/UPSTREAM.json`](telebox/UPSTREAM.json); separate worker, data directory, status, logs and plugin controls per account. |
| Migration | The former Python task scheduler, actions and keyword monitor have been removed from the panel. TeleBox tasks select loaded commands per account; legacy task data is not executed or migrated automatically. |
| Development | Trellis specifications and task notes under [`.trellis/`](.trellis/), with Codex skills/hooks. |

## Requirements

- Docker Engine 24+ and Docker Compose v2, or a local Linux development environment.
- A Telegram account. TeleBox-enabled accounts enter their own API ID / API Hash from `my.telegram.org` at login. Ordinary accounts can log in without entering these values; the server can optionally supply private `TG_MANAGE_TG_API_ID/HASH` in `.env`. The older `SIGNPULSE_TG_API_*` and `TG_API_*` pairs remain readable for upgrades.
- The Compose file allocates a 2 GiB container limit and 2 CPUs; building native TeleBox modules needs additional resources. Each running TeleBox account has its own Node process.
- Source development: Python >=3.10,<3.14, Node 22.23.1 for the Vue frontend, **separate Node 24.x** for TeleBox, and native Cairo/Pango/C++ dependencies (see [`Dockerfile`](Dockerfile)). The Docker runtime uses Python 3.11.

## Deploy from source

```bash
git clone https://github.com/hikling/TG-SignPulse-Private.git && cd TG-SignPulse-Private && bash scripts/install.sh
```

The private repository requires GitHub access. Docker Compose builds from source and bind mounts `./data` at `/data`. The app secret is generated in `data/.app_secret_key`; the script prints a one-time setup token to set the admin password. For many accounts, set your own `TG_MANAGE_TG_API_ID/HASH` in a private server `.env`.

Open `http://YOUR_SERVER_IP:8080`, enter the one-time setup token and choose an admin password. When adding an account, opt into TeleBox and enter that account's API ID/Hash, or leave it off for ordinary login. Verify by code or QR; TeleBox starts automatically for opted-in accounts. Supply Telegram 2FA on the account card if requested.

## Upgrade without losing data

From the existing repository directory, run `bash scripts/update.sh`. It checks the data directory, archives all of it to `backups/` without deleting older archives, pulls this repository with `git pull --ff-only`, then rebuilds and starts via `scripts/install.sh`. Preserve the `./data:/data` bind mount and the full `data/` directory, especially `.app_secret_key`, `sessions/`, and `telebox/`. For manual steps, rollback, and verification, see the [Docker guide](docs/deploy/docker.md#无损升级与回退). An external PostgreSQL database needs its own backup.

The bundled TeleBox runtime contains its system plugins and the native Panel. Community plugins live in the separate [TeleBox-Plugins](https://github.com/TeleBoxOrg/TeleBox-Plugins) repository; use `.tpm install <name>` and `.tpm update` from Telegram Saved Messages. On upgrade, the core code is refreshed for existing accounts while their plugins and account data are preserved. Optional plugin settings can go in an account-local `data/telebox/<SHA-256 account name>/.env` (mode 600). Failed plugin actions are shown in the account's TeleBox logs.

The [Docker guide](docs/deploy/docker.md) and [quick start](docs/guide/quick-start.md) cover deployment. Verify Telegram authorization, Bot API access, TeleBox plugins, and the full Docker build in your own environment.

TeleBox retains its upstream LGPL-2.1-only [license](telebox/LICENSE); the rest of this project is covered by the root [license](LICENSE).
