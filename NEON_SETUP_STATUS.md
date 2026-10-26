# Neon setup status — 2026-10-26

- Confirmed Neon organization `Karan` (`org-young-rain-54892000`) is on the Free plan.
- Created `cinemymovies` (`ancient-leaf-30708350`) in AWS Oregon (`aws-us-west-2`), PostgreSQL 17, compute range 0.25–0.25 CU. No paid plan selected.
- Production branch: `br-wispy-fog-ar7mgnjk`; database `cinemymovies`.
- Isolated test branch: `auth-migration-test` (`br-proud-voice-arhl5grk`). Contains synthetic test records only. No real credentials imported.
- Verified the repository schema, transaction advisory lock, user/session insert and join, and committed state read on the test branch through Neon tools.
- Created the same empty schema on production. Verified zero users, sessions and metadata records. The website is not connected to this database yet.
- Render service: `cinemymovies`, `srv-dbe30p3rjlhs738s2q2g`, Oregon, Free, Docker runtime, GitHub auto-deploy enabled on main. Workspace: `tea-da0jt2e1egvs738tk320`.
- Existing Neon project `gymakhara` was not modified.

## Credential migration is pending

The local SQLite file contains admin, viewer and a test account. Local environment passwords match the local admin/viewer hashes, but both passwords received HTTP 401 when tested against the live website's login endpoint. Therefore this local file is not verified as a valid production credential backup and was not imported.

Need a verified production backup or the actual current admin and viewer passwords before completing recovery. Do not import the local test account. Do not overwrite or publicly reinitialize the live website.

## Configuration and verification still pending

Render environment variables are unchanged; no push or deployment was performed. Once credentials are recovered, provision the new database, configure AUTH_DATABASE_URL and a stable SESSION_SECRET through Render, then deploy the reviewed changes after Git push approval. Verify login and restart against the real Postgres backend.

Automatic approval review rejected persisting the live database connection URL in a repository scratch file. No secret file was written. Schema provisioning used the connected Neon tools instead. No connection string or password is recorded here.

The requested explicit 300-second suspend setting was rejected by the Free account before project creation. Creation then succeeded with the plan-managed default. No paid feature was enabled.
