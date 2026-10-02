# Integrated Telegram management panel

## Goal
Rebuild TG-SignPulse using the supplied screenshot layout and real account chat management. User confirmed full scope on 2026-10-02 and requested built-in complete TeleBox migration replacing the existing Python plugin ecosystem. No dedicated channel management page.

## Requirements
- Reference layout: white fixed sidebar, blue-grey background with subtle geometric lines, roomy rounded panels, light/dark themes, mobile drawer, account cards/list and privacy toggles.
- Keep existing login, accounts, scheduling, logs, settings and authentication behavior.
- Chat center across all account dialogs: private, bot, group and channel conversations, history pagination, text/media send, reply, edit/delete, archive/unarchive, read state and search. Channel conversations remain here without a separate channel administration area.
- Account workbench: select account/targets, send messages and create timed tasks through the existing scheduler.
- Group management and proxy management with real APIs. Bot center with token registration, profile/commands and message management through Telegram Bot API.
- Vendor complete TeleBox source, preserve its license, plugin runtime, built-in commands, TPM and lifecycle. Integrate per-account runtime control and logs into the panel; each account has isolated persistent plugin/config/data paths.
- Remove legacy Python plugin system, marketplace, debug/storage/editor UI, custom-plugin action and associated build/scripts/tests/docs. Existing legacy actions must fail visibly and never silently run a substitute.
- Supplied Telegram credentials belong only in an ignored private backend environment file; no secrets in frontend, git, API output or logs.

## Acceptance
- Existing account/task workflows continue working; new pages have actual authenticated APIs and actionable errors.
- No legacy plugin route or menu remains; only TeleBox plugin management exists.
- TeleBox full source is traceable to a pinned upstream commit; native dependencies and runtime included in deployment.
- Tests cover account boundaries, sensitive data filtering, history pagination, invalid inputs and runtime lifecycle.
- Frontend typecheck/build/tests and targeted backend tests pass. Desktop/mobile light/dark screenshots reviewed.
- Any operation needing actual Telegram authorization is reported unverified unless a real session is supplied; no unsolicited messages sent.
