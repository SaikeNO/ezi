# Codex instructions — WebCrawler Studio

## Mission

Build a **working** Polish-language web application meeting `docs/LAB_REQUIREMENTS.md`. Read `IMPLEMENTATION_PLAN.md`, `docs/ARCHITECTURE.md` and `docs/API.md` before implementing features.

## Development workflow

1. Inspect the repository and current implementation before making changes.
2. Implement only the requested phase, preserving previous functionality.
3. Use typed interfaces, database migrations and explicit validation.
4. Add or update unit/integration tests for every meaningful behavior.
5. Run relevant checks. Report actual pass/fail results; never claim unrun checks passed.
6. Update documentation, list changed files, known issues and deferred work.
7. Stop after the requested phase; do not silently start the next phase.

## Technical constraints

- Backend: Python 3.12+, FastAPI, httpx, BeautifulSoup4, SQLAlchemy 2, Alembic, SQLite.
- Frontend: React, TypeScript, Vite, Tailwind, shadcn/ui, Cytoscape.js, Recharts.
- REST endpoints and SSE as specified in `docs/API.md`.
- Database/API are the source of truth. Frontend must not invent crawl metrics.
- Tests must cover BFS, DFS, normalization, depth, scope, extraction, CSV and comparison.
- Never pass fixture/demo metrics off as real crawler results.

## Security and responsible crawling

- Allow only HTTP/HTTPS URLs; enforce bounded page count, depth, response size, time, redirects and concurrency.
- Respect `robots.txt` by default; use a descriptive User-Agent and per-origin rate limiting.
- Defend against SSRF including DNS resolution, DNS rebinding, redirects, IP literals and private/loopback/link-local/metadata endpoints. Verify actual connection destinations.
- Reject invalid hosts and unsupported schemes. Do not execute downloaded JavaScript or HTML.
- Track request errors without losing the entire crawl; cancellation must terminate new requests promptly.
- Prevent CSV formula injection. Escape all untrusted HTML/text in frontend.

## Semantics

- The start page has depth 0; depth is number of link traversals from the start.
- BFS/DFS control retrieval order; comparisons must not claim that traversal order necessarily changes the final complete graph.
- Distinguish discovered links from fetched HTML pages; images/assets can be graph targets without being crawled as HTML.
- Persist config per session so comparisons are reproducible.
- When historical tools' semantics are ambiguous, document the project's precise interpretation rather than claiming byte-for-byte compatibility.
