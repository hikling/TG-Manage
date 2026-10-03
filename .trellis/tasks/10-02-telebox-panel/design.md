# Design

Retain Vue/Pinia/Tailwind and FastAPI/Pyrogram. Add domain router/services for communications and TeleBox. Reuse auth dependencies, account session lifecycle and existing request helper. Telegram IDs serialized as strings to avoid JS precision loss.

## Shared API contract
All new routes under `/api`, using existing Bearer auth.
- `/communications/{account}/dialogs?query=&offset=0&limit=50&archived=false&kind=all`: `{items:[{id,title,username,type,unread_count,archived,last_message,last_message_at}],has_more,next_offset}`.
- `/communications/{account}/messages?chat_id=&before_id=0&limit=50`: `{items:[{id,chat_id,text,date,outgoing,sender_name,reply_to_message_id,media_type,has_media}],has_more,next_before_id}` in chronological order.
- POST `/communications/{account}/messages` `{chat_id,text,reply_to_message_id?}`; PUT/DELETE `/communications/{account}/messages/{message_id}` with `{chat_id,text?}`.
- POST `/communications/{account}/media` multipart `chat_id,file,caption?,reply_to_message_id?`, max 20 MiB. GET `/communications/{account}/media/{message_id}?chat_id=` authenticated blob.
- POST `/communications/{account}/dialogs/action` `{chat_id,action:read|archive|unarchive|pin|unpin|mute|unmute}`.
- The workbench filters `/communications/{account}/dialogs?kind=groups` for common group conversations; dedicated group management APIs are removed.
- Per-account proxy updates use the existing account settings path. The former aggregate proxy view is not exposed as a separate page.
- GET/POST `/bots` list `{items:[{id,username,first_name,description,short_description,running}]}` and create `{token}`; GET/PUT/DELETE `/bots/{id}`; PUT body `{first_name?,description?,short_description?}`; GET/PUT `/bots/{id}/commands` envelope `{commands:[{command,description}]}`.
- `/telebox/{account}` GET status `{account,status,enabled,version,plugins:[{name,kind}],message?}`; POST `/telebox/{account}/start`, `/stop`, `/restart`; GET `/telebox/{account}/logs` `{items:[{time,level,message}]}`; POST `/telebox/{account}/plugins` `{action:install|uninstall|update|reload,name?}`. GET `/telebox` overview `{version,upstream_commit,accounts:[]}`.
Backend service may extend contracts but coordinate with frontend before changing.

## Runtime boundary
TeleBox vendored under `telebox/`, original TypeScript and upstream metadata retained. Per-account working directory under app data, private permissions. Real Node 24 runtime, subprocess supervision, bounded logs, graceful stop and restart recovery. Independent Telegram authorization per worker preferred; avoid concurrent SQLite ownership. Process args must never contain API hashes/session strings. No arbitrary paths or shell snippets accepted by panel APIs.

## Migration
No destructive deletion of user data. Legacy sign-task files and history remain for recovery, but their routes, scheduler and action pipeline are retired. Old actions are not converted or executed.

## 2026-10-03 onboarding and credential amendment

- Compose mounts `./data` at `/data` and invokes the repository build through `scripts/install.sh`. No shared Telegram API, application secret, or initial password is required in `.env`. `get_default_secret_key()` creates a mode 0600 `data/.app_secret_key` once; startup prepares a mode 0600 `data/.admin_setup_token` only if the user table is empty. `/auth/setup-status` reports only whether setup is needed; `/auth/setup` verifies the server-side token with a constant-time comparison under a file lock, hashes the chosen password, creates `admin`, consumes the token and returns a JWT. Existing users are unaffected.
- Phone and QR login start requests require `api_id` and `api_hash`. The pair remains in the pending login session and is persisted only after Telegram authorization succeeds. The account store encrypts the pair using a Fernet key derived from the persisted application secret; `accounts.json` and the key file remain mode 0600 across container restarts. List/detail APIs expose no credential fields.
- `get_client` and current chat/account operations resolve the logged-in account's encrypted pair. TeleBox uses `_build_account_client`, so its worker receives the same account-specific pair via IPC without putting it in process args. Existing accounts without a pair are marked `API_CREDENTIALS_MISSING` in the list and must reauthenticate. Renaming moves the encrypted entry; deleting an account removes it.
- Global Telegram API and AI model configuration routes and cards are removed. Config JSON export/import no longer carries or reactivates those retired settings. Existing task records and data files are left in place for manual migration; the new task action picker no longer offers AI actions. “拓展插件” routes to the installed TeleBox plugin inventory per account.

## Ownership
Frontend agent owns frontend except legacy plugin files/removal (coordinates removal agent). Communications agent owns new backend services/routes and tests. TeleBox agent owns telebox/, TeleBox backend/tests and Docker build. Removal agent owns removal of old plugin backend/engine/frontend imports/scripts/docs/tests. Root wires shared router/lifespan, private config, integration checks and packaging.

## Current design amendment (2026-10-03)

- `views/Layout.vue` always includes Chat Center. `views/Chats.vue` owns the persistent toggle; when off it calls only the official-message endpoint for 777000, and when on it loads group dialogs. The communications service blocks ordinary chat reads when disabled. Chat/avatar caches are bounded at 5 MiB, cleared on disable and evicted at the limit.
- Account login optionally enables TeleBox. Disabled TeleBox does not require account-entered API ID/Hash when private server defaults are configured; Telegram authorization itself still needs valid application credentials. The worker loads `teleproto/sessions/index.js` through the compatible CommonJS path and reports the failing startup phase.
- The TeleBox worker lists loaded commands with plugin and `source` (`builtin` or `installed`). `/telebox-tasks/available/{account}` and the UI admit only built-in KITT or commands of per-account installed plugins. Save and execution validate again against the running account; manual execution sends a command into that account's Saved Messages through TeleBox. A successful delivery is not proof of plugin completion; inspect TeleBox logs.
- `backend/services/telebox_tasks.py` stores plugin command tasks and workbench daily messages in `data/telebox-tasks.json`; the old sign-task files remain inert. Plugin task `time` is `null`; the panel scheduler registers only daily message jobs. Plugin-owned `cronTasks` execute within TeleBox's own lifecycle. Account renames move new task references; account removal disables affected tasks.
- `views/Settings.vue` keeps General, Bot Notification and Data Management collapsed until opened. Proxy edits stay on account controls, with no proxy card in Settings. Account Workbench uses searchable avatar-backed target selection, and the standalone group management route is removed.

## Visual and memory amendment (2026-10-03)

- `views/Layout.vue` persists a desktop-only collapsed state in local storage; icon links retain title/accessible label and distinct colors. The mobile drawer and focus handling remain separate. Remove idle-time warmup of every lazy page; hover/focus prefetch stays available.
- Shared panel color tokens in `style.css` create tinted light/dark surfaces and a dark blue sidebar without large images or additional UI dependencies. `views/Accounts.vue` uses one compact avatar-first tile per account with a single at-a-time action menu, outside-click and Escape dismissal.
- Account avatar fetch concurrency is 2. The browser refuses individual blobs over 128 KiB or an aggregate over 2 MiB, reuses Object URLs, removes deleted-account entries and revokes all URLs on unmount. The server's disk avatar cache remains distinct from this browser memory budget.
- TeleBox sets Node `--max-old-space-size` to `TELEBOX_NODE_HEAP_MB` (default 128; clamped 64–512). This only bounds V8 old-space; native allocations, Python and other services still count against the 2 GiB container. Capacity for 20 running workers needs real RSS measurements.
