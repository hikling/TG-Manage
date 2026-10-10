<p align="center"><img src="docs/public/logo.svg" width="80" height="80" alt="TG Manage logo"></p>
<h1 align="center">🚀 TG Manage</h1>
<p align="center">A focused Telegram multi-account dashboard with an isolated TeleBox runtime.</p>
<p align="center"><a href="README.md">简体中文</a> · <a href="README_EN.md"><strong>English</strong></a></p>
<p align="center"><a href="#features">✨ Features</a> · <a href="#quick-start">🚀 Quick start</a> · <a href="#guides">📚 Guides</a> · <a href="#reference">🧰 Reference</a></p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-BSD--3--Clause-0b7285?style=flat-square" alt="BSD 3-Clause license"></a>
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/Python-3.10%E2%80%933.13-3776AB?style=flat-square&amp;logo=python&amp;logoColor=white" alt="Python 3.10 to 3.13"></a>
  <a href="https://fastapi.tiangolo.com/"><img src="https://img.shields.io/badge/FastAPI-0.109%2B-009688?style=flat-square&amp;logo=fastapi&amp;logoColor=white" alt="FastAPI 0.109 or later"></a>
  <a href="https://vuejs.org/"><img src="https://img.shields.io/badge/Vue.js-3.5-42B883?style=flat-square&amp;logo=vuedotjs&amp;logoColor=white" alt="Vue.js 3.5"></a>
  <a href="https://www.typescriptlang.org/"><img src="https://img.shields.io/badge/TypeScript-6%20%7C%207-3178C6?style=flat-square&amp;logo=typescript&amp;logoColor=white" alt="TypeScript 6 and 7"></a>
  <a href="https://nodejs.org/"><img src="https://img.shields.io/badge/Node.js-22%20%7C%2024-339933?style=flat-square&amp;logo=nodedotjs&amp;logoColor=white" alt="Node.js 22 and 24"></a>
  <a href="https://github.com/TeleBoxOrg/TeleBox"><img src="https://img.shields.io/badge/TeleBox-0.2.9-6f42c1?style=flat-square" alt="TeleBox 0.2.9"></a>
</p>

> Based on [Silentely/TG-SignPulse](https://github.com/Silentely/TG-SignPulse) and integrating [TeleBoxOrg/TeleBox](https://github.com/TeleBoxOrg/TeleBox). The current project is [hikling/TG-Manage](https://github.com/hikling/TG-Manage); build from this repository because upstream images do not include these UI and TeleBox changes.

<a id="features"></a>
## ✨ Features

<table>
  <tr>
    <td valign="top" width="50%">
      <h3>👥 Account management</h3>
      <p>Sign in by code or QR, check status, refresh avatars on demand, and set per-account proxies. Single and batch checks share a 45-second interval after each successful account check.</p>
    </td>
    <td valign="top" width="50%">
      <h3>💬 Chat center</h3>
      <p>Browse group conversations by account, search, send attachments, reply, edit, and delete messages. Chat can be switched on independently.</p>
    </td>
  </tr>
  <tr>
    <td valign="top" width="50%">
      <h3>🤖 Private bot</h3>
      <p>The configured private target ID may use <code>/code account-name</code> to query a code from the last five minutes of <code>777000</code>, or <code>/me</code> to list local account names and remarks. Both commands share a 45-second interval; idle operation never scans account messages.</p>
    </td>
    <td valign="top" width="50%">
      <h3>🎨 Dashboard and appearance</h3>
      <p>The dashboard provides the cover, Manage accounts, and Refresh entry points. Accent colors and custom covers are saved on the server, with positioning, reset, and a 1 MiB upload limit.</p>
    </td>
  </tr>
  <tr>
    <td valign="top" width="50%">
      <h3>🔌 Integrated TeleBox</h3>
      <p>Each enabled account gets a separate Telegram session and runtime directory, with status and logs on its account card. Start, stop, or log out from the same card; the pinned upstream revision is recorded in <a href="telebox/UPSTREAM.json"><code>telebox/UPSTREAM.json</code></a>.</p>
    </td>
    <td valign="top" width="50%">
      <h3>🔐 Separate session boundary</h3>
      <p>Logging out of TeleBox clears only its separate authorization, not the main account session. Keep the two session stores separate.</p>
    </td>
  </tr>
</table>


<a id="quick-start"></a>
## 🚀 Quick start

Small deployments support a minimum of 1 vCPU / 1 GiB RAM, with no artificial upper limit. Scale according to account count and actual workload. Install Docker Engine, Docker Compose v2, and Git. Ensure the server can reach Telegram and download build dependencies, then run:

```bash
git clone https://github.com/hikling/TG-Manage.git
cd TG-Manage
bash scripts/install.sh
```

The installer builds from this repository, starts the service, and prints a one-time setup token. Open `http://YOUR_SERVER_IP:8080`, enter the token, and choose an admin password of at least 12 characters. Configure an [HTTPS reverse proxy](docs/deploy/nginx.md) before exposing the service publicly.

> **⚠️ Upgrading an existing installation? Do not reinitialize or delete its data.** Run `bash scripts/update.sh` in the existing checkout. Keep the entire `data/` directory, including the hidden `data/.app_secret_key`, database, account sessions, and TeleBox data. See “Data, upgrades, and backups” below.

<a id="first-use"></a>
## 🧭 First use

1. **🔐 Set up the admin:** Enter the one-time setup token; existing installations keep their current login. Enable panel TOTP if possible.
2. **➕ Add an account:** Choose code or QR login in Account Management. An ordinary account may omit API ID/Hash; supply account-specific credentials when enabling TeleBox, and complete 2FA if prompted.
3. **🗂️ Work on demand:** Check an account to refresh its status and avatar, manage its separate TeleBox process, and enable chat from inside the Chat Center when needed.

TeleBox manages its own commands and plugins. System plugins are bundled; community plugins are published in [TeleBox-Plugins](https://github.com/TeleBoxOrg/TeleBox-Plugins). See the bundled [`telebox/README.md`](telebox/README.md) for details.

<a id="guides"></a>
## 📚 Guides

- **📦 [Docker deployment and upgrades](docs/deploy/docker.md)** — Installation, backups, rollback, and build troubleshooting.
- **🧭 [Quick-start guide](docs/guide/quick-start.md)** — Initial setup and account onboarding.
- **⚙️ [Configuration reference](docs/reference/configuration.md)** — Environment variables and data paths.
- **🛠️ [Local development](docs/reference/development.md)** — Source setup and development commands.

<a id="reference"></a>
## 🧰 Reference

Expand a section only when you need its details.

<a id="environment"></a>
<details>
<summary><strong>⚙️ Environment variables</strong></summary>

| Variable | Purpose |
| --- | --- |
| `TG_MANAGE_TG_API_ID/HASH` | Optional private server credentials for ordinary accounts; use account-specific credentials for TeleBox. |
| `SIGNPULSE_TG_API_ID/HASH`, `TG_API_ID/HASH` | Legacy aliases still read during upgrades. |
| `APP_SECRET_KEY` | Authentication and credential encryption key; persisted in `data/.app_secret_key` and essential to backups. |
| `APP_DATA_DIR` | Database, sessions, logs, and TeleBox data directory; Compose uses `/data`. |
| `TG_PROXY` | Global Telegram proxy; per-account proxies can also be set in the UI. |
| `APP_DATABASE_URL` | Override the default SQLite connection. |
| `TG_GLOBAL_CONCURRENCY` | Limit for concurrent Telegram operations, not the total number of signed-in accounts. |
| `TELEBOX_NODE` | Select the Node 24 executable for local TeleBox development. |

See [`backend/core/config.py`](backend/core/config.py) and the [configuration reference](docs/reference/configuration.md) for all options. Never commit secrets, sessions, bot tokens, or backups.

</details>

<a id="data-upgrade-backup"></a>
<details>
<summary><strong>💾 Data, upgrades, and backups</strong></summary>

Compose bind-mounts host `./data` to container `/data`. This includes the database, account sessions, settings, logs, per-account TeleBox directories, dashboard cover, and `data/.app_secret_key`. Older installations may store the cover in `data/.signer/appearance/`. **Preserve the entire directory, including hidden files.** Without the original secret, encrypted account credentials and bot tokens cannot be decrypted.

From the existing checkout, run:

```bash
bash scripts/update.sh
```

The script uses `scripts/backup.sh` to archive the full data directory under `backups/`, runs `git pull --ff-only`, then rebuilds and starts the service. It does not remove older backups. If you changed the data directory, verify that `APP_DATA_DIR` and the Compose mount point to the same location first. Back up external PostgreSQL databases separately. See the [Docker guide](docs/deploy/docker.md#无损升级与回退) for manual steps and rollback.

To restore, stop the service, restore the full data directory, then restart and check accounts, sessions, and settings. Backups contain sensitive credentials; never publish them. TeleBox core code can be updated while user plugins, configuration, and separate sessions remain in place.

</details>

<a id="verification-limitations"></a>
<details>
<summary><strong>🧪 Verification and known limitations</strong></summary>

Local checks:

```bash
python3 -m ruff check backend tg_manage tests
python3 -m pytest -q
cd frontend && npm run typecheck && npm test && npm run build
cd ../telebox && npx tsc --noEmit
```

Real-account code and QR login, independent TeleBox authorization, Bot API access, remote plugin installation, and a complete Docker build still need verification in your deployment environment. Former scheduler and monitor data may remain on disk, but the removed actions no longer run. Allow for the additional process and session overhead of each active TeleBox account.

</details>

<a id="project-development"></a>
<details>
<summary><strong>🗂️ Project structure and development</strong></summary>

```text
TG-Manage/
├── backend/       FastAPI routes and account/message services
├── frontend/      Vue 3 management UI
├── tg_manage/     Telegram client and session utilities
├── telebox/       Upstream TeleBox source and integration adapter
├── docs/          User, deployment, and operations guides
└── tests/         Backend tests
```

Source development needs Python 3.10–3.13, Node 22.23.1 for the frontend, and Node 24 for TeleBox. See [`Dockerfile`](Dockerfile) for native module dependencies. Local AI workflows, skills, and task notes are not published with the source. TeleBox keeps its upstream [LGPL-2.1-only license](telebox/LICENSE); the rest of this project uses the root [`LICENSE`](LICENSE).

</details>
