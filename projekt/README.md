# WebCrawler Studio

Planowany projekt aplikacji webowej łączącej funkcjonalności wymagane w ćwiczeniach opartych na WebSPHINX i Win Web Crawler.

> **Status:** dokumentacja projektowa. Implementacja nie jest jeszcze gotowa.

## Cel

Aplikacja umożliwi eksplorację stron WWW, wizualizację grafu linków, analizę strategii BFS/DFS, zbieranie metadanych, zapis sesji, eksport CSV i porównanie wyników eksperymentów. Interfejs użytkownika będzie po polsku.

## Planowany stos

- **Frontend:** React, TypeScript, Vite, Tailwind CSS, shadcn/ui, Cytoscape.js, Recharts
- **Backend:** Python 3.12+, FastAPI, httpx, BeautifulSoup4
- **Dane:** SQLite, SQLAlchemy 2, Alembic
- **Postęp:** Server-Sent Events (SSE)
- **Testy:** pytest, Vitest, React Testing Library, Playwright

## Dokumenty

- [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) — harmonogram etapów i kryteria ukończenia
- [AGENTS.md](AGENTS.md) — reguły pracy Codex
- [CODEX_PROMPTS.md](CODEX_PROMPTS.md) — prompty do realizacji poszczególnych etapów
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — komponenty, dane, semantyka crawlera i bezpieczeństwo
- [docs/API.md](docs/API.md) — planowane kontrakty HTTP
- [docs/LAB_REQUIREMENTS.md](docs/LAB_REQUIREMENTS.md) — pokrycie wymagań laboratorium

## Zakładana struktura repozytorium

```text
webcrawler-studio/
├── backend/
│   ├── app/{api,core,crawler,models,schemas,services}/
│   ├── tests/
│   ├── pyproject.toml
│   └── alembic.ini
├── frontend/
│   ├── src/{components,pages,hooks,lib,types}/
│   └── package.json
├── docs/
├── AGENTS.md
├── CODEX_PROMPTS.md
├── IMPLEMENTATION_PLAN.md
├── docker-compose.yml
└── README.md
```

## Uruchomienie — po wdrożeniu etapu 01

Codex powinien uzupełnić ten rozdział o *zweryfikowane* instrukcje, wymagane wersje narzędzi, plik `.env.example`, polecenia startu usług, migracji i testów. Nie należy podawać nieprzetestowanych komend jako działających.

## Zasady

Crawler respektuje `robots.txt` domyślnie, ogranicza częstotliwość żądań, weryfikuje bezpieczeństwo adresów docelowych i przekierowań oraz nie pobiera sieci wewnętrznych. Dane testowe są oznaczone jako testowe; statystyki prawdziwych sesji zawsze wynikają z faktycznych pomiarów.
