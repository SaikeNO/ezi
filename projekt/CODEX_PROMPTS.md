# Prompty do Codex

## Prompt startowy — etap 01

Skopiuj poniższy prompt do Codex w katalogu repozytorium:

```text
You are a senior full-stack engineer implementing WebCrawler Studio: a working Polish-language website crawler and graph analysis app inspired by WebSPHINX and Win Web Crawler.

Read AGENTS.md, IMPLEMENTATION_PLAN.md, docs/ARCHITECTURE.md, docs/API.md and docs/LAB_REQUIREMENTS.md before coding.

Stack: Python 3.12+, FastAPI, SQLAlchemy 2, Alembic, SQLite, httpx, BeautifulSoup4; React, TypeScript, Vite, Tailwind CSS, shadcn/ui, Cytoscape.js, Recharts; pytest, Vitest, Playwright.

The eventual application must support URL crawling; BFS/DFS; depth and page limits; server/web scope; hyperlinks/images+hyperlinks/all links; optional external URLs and one-page mode; URL/title/description/keywords/body extraction; directed graph and metrics; session storage; configurable CSV export; experiment comparison; Polish UI; laboratory reporting.

Implement real features, not mockups. Respect robots.txt, throttle requests, enforce SSRF protection, validate redirects, and apply strict crawl limits. Do not fabricate statistics.

Implement ONLY Phase 01: Project Bootstrap as described in IMPLEMENTATION_PLAN.md. Create functioning backend/frontend, development configuration, database and health check, Docker Compose, .env.example and accurate README. Run and report tests/checks. Do not proceed to Phase 02.
```

## Prompty kolejnych etapów

Wysyłaj po jednym, po weryfikacji poprzedniego etapu.

### Etap 02 — Database & Sessions

```text
Continue WebCrawler Studio. Read AGENTS.md and project docs. Implement ONLY Phase 02 (Database & Sessions) from IMPLEMENTATION_PLAN.md. Add migrations, CRUD API, configuration validation, persistence tests. Run checks, fix failures, document results and stop.
```

### Etap 03 — Crawler Engine

```text
Continue WebCrawler Studio. Read AGENTS.md and project docs. Implement ONLY Phase 03 (Crawler Engine) from IMPLEMENTATION_PLAN.md. Implement real BFS/DFS, scopes, link types, limits, cancel/progress, robots.txt, throttling and robust SSRF protections including redirects and resolved addresses. Use deterministic integration tests. Report checks and stop.
```

### Etap 04 — HTML & Metadata Extraction

```text
Continue WebCrawler Studio. Read AGENTS.md and project docs. Implement ONLY Phase 04 (HTML & Metadata Extraction). Parse and persist title, description, keywords, body, URL and discovered links. Test relative URLs, base href, encoding, malformed HTML and differing link-type modes. Report checks and stop.
```

### Etap 05 — Interactive Graph

```text
Continue WebCrawler Studio. Read AGENTS.md and project docs. Implement ONLY Phase 05 (Interactive Graph). Expose actual stored nodes, edges and per-page statistics. Implement interactive Cytoscape.js display, levels, zoom, search and page detail panel. Verify against fixture data and stop.
```

### Etap 06 — Data Explorer & CSV

```text
Continue WebCrawler Studio. Read AGENTS.md and project docs. Implement ONLY Phase 06 (Data Explorer & CSV). Add table filtering and configurable field/separator export, proper Unicode encoding and formula-injection protection. Add round-trip tests; stop after reporting results.
```

### Etap 07 — Experiments & Comparison

```text
Continue WebCrawler Studio. Read AGENTS.md and project docs. Implement ONLY Phase 07 (Experiments & Comparison). Support multi-configuration sessions and quantitative comparison of URL sets, graph edges, metadata, depth, counts and timing. Ensure interpretations are backed by measurements. Add deterministic tests and stop.
```

### Etap 08 — Reports, QA & Documentation

```text
Continue WebCrawler Studio. Read AGENTS.md and project docs. Implement ONLY Phase 08 (Reports, QA & Documentation). Complete reporting and dashboard, provide deterministic test website with >=20 pages and >=3 depth levels, cover all eight laboratory requirements, run backend/frontend/E2E checks, update README with tested commands and report any residual limitations.
```

## Kontrola po każdej fazie

Poproś Codex o wykaz: zaimplementowanych funkcji, zmodyfikowanych plików, uruchomionych poleceń testowych, rezultatów, znanych ryzyk i rzeczy pozostawionych na później.
