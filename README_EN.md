<p align="center"><img src="docs/public/logo.svg" width="80" height="80" alt="TG Manage logo"></p>
<h1 align="center">🚀 TG Manage</h1>
<p align="center">A focused Telegram multi-account dashboard with an isolated TeleBox runtime.</p>
<p align="center"><a href="README.md">简体中文</a> · <a href="README_EN.md"><strong>English</strong></a></p>
<p align="center"><a href="#whats-new">🆕 v2.5.1</a> · <a href="#features">✨ Features</a> · <a href="#quick-start">🚀 Quick start</a> · <a href="#midnight-report">📨 Daily report</a> · <a href="#bot-web">🤖 Open Web</a> · <a href="#guides">📚 Guides</a> · <a href="#reference">🧰 Reference</a></p>


> Based on [Silentely/TG-SignPulse](https://github.com/Silentely/TG-SignPulse) and integrating [TeleBoxOrg/TeleBox](https://github.com/TeleBoxOrg/TeleBox). The current project is [hikling/TG-Manage](https://github.com/hikling/TG-Manage); build from this repository because upstream images do not include these UI and TeleBox changes.

<a id="whats-new"></a>
## 🆕 What's new in v2.5.1

- **🌙 Midnight subscription refresh:** Fetch the primary and fallback subscriptions at 00:00 in the panel time zone. Report usable nodes and a combined unusable/unsupported count for each source. Regular hourly refreshes and health checks continue.
- **🔄 Abnormal account recovery:** Recheck an abnormal account. If a timeout or connection error persists, try an unassigned usable node with a different exit IP and check again. The report includes the action and final result.
- **📨 One combined summary:** Account status and the preceding 24 hours of official messages appear above subscription node counts. Both headings are bold. A long summary may be split; official message details can still arrive separately.
- **🤖 Private “打开WEB” menu:** The same notification bot sets a Web entry for the configured private target ID. Telegram-signed data authorizes only that user; other IDs cannot obtain dashboard access or use private code commands.
- **🛠️ Reliable startup:** Fixed a restart loop caused by permission changes failing on some restricted data volumes.

See the **[v2.5.1 release notes](docs/releases/v2.5.1.md)**. The [v2.5.0 guide](docs/releases/v2.5.0.md) covers route assignment, login migration, and manual-check scope.

<a id="features"></a>
## ✨ Core features

<table>
  <tr>
    <td valign="top" width="50%">
      <h3>👥 Multi-account management</h3>
      <p>Sign in by code, QR, or 2FA, and migrate main-account authorization with an encrypted <code>.tglogin</code> file.</p>
    </td>
    <td valign="top" width="50%">
      <h3>🌐 Per-account Xray routes</h3>
      <p>Each account gets an exclusive healthy node where possible, using primary, fallback, then direct routing.</p>
    </td>
  </tr>
  <tr>
    <td valign="top" width="50%">
      <h3>🔄 Automatic failover</h3>
      <p>Scheduled checks cover latency, connectivity, and exit IP; two abnormal results switch the route.</p>
    </td>
    <td valign="top" width="50%">
      <h3>🩺 Scoped status checks</h3>
      <p>Card checks cover one account; manual batch checks cover selected accounts and clean orphaned server data.</p>
    </td>
  </tr>
  <tr>
    <td valign="top" width="50%">
      <h3>📨 Daily midnight report</h3>
      <p>At midnight, refresh both subscriptions and recheck abnormal accounts; send a combined account, official-message, and node report when Bot notifications are enabled.</p>
    </td>
    <td valign="top" width="50%">
      <h3>🤖 Private Bot and Web entry</h3>
      <p>The target user can request codes with <code>/me</code> and <code>/code</code>, or open the dashboard from the private-chat menu.</p>
    </td>
  </tr>
  <tr>
    <td valign="top" width="50%">
      <h3>🔌 Isolated TeleBox</h3>
      <p>Each account has a separate session, directory, and process; TeleBox logout leaves the main authorization intact.</p>
    </td>
    <td valign="top" width="50%">
      <h3>💬 Chat and panel tools</h3>
      <p>Includes optional chat, themes and covers, TOTP, backup upgrades, and bounded caches and logs.</p>
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
2. **🌐 Configure subscriptions:** In Settings, save an HTTPS primary subscription and optionally a fallback, then refresh. Account networking remains in setup-required mode until configured. Each healthy node serves one account; overflow accounts use direct access. See the [Xray deployment notes](docs/deploy/docker.md#机场订阅与-xray).
3. **➕ Add an account:** Choose code or QR login in Account Management. An ordinary account may omit API ID/Hash; supply account-specific credentials when enabling TeleBox, and complete 2FA if prompted.
4. **🗂️ Check as needed:** A card check reads that account's Telegram, TeleBox, and IP status; a manual batch check also cleans orphaned server data. At 00:00 the service refreshes subscriptions, checks every account and the previous 24 hours of official messages, then sends the combined summary if Bot notifications are enabled.
5. **🤖 Configure the bot:** Set the Bot Token and target ID under Settings → Telegram bot notifications. For “打开WEB”, also set a Telegram-accessible HTTPS root URL. The target ID must be a positive private user ID.
6. **💾 Migrate authorization if needed:** Account Management → Login Backup can export/import an encrypted <code>.tglogin</code> file for primary sessions. It excludes TeleBox and panel settings; stop the old server before using the same authorization elsewhere. See the [login-backup guide](docs/guide/account-login-backup.md) (Chinese).

TeleBox manages its own commands and plugins. System plugins are bundled; community plugins are published in [TeleBox-Plugins](https://github.com/TeleBoxOrg/TeleBox-Plugins). See [TeleBox's README](telebox/README.md) for details.

<a id="midnight-report"></a>
## 📨 Combined midnight report

At 00:00 in the **configured panel time zone**, the service refreshes subscriptions, checks accounts and attempts recovery, reads official messages, then sends a combined summary. Example layout (counts are illustrative):

> **零点账户状态与官方消息日报**<br>
> Total 2 · Healthy 1 · Abnormal 1<br>
> 🟢 @account_a — healthy · primary · no new official messages<br>
> 🔴 @account_b — abnormal · fallback · new official messages · still abnormal after switching
>
> **零点机场订阅节点报告**<br>
> Primary (refreshed): usable 8 · unusable/unsupported 2<br>
> Fallback (refreshed): usable 3 · unusable/unsupported 1

The summary is sent only when Bot notifications are enabled. Refresh and check failures are called out, including retained-node status. Telegram's message limit may split the summary; official message details are sent separately where applicable.

<a id="bot-web"></a>
## 🤖 Bot “打开WEB” entry

This uses the **same notification bot**, independently of TeleBox plugins. In bot notification settings, save the Bot Token, a **positive private target user ID**, and the dashboard's **HTTPS root URL** (for example, <code>https://example.com</code>). The private chat receives the menu entry, and Settings shows the synchronization result. This entry does not depend on the notification delivery switch.

When the target user opens it inside Telegram, the backend verifies Telegram's signature and exact target ID before signing them in. Other IDs receive no Web authorization; visiting a public dashboard URL still requires normal administrator login. When private code retrieval is enabled, only the configured target can use <code>/me</code> and <code>/code</code>. Changing the Bot Token, target ID, or Web URL invalidates previous entry authorization.

<a id="guides"></a>
## 📚 Guides

- **🆕 [v2.5.1 release notes](docs/releases/v2.5.1.md)** — Combined report, Bot Web entry, and upgrade checks (Chinese).
- **📦 [Docker deployment and upgrades](docs/deploy/docker.md)** — Installation, backups, rollback, and build troubleshooting.
- **🧭 [Quick-start guide](docs/guide/quick-start.md)** — Initial setup and account onboarding.
- **📖 [v2.5.0 release guide](docs/releases/v2.5.0.md)** — Route assignment, timing, migration, and verification limits (Chinese).
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
