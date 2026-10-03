# Integrated Telegram management panel

## Goal
Rebuild TG-SignPulse using the supplied screenshot layout and real account chat management. User confirmed full scope on 2026-10-02 and requested built-in complete TeleBox migration replacing the existing Python plugin ecosystem. No dedicated channel management page.

## Requirements
- Reference layout: white fixed sidebar, blue-grey background with subtle geometric lines, roomy rounded panels, light/dark themes, mobile drawer, account cards/list and privacy toggles.
- Keep login, accounts, logs, settings and authentication behavior; replace legacy sign-task scheduling with the TeleBox task store and a separate workbench daily-message schedule.
- The Chat Center menu remains visible. Its own switch defaults off and then reads only official 777000 verification messages. When on, show group conversations with history and supported message actions. Limit chat cache to 5 MiB and clear it when disabled or over limit; there is no separate channel or group administration page.
- Account workbench: select account/targets, send immediately and create daily scheduled messages through the new task store.
- Account-level proxy editing remains in Account Management; no separate proxy page or System Settings proxy card. Bot center uses real Telegram Bot API calls.
- Vendor complete TeleBox source, preserve its license, plugin runtime, built-in commands, TPM and lifecycle. Integrate per-account runtime control and logs into the panel; each account has isolated persistent plugin/config/data paths.
- Remove legacy Python plugin system, marketplace, debug/storage/editor UI, custom-plugin action and associated build/scripts/tests/docs. Existing legacy actions must fail visibly and never silently run a substitute.
- Supplied Telegram credentials belong only in an ignored private backend environment file; no secrets in frontend, git, API output or logs.

## 2026-10-03 revised requirements

## 2026-10-03 TeleBox-only task revision

- Remove the dedicated proxy navigation/route; the proposed System Settings proxy section was subsequently withdrawn. Account Management retains per-account proxy editing.
- Replace the active TG-SignPulse sign task form, action codes, keyword listener and scheduled sign execution with TeleBox plugin-command tasks. Adding a task first selects a TeleBox-enabled account, then reads that running account's loaded commands.
- Keep account workbench immediate send and daily scheduled message features; daily messages use a small explicit schedule, independent of the removed sign-task action pipeline.
- Existing sign task files/history remain on disk for recovery, but are never scheduled or offered as editable tasks. Do not silently transform old actions into TeleBox commands.

- Remove the dedicated group management page, navigation, account shortcut and group management API. Group conversations remain available in chat and workbench.

- Remove all remaining original TG-SignPulse plugin UI, API, runtime references and plugin-specific task actions; TeleBox is the only plugin system. Historical task data remains readable for migration, with a clear error if it attempts an old action.
- Simplify server installation to a single copyable command. Generate and persist `APP_SECRET_KEY` automatically. On a fresh instance, the administrator sets their own password in a guarded web setup flow; no printed bootstrap password.
- Collect Telegram `API_ID` and `API_HASH` for each account at login and store them securely per account. All later client, monitor, task and TeleBox operations use that account's pair. Do not expose hashes in list/detail API responses.
- Remove AI model configuration and the global Telegram API settings feature from panel and API. Migrate/deprecate old global settings without deleting unrelated task data.
- Replace any old extension/plugin section with TeleBox installed/built-in plugin inventory and controls per account.
- Target the user's protected `main` branch through a feature branch and pull request, leaving the merge to the user. Keep Markdown updated with changes, setup, requirements, checks and limitations.

## Acceptance
- Account login, chat when enabled, workbench send/daily message and TeleBox command workflows use authenticated APIs and actionable errors; retired sign tasks are not executed.
- No legacy plugin route or menu remains; only TeleBox plugin management exists.
- TeleBox full source is traceable to a pinned upstream commit; native dependencies and runtime included in deployment.
- Tests cover account boundaries, sensitive data filtering, history pagination, invalid inputs and runtime lifecycle.
- Frontend typecheck/build/tests and targeted backend tests pass. Desktop/mobile light/dark screenshots reviewed.
- Any operation needing actual Telegram authorization is reported unverified unless a real session is supplied; no unsolicited messages sent.

## 2026-10-03 chat and task revisions

- The Chat Center entry is always visible. Its own on/off control persists the setting. When off, the page shows only Telegram's official 777000 verification messages; when on, it shows ordinary conversations.
- Remove the separate per-account Proxy Management card from System Settings. Account-level proxy editing remains in Account Management.
- Add Task offers only loaded KITT commands and commands originating from newly installed per-account TeleBox plugins. Other bundled commands do not appear or run through this task list.
- Plugin tasks do not have a daily execution time. TeleBox owns plugin cron scheduling; existing saved plugin tasks stop receiving panel scheduler jobs. Workbench daily message timing remains available.

## 2026-10-03 visual and resource revision

- Rework the light and dark panel surfaces so the interface has a clear colored hierarchy instead of mostly white cards. The desktop sidebar can collapse to icons, remains a mobile drawer, and each navigation option from Dashboard through Logs has its own identifiable accent color.
- Account cards follow the supplied compact reference: one bounded tile, a larger avatar at the upper left, name then remark underneath, status below; all existing card actions appear only when the upper-right three-dot button is opened. Retain keyboard/accessible action labels and responsive layout.
- Favor a small resource footprint for roughly 20 accounts on a 2 GiB host: avoid eager route preloading, limit avatar requests and retained browser blob URLs, and constrain per-account TeleBox Node heap. Do not claim that 20 active TeleBox workers fit 2 GiB without measuring their total RSS on the deployment server.
