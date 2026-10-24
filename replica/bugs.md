# Bug Reports: CineStream

Tracking issues discovered during automated and manual QA passes.

---

### BUG-001: Missing Episode 2 in Series Seed Data Causing Null Next Episode Traversal

- **Severity:** S2 (Feature broken)
- **Flow / Case:** F03 / F03-H2
- **Screen:** S07 (TV Episode Watch Page)
- **Build:** v1.0.0  Browser / Device: Node.js Test Suite / Chrome 140

#### Steps
1. Navigate to `/api/series/stranger-things/seasons/1/episodes/1`.
2. Inspect `nextEpisode` pointer in JSON response.

- **Expected:** `nextEpisode` contains `{ episodeNumber: 2, title: "Chapter Two: The Weirdo on Maple Street" }`.
- **Actual:** `nextEpisode` was `null` because `Stranger Things` season 1 only contained 1 episode in the backend seed dictionary.
- **Evidence:** `TypeError: Cannot read properties of null (reading 'episodeNumber')` in `node --test tests/test-flows.js`.
- **Suspected Cause:** Seed data in `server/db.js` had truncated episode array.
- **Status:** Fixed. Added Episode 2 and 3 to `server/db.js` and re-ran tests. `F03-H2` passed.

---

### BUG-002: Deprecation Warning on Legacy `url.parse()` in HTTP Server

- **Severity:** S3 (Non-breaking warning with security implications)
- **Flow / Case:** Core Server / API routing
- **Screen:** Server runtime
- **Build:** v1.0.0

#### Steps
1. Launch Node.js server.
2. Trigger any incoming HTTP API request.

- **Expected:** Clean request execution with no runtime deprecation warnings.
- **Actual:** Node.js emitted `(node:10060) [DEP0169] DeprecationWarning: url.parse() behavior is not standardized and prone to errors that have security implications. Use the WHATWG URL API instead.`
- **Evidence:** Console log during `node server/index.js`.
- **Suspected Cause:** Legacy `url.parse(req.url, true)` call in request handler.
- **Status:** Fixed. Refactored `server/index.js` to use WHATWG `new URL(req.url, 'http://' + host)` and `searchParams`.

---

### Bug Summary
- **Open S1 Bugs:** 0
- **Open S2 Bugs:** 0
- **Open S3 Bugs:** 0
- **Total Bugs Fixed:** 2 (BUG-001, BUG-002)
- **Status:** Ready for replica-diff.
