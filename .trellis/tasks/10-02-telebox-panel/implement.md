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
