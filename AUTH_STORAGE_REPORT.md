# Authentication reset investigation and recovery

## Root cause: evidence and limits

The repository confirms an unsafe persistence design, but does not establish the precise production incident. Render deployment logs, dashboard environment values, and a pre/post-incident database snapshot were not available in this session.

At commit `59abf5e`, `app/auth/store.py:get_db_connection` opened a local SQLite file. `is_setup_completed` read only `auth_meta.setup_completed`; absence of that row returned false even if credentials remained. `complete_initial_setup` used `ON CONFLICT(username) DO UPDATE` to overwrite password hashes. See `git show 59abf5e:app/auth/store.py`. The checked-in `render.yaml` specifies `plan: free`, no durable database or disk, and originally only PYTHON_VERSION. SQLite files are ignored by Git. Thus losing the runtime database, using another path, or reaching an instance with a different local database could reopen setup. Dashboard overrides could differ from this file.

Render documents that its default filesystem is ephemeral across restarts and deploys: https://render.com/docs/disks . Its disks cannot be shared across service instances. This supports the persistence failure mechanism, but does not prove which lifecycle event caused this incident. Do not attribute it to a new browser/device or a specific sleep event without logs.

The supplied report overstates several findings:

- At `59abf5e`, SQLite query exceptions propagate; the code does not demonstrate that every database error evaluates to false.
- The subsequent `57aa818` fix still used local SQLite plus a colocated `.setup_locked` file. Both could disappear together. Environment passwords cannot preserve later password changes, revocations, or database-backed sessions.
- Its state function computed `has_valid_viewer` but never used it to prevent setup. A lock marker alone could report initialized with no usable accounts.
- `scratch/test_setup_resilience.py`, part 5, merely navigated both pages again. It did not terminate or restart a server. Its outage check tested Python state/rendering rather than HTTP access during an outage.

## Trace and changes

- `app/auth/database.py`: shared Postgres for production, local SQLite only for development. Production requires AUTH_DATABASE_URL and SESSION_SECRET and never falls back to a local file. Connections are closed, errors propagate, and initialization uses a Postgres transaction advisory lock (SQLite BEGIN IMMEDIATE locally).
- `app/auth/store.py`: bcrypt hashes reside in auth_users; completion in auth_meta; sessions/revocations/rate limits in the same database. State reads perform no bootstrap or schema creation. Existing admin OR viewer credentials prevent setup even when metadata is missing. A completion marker without credentials requires recovery. Empty production storage returns unavailable, never public setup. Startup creates schema but does not recreate or overwrite production credentials from environment passwords.
- `app/auth/provision.py`: explicit operator command imports existing password hashes, names, roles, versions and timestamps from a readable SQLite backup. It serializes with other initialization and refuses a destination with existing authentication state. It deliberately does not import old sessions; users sign in again with their unchanged passwords. A separate interactive `--new` mode is only for a genuinely new installation.
- `app/auth/middleware.py` / `routes.py`: failed state reads and later session/login database failures return 503 and deny protected access. POST /setup is denied after initialization; production public setup is always disabled. Local initial setup checks inside a write transaction before inserting. Expired/revoked sessions go to login.
- `server/static/index.html`: the frontend routes 401 to login, while 503 authentication responses show a retry overlay. No service-worker registration was found in server, web, or root index.html. The server chooses setup/login; browser storage does not control global setup. All middleware responses have no-store caching headers.

## Verification performed

`python -m scratch.test_auth_durable` passed using disposable SQLite storage and real Edge/Playwright browser contexts:

1. Two independent contexts log in through two separate server processes sharing storage.
2. One server process is terminated and restarted; both sessions remain usable and neither browser sees setup.
3. Both contexts clear cookies and log in again with the original viewer credentials.
4. Injected state-read and late session-query failures produce HTTP 503 for protected pages; setup GET/POST stays inaccessible; restoring storage restores access.
5. Removing the admin and completion marker leaves the viewer password hash intact and setup locked.
6. Expiring and revoking sessions returns both browsers to login.

`python -m unittest scratch.test_auth_state -v` covers production configuration absence, empty production storage, lost database, markers without credentials, actual Postgres-driver connection failure, and competing setup submissions. The tests use disposable databases and never modify the existing local credentials.

These are auth integration tests with the real routes/middleware and a minimal protected page, not a full catalogue/playback regression run. No live Postgres server or Render credentials were supplied; successful Postgres provisioning, cross-host behavior and Render redeploy verification remain deployment checks. The failed-connection test exercises the actual psycopg driver. Syntax compilation and `git diff --check` were also run. No push or deployment was performed.

## Required Render configuration and migration order

1. Before restarting/redeploying the old service, preserve its current SQLite database if still readable. Use SQLite's backup API (or a consistent stopped-database backup including WAL), not a casual copy of an active main file. Keep this backup private; it contains password hashes. Check the actual AUTH_DB_PATH / DB_PATH in the current service. A local development database is not automatically the production database.
2. Create or select a durable, backed-up Postgres database. Use a non-expiring production plan. Render's free database expiration is documented at https://render.com/docs/free . A persistent disk with SQLite does not satisfy the multiple-instance requirement.
3. Install the updated requirements in the operator environment. Set AUTH_DATABASE_URL to that database's connection URL (use provider TLS settings for external connections). Set ENVIRONMENT=production and a stable SESSION_SECRET. Preserve the existing secret if known; otherwise generate a strong random value and expect all existing sessions to sign in again. Give every web instance the identical URL and secret.
4. Before directing the web service to the new database, run from the updated checkout:

   ```text
   python -m app.auth.provision --sqlite-backup /absolute/path/to/auth-backup.sqlite3
   ```

   The importer refuses an already populated destination. Do not delete destination credentials to bypass this safeguard. Import from a host that can reach the database; an internal Render URL is reachable only in the applicable Render network. Do not commit connection strings, passwords, secrets, or backups.

5. Set those same AUTH_DATABASE_URL, SESSION_SECRET and ENVIRONMENT values in the Render web service. `render.yaml` now declares them; it does not provision a database or change an existing dashboard service by itself. AUTH_DB_PATH and DB_PATH no longer select production authentication storage. DB_PATH still controls the separate catalogue database; this change does not migrate catalogue data.
6. Deploy. Missing configuration or an empty/unreachable database intentionally produces 503, never setup. ADMIN_INITIAL_PASSWORD / VIEWER_INITIAL_PASSWORD are no longer production recovery mechanisms. If no valid credential backup survives, old hashes cannot be reconstructed; an operator must make an explicit recovery decision. Do not use `--new` as an automatic replacement for lost credentials.
7. On Render, log in from two independent contexts, restart/redeploy, verify the same credentials still work, and verify GET/POST /setup cannot expose or overwrite credentials. On staging, interrupt database connectivity and confirm protected routes plus setup remain denied with a retry response. Restore connectivity and recheck login. Collect deploy timestamps, resolved historical database paths (without secrets), instance IDs and storage errors to confirm the original incident.
