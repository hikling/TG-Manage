<p align="center"><img src="docs/public/logo.svg" width="80" height="80" alt="TG Manage logo"></p>
<h1 align="center">TG Manage</h1>
<p align="center">A Telegram multi-account dashboard with independently running TeleBox sessions.</p>
<p align="center"><a href="README.md">简体中文</a> · <strong>English</strong></p>
<p align="center"><a href="#whats-new">2.5.1</a> · <a href="#features">Features</a> · <a href="#quick-start">Install</a> · <a href="#bot-web">Bot Web entry</a> · <a href="#docs">Docs</a></p>

> Based on [Silentely/TG-SignPulse](https://github.com/Silentely/TG-SignPulse) and integrated with [TeleBoxOrg/TeleBox](https://github.com/TeleBoxOrg/TeleBox). Build from [hikling/TG-Manage](https://github.com/hikling/TG-Manage); upstream images do not include this project's dashboard and integration changes.

<a id="whats-new"></a>
## What's new in 2.5.1

| Feature | Behavior |
| --- | --- |
| Midnight subscription refresh | At 00:00 in the configured panel time zone, fetch the primary and fallback subscriptions and report usable nodes plus a combined unusable/unsupported count. Regular subscription refreshes and health checks continue. |
| Account recovery | An abnormal account is checked again. If it remains abnormal and a route change is appropriate, the system tries another usable node with a different exit IP and checks once more. The final result and recovery action appear in the report. |
| Combined daily report | Account status, Telegram official messages from the preceding 24 hours, and subscription node counts share a summary. Accounts appear above nodes, and both headings are bold. Long summaries can be split; official message details can still arrive separately. |
| Bot “打开WEB” menu | Add a Web entry to the private chat of the configured notification target ID. Telegram-signed data grants automatic dashboard login only to that ID. Other IDs receive no dashboard authorization and cannot use the private bot commands. |

See the [v2.5.1 release notes](docs/releases/v2.5.1.md) for details and upgrade checks.

<a id="features"></a>
## Features

- **Accounts and login:** Sign in with a phone code, QR code, or two-step verification. Migrate a primary account session with a password-encrypted <code>.tglogin</code> file.
- **Dedicated routes:** Built-in Xray supports an HTTPS primary subscription and an optional fallback. Each account prefers its own healthy node, then the fallback pool, then direct access when nodes run out.
- **Health and failover:** Check connectivity, latency, and exit IP regularly; recheck failures before switching routes and switch back after recovery. Account cards show country, public IP, and route source.
- **Daily summary:** Refresh subscriptions, recover abnormal accounts, and send one combined account, official-message, and node summary at midnight. See the [v2.5.0 notes](docs/releases/v2.5.0.md) for the scope of manual checks.
- **Private notification bot:** Send notifications to the configured target. Use <code>/me</code> for account numbers and <code>/code number</code> or an account name for recent login codes. The same bot provides the Web menu.
- **TeleBox and dashboard:** Independent TeleBox session and process per account, plus optional chat center, TOTP, themes, backups, and update tools.

<a id="quick-start"></a>
## Quick install

Install Docker Engine, Compose v2, and Git. A small deployment supports at least 1 vCPU and 1 GiB RAM; size up for more accounts or plugins. The server must reach Telegram and build dependencies.

~~~bash
git clone https://github.com/hikling/TG-Manage.git
cd TG-Manage
bash scripts/install.sh
~~~

The installer builds and starts the service, then prints a one-time setup code. Open <code>http://SERVER_IP:8080</code> and use the code to create an administrator password of at least 12 characters. Configure an [HTTPS reverse proxy](docs/deploy/nginx.md) before exposing the dashboard publicly.

**Existing installation:** Run the update script from the existing checkout. It backs up data before a fast-forward pull, rebuild, and restart.

~~~bash
bash scripts/update.sh
docker compose ps
docker compose logs --tail=100 app
~~~

Preserve all of <code>data/</code>, including <code>data/.app_secret_key</code>, the database, account sessions, and TeleBox data. Do not reinitialize or delete it. See the [Docker deployment guide](docs/deploy/docker.md) for manual upgrades, backups, and rollback.

## First-time setup

1. Add an HTTPS primary subscription under “Settings → Subscriptions”; a fallback is optional. Refresh it. Routes show “setup required” until configured.
2. Add accounts with phone-code or QR login. Ordinary accounts can omit API ID/Hash; TeleBox requires account-specific credentials as prompted.
3. Set the Bot Token and private target ID under “Settings → Telegram bot notifications”; enable notifications and the Web entry as needed.
4. For migration between servers, export/import an encrypted <code>.tglogin</code> under “Accounts → Login backup”. It does not include TeleBox or dashboard configuration.

<a id="bot-web"></a>
## Bot Web entry

The menu uses the **same notification bot** and is unrelated to TeleBox plugins. To enable it:

- Configure the Bot Token and a **positive private Telegram user ID** as the target. Group and channel IDs are not supported.
- Give the panel a Telegram-accessible **HTTPS root URL**, such as <code>https://example.com</code>, and save it in the bot notification settings. The dashboard sets “打开WEB” for that private chat and shows the menu synchronization result.
- Have that user start a private chat with the bot, then open the menu in that chat. The backend verifies Telegram's short-lived signature and the exact target ID before signing the user in.

Only that target ID can use the entry; when private code retrieval is enabled, only that ID can use <code>/me</code> and <code>/code</code>. Changing the Bot Token, target ID, or Web URL invalidates previous entry authorization. Anyone may still load a public URL, but that alone gives no dashboard login; normal browser visits continue through administrator login. Protect the Bot Token and administrator credentials.

## Midnight report

At 00:00 in the **configured panel time zone**, the service refreshes both subscriptions, checks all accounts (including recovery attempts), queries the previous 24 hours of official messages, and sends the combined summary. Its structure is:

~~~text
Midnight account status and official messages
Total 2 · Healthy 1 · Abnormal 1
🟢 @account_a — healthy · primary · no new official messages
🔴 @account_b — abnormal (...) · fallback · new official messages · still abnormal after switching

Midnight subscription node report
Primary (refreshed): usable ... · unusable/unsupported ...
Fallback (refreshed): usable ... · unusable/unsupported ...
~~~

Actual notification headings use the Chinese labels and are **bold**. Failures are shown explicitly, including when retained nodes are reported after a failed refresh. The summary may be split if it exceeds Telegram's message size limit; official message details are sent separately where applicable.

<a id="docs"></a>
## Documentation

- [v2.5.1 release notes](docs/releases/v2.5.1.md) · [v2.5.0 features and check timing](docs/releases/v2.5.0.md)
- [Docker install, upgrade, and rollback](docs/deploy/docker.md) · [Nginx HTTPS](docs/deploy/nginx.md)
- [Quick start](docs/guide/quick-start.md) · [Account login backup](docs/guide/account-login-backup.md)
- [Configuration reference](docs/reference/configuration.md) · [Local development](docs/reference/development.md) · [TeleBox](telebox/README.md)

<details>
<summary>Data, configuration, and development reference</summary>

Compose mounts the host's <code>./data</code> at <code>/data</code> in the container. Back up the entire directory: database, sessions, settings, logs, TeleBox data, custom covers, and <code>data/.app_secret_key</code>. Losing the key makes encrypted credentials and the Bot Token unreadable. Back up an external PostgreSQL database separately.

Common environment variables: <code>TG_MANAGE_TG_API_ID/HASH</code>, <code>APP_SECRET_KEY</code>, <code>APP_DATA_DIR</code>, <code>APP_DATABASE_URL</code>, and <code>TG_GLOBAL_CONCURRENCY</code>. Legacy aliases <code>SIGNPULSE_TG_API_ID/HASH</code> and <code>TG_API_ID/HASH</code> remain readable. See the [configuration reference](docs/reference/configuration.md) and [backend settings](backend/core/config.py) for full details. Never commit real secrets, sessions, Bot Tokens, or backups.

Source development requires Python 3.10–3.13, Node 22.23.1 for the frontend, and Node 24 for TeleBox. Checks:

~~~bash
python3 -m ruff check backend tg_manage tests
python3 -m pytest -q
cd frontend && npm run typecheck && npm test && npm run build
cd ../telebox && npx tsc --noEmit
~~~

Real Telegram login, Bot API behavior, and Docker builds still need verification on the deployment. TeleBox retains its [LGPL-2.1-only license](telebox/LICENSE); see the root [LICENSE](LICENSE) for the rest of the project.

</details>
