# Implementation
1. Pin both upstream commits and inspect integration points.
2. Parallel Trellis implementers: frontend/reference layout, communication backend, complete TeleBox runtime integration, old-plugin removal.
3. Root integrates router/lifespan, environment and build wiring; resolves contract drift.
4. Run frontend typecheck/build/tests, targeted Python tests and TeleBox runtime smoke check without sending messages.
5. Review auth, private material exposure, process shutdown, API consistency and desktop/mobile visual behavior.
6. Update deployment/user documentation, document verification limits, deliver reviewable branch and source bundle.

## Verification and remaining deployment checks (2026-10-02)

- Vue typecheck/build and 425 frontend tests passed. Targeted Python suite passed 141 tests before the additional integration tests; new cases cover auth, validation, bot token storage, pagination and runtime data isolation.
- TeleBox TypeScript `tsc --noEmit` and adapter import smoke passed using local dependencies, without opening a Telegram session.
- Live QR authorization, Bot API access, TPM remote installation and the multi-stage Docker image cannot be validated here without an authorized Telegram session / Docker runtime. Run `docker compose up -d --build` in the target environment and test one account before enabling more.
- Browser-based pixel review was unavailable in this environment. The screenshot-inspired layout is implemented in CSS with desktop/mobile and light/dark branches, but should be visually compared in the target browser.
- Keep the task in progress until the live checks above are completed; do not claim live TeleBox activation verified.

Rollback: independent feature branch; retain user data. Never rewrite upstream history or modify deployed servers.

## Documentation refresh (2026-10-03)

- [x] Audit current README, `.env.example`, Compose, Dockerfile, Python settings, frontend Vite proxy and TeleBox runtime requirements.
- [x] Replace upstream image based quick start with this branch's source build instructions in `README.md`, `README_EN.md`, `docs/guide/quick-start.md`, and `docs/deploy/docker.md`.
- [x] Document implemented modules, legacy plugin migration, Node 22/24 + Python requirements, private `.env`, local/Docker setup, data/backup, checks and validation limits in `README.md`.
- [x] Align `docs/index.md` and `docs/README.md`; check local Markdown links, fenced code blocks, secret absence, and `git diff --check`.

The user requested that changes, setup and required environment all be visible in Markdown. Do not put the supplied personal Telegram API credentials in committed documentation; use placeholders only.

### Documentation changes and verification

| File | Change |
| --- | --- |
| `README.md` | Authoritative Chinese guide: update inventory, system requirements, source build, first login, local dev, env variables, storage, upgrade, checks and limits. |
| `README_EN.md` | English summary and source build; removed old upstream GHCR `docker run` instructions. |
| `docs/guide/quick-start.md` | Private-repo clone, `.env`, Compose build, Telegram account and TeleBox first run. |
| `docs/deploy/docker.md` | Current three-stage Docker build, 2 GiB Compose limit, `/data`, troubleshooting and source upgrade. |
| `docs/index.md`, `docs/README.md` | Point documentation readers to this fork and the new installation guide. |

Static validation: all six modified Markdown files have balanced code fences and valid local links; the supplied API ID/Hash values are absent; `git diff --check` passes. This environment has Python 3.12 and Node 24, but no Docker CLI, so `docker compose config/build/up` were not run. This docs-only update did not rerun application tests or contact Telegram.

## User revisions (2026-10-03)

- [x] Inventory and remove remaining legacy plugin surfaces and task action branches while preserving actionable migration errors.
- [x] Add first-run administrator setup without a generated/printed password; retain existing installations safely.
- [x] Require and securely persist per-account Telegram API ID/Hash from both phone and QR login; update every client consumer and TeleBox.
- [x] Remove global AI model and Telegram API settings/UI/routes/services; keep unrelated settings and task history intact.
- [x] Show per-account installed TeleBox plugins in the extension area and support allowed controls.
- [x] Implement one-command server setup, update README/quick start/Compose and an ongoing Markdown change log.
- [x] Run focused backend/frontend tests and static validation. Publish a feature branch and PR against protected main; do not merge.

Live Docker build, Telegram account authorization, Bot API and remote TeleBox plugin installation remain deployment acceptance checks. The task stays in progress until those can be checked in the owner's environment.

## Current implementation checklist (2026-10-03, merged PR #17)

- [x] Keep Chat Center in the sidebar and move its on/off switch into the page; off reads only 777000, on shows group dialogs. Enforce a 5 MiB chat/avatar cache limit and clear when disabled.
- [x] Remove the dedicated group management page and System Settings proxy card; retain per-account proxy editing in Account Management. Keep General, Bot Notification and Data Management collapsed on initial render.
- [x] Repair TeleBox ESM dependency loading and surface its failure stage; support the optional TeleBox choice at login with account credentials or configured server defaults.
- [x] Report loaded command origin from the worker; filter both UI and backend to KITT and installed plugin commands. Reject an unavailable command on save and execution.
- [x] Remove plugin daily execution time and panel plugin scheduler jobs; keep TeleBox native `cronTasks` and Workbench daily messages. Preserve retired task data without executing its actions.
- [x] Present account and target selectors with avatars/search, and expose task delivery and worker logs without treating delivery as plugin completion.
- [x] Verify TeleBox TypeScript typecheck, frontend typecheck, 250 Vitest tests and production build, plus 29 focused backend tests; changed-file Ruff and whitespace checks passed for the PR snapshot.
- [ ] Validate a full Docker build, real Telegram authorization, KITT/installed plugin discovery and execution, official-message-only mode and scheduled Workbench delivery on the owner's server. Keep this task `in_progress` until those checks finish.

Earlier sections record the implementation sequence and test counts at those points in time. This checklist describes the behavior merged through PR #17.

## Visual and capacity checklist (2026-10-03)

- [x] Add a persisted desktop sidebar collapse toggle and distinct navigation accents; preserve mobile drawer and accessible names.
- [x] Rework shared light/dark surfaces and account tiles to match the supplied avatar/name/remark reference; move all account actions behind one three-dot menu.
- [x] Remove eager page warmup; bound account avatar request concurrency, blob size and total browser cache; release URLs on account removal and page exit.
- [x] Reduce the default per-worker V8 old-space limit from 512 to 128 MiB, make the 64–512 MiB setting configurable, document that it does not cap total process RSS.
- [x] Run frontend typecheck, tests and build; focused backend tests and Ruff; Git whitespace check.
- [ ] Visually check the authenticated account page on desktop/mobile in a real browser and measure total server RSS with the intended 20-account mix before claiming 2 GiB capacity.
