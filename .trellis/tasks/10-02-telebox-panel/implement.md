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

- [ ] Inventory and remove remaining legacy plugin surfaces and task action branches while preserving actionable migration errors.
- [ ] Add first-run administrator setup without a generated/printed password; retain existing installations safely.
- [ ] Require and securely persist per-account Telegram API ID/Hash from both phone and QR login; update every client consumer and TeleBox.
- [ ] Remove global AI model and Telegram API settings/UI/routes; keep unrelated settings and task history intact.
- [ ] Show per-account installed TeleBox plugins in the extension area and support allowed controls.
- [ ] Implement one-command server setup, update README/quick start/Compose and an ongoing Markdown change log.
- [ ] Run focused backend/frontend tests and static validation. Publish a feature branch and draft PR against protected main; do not merge.
