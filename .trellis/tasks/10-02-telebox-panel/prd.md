# Integrated Telegram management panel

## Goal
Rebuild TG-SignPulse using the supplied screenshot layout and real account chat management. User confirmed full scope on 2026-10-02 and requested built-in complete TeleBox migration replacing the existing Python plugin ecosystem. No dedicated channel management page.

## Requirements
- Reference layout: white fixed sidebar, blue-grey background with subtle geometric lines, roomy rounded panels, light/dark themes, mobile drawer, account cards/list and privacy toggles.
- Keep existing login, accounts, scheduling, logs, settings and authentication behavior.
- Chat center across all account dialogs: private, bot, group and channel conversations, history pagination, text/media send, reply, edit/delete, archive/unarchive, read state and search. Channel conversations remain here without a separate channel administration area.
- Account workbench: select account/targets, send messages and create timed tasks through the existing scheduler.
- Proxy management with real APIs. Bot center with token registration, profile/commands and message management through Telegram Bot API.
- Vendor complete TeleBox source, preserve its license, plugin runtime, built-in commands, TPM and lifecycle. Integrate per-account runtime control and logs into the panel; each account has isolated persistent plugin/config/data paths.
- Remove legacy Python plugin system, marketplace, debug/storage/editor UI, custom-plugin action and associated build/scripts/tests/docs. Existing legacy actions must fail visibly and never silently run a substitute.
- Supplied Telegram credentials belong only in an ignored private backend environment file; no secrets in frontend, git, API output or logs.

## 2026-10-03 revised requirements

- Remove the dedicated group management page, navigation, account shortcut and group management API. Group conversations remain available in chat and workbench.

- Remove all remaining original TG-SignPulse plugin UI, API, runtime references and plugin-specific task actions; TeleBox is the only plugin system. Historical task data remains readable for migration, with a clear error if it attempts an old action.
- Simplify server installation to a single copyable command. Generate and persist `APP_SECRET_KEY` automatically. On a fresh instance, the administrator sets their own password in a guarded web setup flow; no printed bootstrap password.
- Collect Telegram `API_ID` and `API_HASH` for each account at login and store them securely per account. All later client, monitor, task and TeleBox operations use that account's pair. Do not expose hashes in list/detail API responses.
- Remove AI model configuration and the global Telegram API settings feature from panel and API. Migrate/deprecate old global settings without deleting unrelated task data.
- Replace any old extension/plugin section with TeleBox installed/built-in plugin inventory and controls per account.
- Target the user's protected `main` branch through a feature branch and pull request, leaving the merge to the user. Keep Markdown updated with changes, setup, requirements, checks and limitations.

## Acceptance
- Existing account/task workflows continue working; new pages have actual authenticated APIs and actionable errors.
- No legacy plugin route or menu remains; only TeleBox plugin management exists.
- TeleBox full source is traceable to a pinned upstream commit; native dependencies and runtime included in deployment.
- Tests cover account boundaries, sensitive data filtering, history pagination, invalid inputs and runtime lifecycle.
- Frontend typecheck/build/tests and targeted backend tests pass. Desktop/mobile light/dark screenshots reviewed.
- Any operation needing actual Telegram authorization is reported unverified unless a real session is supplied; no unsolicited messages sent.
