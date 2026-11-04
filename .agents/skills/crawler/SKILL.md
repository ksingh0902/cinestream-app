---
name: crawler
description: >-
  Crawls and syncs newly added movies, web series, dual-audio, and featured content across YoMovies, PRMovies, Ask4Movies, DuoFlix, and Movies7 into CineMyMovies. Detects duplicates, reports newly added vs refreshed counts, and keeps both local and production databases unified. Use when the user types "/crawler", "/crawler discover", "crawl movies", "sync catalogue", "fetch latest movies", or asks to crawl or update movies from supported sources.
---

# CineMyMovies Crawler Skill (`/crawler`)

Use this skill whenever the user invokes `/crawler`, asks to crawl/scrape movies or series, or wants to synchronize the CineMyMovies catalogue across supported sources.

## Supported Content Sources
1. **YoMovies** (`https://yomovies.com.im`): Latest Bollywood, Hollywood, Dual Audio, Web Series, OTT releases.
2. **PRMovies** (`https://prmovies.ventures`): High-definition Hindi dubbed, regional South Indian, and featured titles.
3. **Ask4Movies** (`https://fbox.gd` / `https://ask4movietv.cyou`): Global movies, trending TV series, and top IMDb collections.
4. **Movies7** (`https://movies7to.net`): Hollywood releases with TMDB metadata enrichment and cross-source duplicate prevention.
5. **DuoFlix** (`cluster.watchkar.com` / `dooflix.app`): Direct streaming catalogue feeds and episode structures.

---

## Command Routing & Execution

Execute the unified CLI runner [sync_latest.py](file:///c:/Users/Singh/Downloads/new-me/sync_latest.py) via `run_command`:

| User Command | Action & Command Line |
| :--- | :--- |
| `/crawler` or `/crawler all` | `python sync_latest.py --source all` |
| `/crawler yomovies` | `python sync_latest.py --source yomovies` |
| `/crawler prmovies` | `python sync_latest.py --source prmovies` |
| `/crawler ask4movies` | `python sync_latest.py --source ask4movie` |
| `/crawler movies7` | `python sync_latest.py --source movies7` |
| `/crawler duoflix` | `python sync_latest.py --source duoflix` |
| `/crawler report` | `python sync_latest.py --report-only` |

---

## De-Duplication Protocol

Always ensure duplicates are prevented across sources:
1. **Primary Key Match**: If `(source, source_id)`, `url`, or `slug` already exists in `movies`, update recency and streams; never create a duplicate row.
2. **Cross-Source Title Normalization**: Before inserting titles from secondary sources (e.g. Movies7, Ask4Movies), verify against `is_movie_available_on_primary_sources(title, year)`.
3. **Title Normalizer Rules**: Strip release years `(2026)`, dubbing markers (`[Dual Audio]`, `Hindi Dubbed`), season numbers (`Season 1`, `S01`), and OTT network names (`Netflix`, `Zee5`, `Hotstar`). If the normalized string matches an existing title within a $\pm 1$ year window, skip duplicate insertion.
4. **Tag Preservation**: When refreshing an existing title, union-merge newly discovered tags with previously stored tags in `genres` so no multi-platform badges are lost.

---

## Verification & Reporting

After running the crawl:
1. **Database Integrity**:
   Verify integrity on both SQLite databases:
   ```python
   import sqlite3
   for db in ["yomovies.db", "cinemymovies.sqlite3"]:
       res = sqlite3.connect(db).execute("PRAGMA integrity_check").fetchone()[0]
       assert res == "ok"
   ```
2. **Output Structured Metrics**:
   Present the crawl results to the user with exact numbers in the following format:

```markdown
### CineMyMovies Crawler Ingestion Report

| Source | Scanned | Added (New) | Refreshed | Duplicates Skipped |
| :--- | :---: | :---: | :---: | :---: |
| **YoMovies** | {count} | {added} | {updated} | {skipped} |
| **PRMovies** | {count} | {added} | {updated} | {skipped} |
| **Ask4Movies** | {count} | {added} | {updated} | {skipped} |
| **Movies7** | {count} | {added} | {updated} | {skipped} |
| **DuoFlix** | {count} | {added} | {updated} | {skipped} |
| **TOTAL** | **{total}** | **{total_added}** | **{total_refreshed}** | **{total_skipped}** |

* **Total Database Catalogue**: {total_count} titles (+{newly_added} newly added)
* **Databases Synchronized**: `cinemymovies.sqlite3` & `yomovies.db`
* **Cache Status**: Invalidation & prewarming triggered
```

3. **Follow Project Rules**:
   - Provide the 3-section Post-Change Summary (`1. Root Cause`, `2. What Was Fixed`, `3. Status`).
   - If the user requests pushing to GitHub or deploying to Oracle VM, ask for explicit approval before executing any `git push`.

