# Test Plan: CineStream (YoMovies Clean-Room Rebuild)

Build: v1.0.0-verified  Date: 2026-10-24  Env: Local Node.js REST API + SPA Client (Seed Data & PostgreSQL)

| Case ID | Flow / Goal | Type | Steps | Expected Outcome | Auto | Result |
| --- | --- | --- | --- | --- | --- | --- |
| F01-H1 | Search and stream movie | Happy | Open homepage, enter "dune" in global search bar | Live dropdown displays matching titles with poster, rating, and year | e2e | PASS |
| F01-H2 | View movie streaming details | Happy | Click "Dune: Part Two", navigate to /movie/dune-part-two | 16:9 player initializes, active server indicator displays green, synopsis & cast visible | e2e | PASS |
| F01-E1 | Empty search query handling | Edge | Type whitespace or empty string in search box | Dropdown hides gracefully without network errors or unhandled exceptions | e2e | PASS |
| F01-E2 | Multi-server playback failover | Edge | Click Server 2 / Server 3 pill tabs during playback | Player swaps video stream source seamlessly without reloading page or losing layout | e2e | PASS |
| F01-N1 | Non-existent title lookup | Negative | Navigate to /api/media/non-existent-slug-xyz | API returns 404 with structured JSON error; client displays friendly 404 screen | e2e | PASS |
| F02-H1 | Catalog type filtering | Happy | Click "Movies" filter pill on /movies archive | Results grid displays exclusively movie items; TV shows filtered out | e2e | PASS |
| F02-H2 | Multi-attribute genre filter | Happy | Select Genre: "Action" from dropdown | All displayed titles contain "Action" tag in metadata | e2e | PASS |
| F02-H3 | Sort order ranking | Happy | Select Sort: "Top Rated" | Catalog items sorted in descending order of IMDb rating | e2e | PASS |
| F02-E1 | Zero-match filter combination | Edge | Select non-matching filters (e.g. invalid genre & quality) | Grid displays empty state with "Reset All Filters" CTA button | e2e | PASS |
| F03-H1 | TV Series hierarchy | Happy | Open /series/stranger-things | Header displays title, synopsis, season tabs (Season 1, Season 2), and episode cards | e2e | PASS |
| F03-H2 | Episode stream & traversal | Happy | Play Season 1 Episode 1, click "Next Episode" | Player transitions to Episode 2, updates title and synopsis, prev button enabled | e2e | PASS |
| F03-E1 | Boundary episode navigation | Edge | Navigate to Episode 1 (start) and Season Finale (end) | Previous button disabled on Ep 1; Next button shows "Season Finale" disabled | e2e | PASS |
| F03-N1 | Non-existent episode route | Negative | Request /series/stranger-things/seasons/99/episodes/99 | API returns 404; client renders 404 page | e2e | PASS |
| F04-H1 | Broken link reporting | Happy | On watch page, click "Report Broken Link", select reason, submit | Modal POSTs to /api/reports, receives 201 Created with report ID, shows toast confirmation | e2e | PASS |
| F04-E1 | Server health monitoring | Edge | Trigger /api/cron/check-servers endpoint | Returns operational health status with tested endpoint count | e2e | PASS |
| F04-E2 | Abuse prevention / Rate limiting | Edge | Submit >10 reports within 60 seconds from same IP | Server returns HTTP 429 Too Many Requests | e2e | PASS |
| F05-H1 | Add to watchlist | Happy | Click bookmark heart icon on media card | Item added to client queue, header counter increments to 1, toast alert shown | e2e | PASS |
| F05-H2 | Remove from watchlist | Happy | Click active bookmark icon again | Item removed from queue, header badge decrements, toast confirmation shown | e2e | PASS |
| F05-E1 | Strict session isolation | Edge | Access /api/watchlist from Client B (different cookie) | Client B receives completely empty queue (0 items); Client A items invisible | e2e | PASS |
| F05-E2 | LocalStorage persistence | Edge | Refresh browser after bookmarking title | Watchlist state retained across page reload and browser restarts | e2e | PASS |
| UI-H1 | Theater mode toggle | Happy | Click "Lights Off" button on watch page | Background dims, main container focused, press ESC to restore lights | e2e | PASS |
