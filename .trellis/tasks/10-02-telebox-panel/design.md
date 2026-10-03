# Design

Retain Vue/Pinia/Tailwind and FastAPI/Pyrogram. Add domain router/services for communications and TeleBox. Reuse auth dependencies, account session lifecycle and existing request helper. Telegram IDs serialized as strings to avoid JS precision loss.

## Shared API contract
All new routes under `/api`, using existing Bearer auth.
- `/communications/{account}/dialogs?query=&offset=0&limit=50&archived=false&kind=all`: `{items:[{id,title,username,type,unread_count,archived,last_message,last_message_at}],has_more,next_offset}`.
- `/communications/{account}/messages?chat_id=&before_id=0&limit=50`: `{items:[{id,chat_id,text,date,outgoing,sender_name,reply_to_message_id,media_type,has_media}],has_more,next_before_id}` in chronological order.
- POST `/communications/{account}/messages` `{chat_id,text,reply_to_message_id?}`; PUT/DELETE `/communications/{account}/messages/{message_id}` with `{chat_id,text?}`.
- POST `/communications/{account}/media` multipart `chat_id,file,caption?,reply_to_message_id?`, max 20 MiB. GET `/communications/{account}/media/{message_id}?chat_id=` authenticated blob.
- POST `/communications/{account}/dialogs/action` `{chat_id,action:read|archive|unarchive|pin|unpin|mute|unmute}`.
- GET `/communications/{account}/groups` same dialog envelope; GET `.../groups/{chat_id}` detail `{id,title,description,members_count,username}`; PUT same `{title?,description?}`; POST `.../groups/{chat_id}/leave`.
- GET `/communications/proxies` `{items:[{account,proxy}]}`; PUT `/communications/{account}/proxy` `{proxy:string}` using existing account settings.
- GET/POST `/bots` list `{items:[{id,username,first_name,description,short_description,running}]}` and create `{token}`; GET/PUT/DELETE `/bots/{id}`; PUT body `{first_name?,description?,short_description?}`; GET/PUT `/bots/{id}/commands` envelope `{commands:[{command,description}]}`.
- `/telebox/{account}` GET status `{account,status,enabled,version,plugins:[{name,kind}],message?}`; POST `/telebox/{account}/start`, `/stop`, `/restart`; GET `/telebox/{account}/logs` `{items:[{time,level,message}]}`; POST `/telebox/{account}/plugins` `{action:install|uninstall|update|reload,name?}`. GET `/telebox` overview `{version,upstream_commit,accounts:[]}`.
Backend service may extend contracts but coordinate with frontend before changing.

## Runtime boundary
TeleBox vendored under `telebox/`, original TypeScript and upstream metadata retained. Per-account working directory under app data, private permissions. Real Node 24 runtime, subprocess supervision, bounded logs, graceful stop and restart recovery. Independent Telegram authorization per worker preferred; avoid concurrent SQLite ownership. Process args must never contain API hashes/session strings. No arbitrary paths or shell snippets accepted by panel APIs.

## Migration
No destructive deletion of user data. Legacy plugin actions are rejected with a clear migration message. Built-in standard task actions remain.

## 2026-10-03 onboarding and credential amendment

- Compose mounts `./data` at `/data` and invokes the repository build through `scripts/install.sh`. No shared Telegram API, application secret, or initial password is required in `.env`. `get_default_secret_key()` creates a mode 0600 `data/.app_secret_key` once; startup prepares a mode 0600 `data/.admin_setup_token` only if the user table is empty. `/auth/setup-status` reports only whether setup is needed; `/auth/setup` verifies the server-side token with a constant-time comparison under a file lock, hashes the chosen password, creates `admin`, consumes the token and returns a JWT. Existing users are unaffected.
- Phone and QR login start requests require `api_id` and `api_hash`. The pair remains in the pending login session and is persisted only after Telegram authorization succeeds. The account store encrypts the pair using a Fernet key derived from the persisted application secret; `accounts.json` and the key file remain mode 0600 across container restarts. List/detail APIs expose no credential fields.
- `get_client` and explicit sign task/chat/keyword paths resolve the logged-in account's encrypted pair. TeleBox uses `_build_account_client`, so its worker receives the same account-specific pair via IPC without putting it in process args. Existing accounts without a pair are marked `API_CREDENTIALS_MISSING` in the list and must reauthenticate. Renaming moves the encrypted entry; deleting an account removes it.
- Global Telegram API and AI model configuration routes and cards are removed. Config JSON export/import no longer carries or reactivates those retired settings. Existing task records and data files are left in place for manual migration; the new task action picker no longer offers AI actions. “拓展插件” routes to the installed TeleBox plugin inventory per account.

## Ownership
Frontend agent owns frontend except legacy plugin files/removal (coordinates removal agent). Communications agent owns new backend services/routes and tests. TeleBox agent owns telebox/, TeleBox backend/tests and Docker build. Removal agent owns removal of old plugin backend/engine/frontend imports/scripts/docs/tests. Root wires shared router/lifespan, private config, integration checks and packaging.
