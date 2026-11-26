<p align="right">
  <a href="README.md">简体中文</a> | <strong>English</strong>
</p>

<h1 align="center">TG Manage</h1>

<p align="center">
  <em>Self-hosted Telegram Multi-Account Operations, Dedicated Xray Routing &amp; TeleBox Panel</em>
</p>

<p align="center"><a href="#whats-new">🆕 v2.6.0</a> · <a href="#features">✨ Features</a> · <a href="#quick-start">🚀 Quick start</a> · <a href="#midnight-report">📨 Daily report</a> · <a href="#bot-web">🤖 Open Web</a> · <a href="#guides">📚 Guides</a> · <a href="#reference">🧰 Reference</a></p>

<p align="center">
  <img src="https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=white" alt="Docker Compose">
  <img src="https://img.shields.io/badge/Python-3.10--3.13-3776AB?logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/Vue-3%20%2B%20FastAPI-42B883?logo=vuedotjs&logoColor=white" alt="Vue 3 and FastAPI">
  <img src="https://img.shields.io/badge/Release-v2.6.0-16a34a" alt="Release v2.6.0">
  <img src="https://img.shields.io/badge/License-BSD--3--Clause-0f766e" alt="License">
</p>

---

**TG Manage** is a lightweight self-hosted web panel built with FastAPI and Vue 3 for managing multiple Telegram accounts, dedicated Xray proxy routes, an on-demand Chat Center (with built-in 777000 verification inbox), per-account TeleBox runtimes, and encrypted login backups.

<a id="whats-new"></a>
## 🆕 What's new in v2.6.0

1. **Showcase Account Card UI & Customizable Cover Height**:
   - **Card-first account layout**: Redesigned account cards with 20 cycling multi-stop gradient headers, larger centered avatars straddling the divider, account names above and remarks below the line, streamlined IP location & route source rows, and direct **Start/Stop TeleBox** and **Check Status** footer buttons (including inline 2FA prompt support).
   - **Theme & Dashboard Cover Control**: Added customizable **dashboard cover height** slider (`120px–420px`) alongside custom accent presets, image upload/focal positioning, and light/dark contrast refinement.
   - **Dedicated Sidebar Chat Center**: Consolidated Chat Center navigation in the sidebar with searchable account switching and instant 777000 official login-code extraction even when full chat is disabled.
2. **Full-Repository Security Hardening & Logic Fixes**:
   - **Auth, SSRF & Boundary Protection**: Blocked short-lived Telegram WebApp tokens from modifying admin password, username, or 2FA settings; added timing-safe bcrypt verification on unknown usernames; enforced bcrypt 72-byte UTF-8 password limits; blocked NAT64 / IPv4-mapped / internal host SSRF vectors in subscription node imports; disabled credentials with wildcard CORS; tightened TOTP replay window cleanup & rate-limiter expiration memory bounds; and guarded Docker entrypoint & TeleBox worker writes against symlink/partial-config hazards.
   - **Concurrency & UI Reliability**: Added thread-safe locking around `accounts.json` mutations and fixed rename conflict ordering plus avatar/marker migration; corrected naive local timestamp handling in Chat Center; fixed multi-layer `Modal` Escape stack, `AddAccountModal` async session races, `useToast` pause/resume remaining-time calculation, and `encodeURIComponent` account paths.
3. **Dead Code & Dependency Cleanup**:
   - Removed legacy task schemas, unused Pydantic v2 compatibility shims, orphaned Vue components (`DatePicker`, `MultiSelect`, `SettingsFieldHint`), unused CSS rules/locale keys, and unused dependencies from [pyproject.toml](pyproject.toml).

See the **[v2.6.0 release notes](docs/releases/v2.6.0.md)** and [CHANGELOG.md](CHANGELOG.md). Previous routing and daily-report behavior are covered in [v2.5.1](docs/releases/v2.5.1.md) and [v2.5.0](docs/releases/v2.5.0.md).

<a id="features"></a>
## ✨ Features

- **Showcase Account Cards & Encrypted Backups**: Phone/code and QR login, encrypted `.tglogin` export/import, cached avatars, active device inspection and termination.
- **Exclusive Primary & Fallback Xray Routing**: Import primary and fallback subscriptions with one dedicated local SOCKS5 port per account; two failures switch to fallback, two healthy probes recover primary, and excess accounts fall back cleanly to direct routing.
- **Per-Account TeleBox Isolation**: Dedicated process, working directory, encrypted session, and stdin/stdout JSON IPC control directly from each account card without SQLite session lock contention.
- **Chat Center & 777000 Inbox**: Unified sidebar entry featuring account switching and a zero-config 777000 verification-code reader; optional full chat supports searching dialogs, sending/editing/deleting messages, and media transfers up to 20 MB.
- **Midnight Combined Report & Private Bot Entry**: Daily `00:00` health refresh, automatic recovery probing, and one consolidated notification combining account/777000 status with Xray node metrics, plus `/me`, `/code`, and WebApp panel access.

<a id="quick-start"></a>
## 🚀 Quick start

Requires **Docker Engine 24+**, **Docker Compose v2**, **Git**, and network access to Telegram.

### Option 1: Install script (recommended)

```bash
curl -fsSL https://raw.githubusercontent.com/hikling/TG-Manage/main/scripts/install.sh -o install.sh
bash install.sh
```

Read the first-run setup token from the data directory to set the initial admin password in the browser:

```bash
cat ./data/.admin_setup_token
```

### Option 2: Manual Docker Compose

```bash
git clone https://github.com/hikling/TG-Manage.git
cd TG-Manage
APP_SECRET_KEY=$(openssl rand -hex 32)
echo "APP_SECRET_KEY=${APP_SECRET_KEY}" > .env
mkdir -p data/.tg_manage data/sessions data/logs data/plugins
docker compose up -d --build
```

### Update & Backup

To pull the latest `main` changes on your deployment host and rebuild:

```bash
cd /root/TG-SignPulse-Private # or your deployment directory
bash scripts/update.sh
```

See [Docker upgrade guide](docs/deploy/docker.md), [Nginx example](docs/deploy/nginx.md), and [backup script](scripts/backup.sh).

<a id="midnight-report"></a>
## 📨 Midnight combined report

When a private Telegram Bot is configured, the scheduler triggers every day at `00:00` (panel timezone) to refresh subscriptions, re-probe failed accounts, attempt healthy fallback node rotation when appropriate, and send one consolidated summary message containing account/official-message status followed by Xray node health metrics.

<a id="bot-web"></a>
## 🤖 Open Web from your private Bot

With a `Bot Token` and single numeric target user ID configured in **Settings → Telegram Bot Notifications**:

1. The bot registers an **Open Web** menu button pointing to your HTTPS public panel URL.
2. Telegram `initData` HMAC-SHA256 signatures are verified server-side and restricted strictly to the configured target user ID.
3. Short-lived WebApp tokens can operate routine monitoring and views while remaining blocked from changing admin credentials or 2FA secrets.

See [Device & WebApp reference](docs/reference/device-management.md) for deployment details.

<a id="guides"></a>
## 📚 Guides

- **[v2.6.0 release notes](docs/releases/v2.6.0.md)** — UI cards redesign, security hardening, and dead code cleanup.
- **[v2.5.1 release notes](docs/releases/v2.5.1.md)** — Midnight combined report, Bot Web entry, and version checks (Chinese).
- **[v2.5.0 release guide](docs/releases/v2.5.0.md)** — Subscription routing, timing rules, and login migration (Chinese).
- **[Quick start](docs/guide/quick-start.md)** · **[Accounts & TeleBox](docs/guide/accounts.md)** · **[Login backup](docs/guide/account-login-backup.md)**
- **[Ops reference](docs/reference/ops.md)** · **[Configuration](docs/reference/configuration.md)** · **[Features](docs/features.md)** · **[FAQ](docs/faq.md)**

<a id="reference"></a>
## 🧰 Technical reference

- **Backend**: Python 3.10–3.13 · FastAPI · SQLAlchemy · APScheduler · Kurigram · Xray-core
- **Frontend**: Vue 3 · TypeScript · Pinia · Vite · Tailwind CSS · Vue I18n (`zh-CN` / `en-US`)
- **Verification**:

```bash
# Backend test suite (Python 3.10 / 3.11)
pytest tests -q

# Frontend typecheck, unit tests & production build
cd frontend && npm run typecheck && npm run test && npm run build
```

<details>
<summary>📂 Repository layout</summary>

```text
TG-Manage/
├── backend/              # FastAPI routes, auth/rate limiting, Xray routing, TeleBox supervisor, scheduler
├── tg_manage/            # Shared Pyrogram client pool, encryption, and log redaction utilities
├── frontend/             # Vue 3 + Vite + TypeScript web panel & Vitest suite
├── telebox/              # Isolated TeleBox TypeScript worker runtime adapter
├── docker/               # Container entrypoint & Nginx reverse-proxy example
├── scripts/              # install.sh / update.sh / backup.sh
├── docs/                 # VitePress documentation & release notes
└── tests/                # pytest backend test suite
```

</details>

## 📄 License

Released under the [BSD-3-Clause](LICENSE) License.
