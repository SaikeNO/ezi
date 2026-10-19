# Etap 01 — raport wdrożenia

Data: 2026-10-18. Zakres: wyłącznie Project Bootstrap.

## Funkcje

- Monorepo FastAPI + React/TypeScript/Vite, Tailwind v4 i Button shadcn/ui.
- Typowany `GET /health`, rzeczywiste `SELECT 1` do SQLite, status 503 przy błędzie bazy.
- SQLAlchemy 2, baza metadanych, sesje i konfiguracja połączeń, migracja bazowa Alembic bez modeli etapu 02.
- Walidacja SQLite URL i originów CORS, wspólny `.env.example`, stabilne ścieżki bazy.
- Polski responsywny interfejs, nawigacja, ładowanie/status/błąd/ponowienie, limit czasu żądania i anulowanie po odmontowaniu.
- Docker Compose, healthcheck obu usług, migracja przy starcie, trwały wolumen SQLite.
- Lockfile zależności backendu/frontend, testy jednostkowe/integracyjne/przeglądarkowe.

## Weryfikacja

Polecenia wykonywano poza sandboxem, z katalogów wskazanych poniżej.

| Katalog | Polecenie lub kontrola | Wynik |
|---|---|---|
| `backend/` | `uv sync --locked`, `uv lock --check` | OK |
| `backend/` | `uv run pytest` | 16 passed |
| `backend/` | `uv run ruff check .`, `uv run ruff format --check .` | OK |
| `backend/` | `uv run alembic upgrade head`, `uv run alembic current` | `0001_bootstrap (head)` |
| `frontend/` | `npm install`, `npx shadcn@latest add button --yes` | OK; importy Button dopasowane do lokalnych modułów |
| `frontend/` | `npm test` | 10 passed |
| `frontend/` | `npm run build`, `npm run typecheck` | OK |
| `frontend/` | `npm audit` | 0 podatności |
| `frontend/` | `npx playwright install chromium`, `npm run test:e2e` | 2 passed; rzeczywiste API + osobne porty 18000/15173 |
| `projekt/` | `docker compose config --quiet` | OK |
| `projekt/` | `docker compose build`, `docker compose up --build -d --wait` | Oba obrazy zbudowane, oba kontenery healthy; `npm ci` sprawdzone podczas budowania |
| `projekt/` | HTTP `/health` i frontend przez hosta | HTTP 200; `{"status":"ok","database":"ok"}` |
| `projekt/` | Restart backendu i ponowny odczyt bazy/API | Nadal `0001_bootstrap`, health OK |
| przeglądarka Chromium | Widoki 1440×1000 i 375×812 | Zrzuty obejrzane, układ poprawny |
| repozytorium | `git diff --check` | OK |

Testy backendu obejmują sprawną/niedostępną bazę, CORS, błędną konfigurację, `.env`, niezależność katalogu roboczego, upgrade/downgrade/ponowny upgrade oraz trwałość historii migracji. Testy UI obejmują rzeczywiste stany odpowiedzi, niepoprawne JSON/statusy, błędy sieci, retry, timeout, anulowanie i nawigację. Playwright sprawdza również odświeżenie podstrony i brak poziomego przepełnienia na telefonie.

Początkowe błędy Ruff i testu serializacji ścieżki Windows poprawiono; ponowne kontrole przeszły. Początkowe zależności Vitest miały 3 zgłoszone podatności — aktualizacja Vitest/Vite dała 0. Błędne wywołanie `npm run test:e2e` z nadrzędnego katalogu bez `package.json` zakończyło się ENOENT; uruchomienie z `frontend/` przeszło. Końcowa kontrola wykryła i poprawiła kodowanie istniejących dokumentów; pliki zapisano jako UTF-8.

## Ograniczenia i dalszy zakres

- Nie ma jeszcze modeli/CRUD sesji, crawlera, grafu, ekstrakcji, CSV, eksperymentów ani raportów. Nie rozpoczęto etapu 02.
- Health potwierdza połączenie SQLite, nie wersję schematu. Migracje uruchamia się osobno lokalnie, automatycznie w Compose.
- Compose jest środowiskiem deweloperskim: frontend działa przez Vite, brak wdrożenia produkcyjnego/TLS.
- Pytest zgłasza ostrzeżenie Starlette o przyszłym zastąpieniu integracji TestClient/httpx przez httpx2. Wszystkie testy przechodzą; wymagany httpx pozostaje zależnością projektu.
- npm zgłasza deprecjację pośredniego `whatwg-encoding`; audit nie wykazuje podatności. Lokalny npm 12 ostrzegał także o zablokowanym postinstall esbuild; build i testy działają, instalacja w Dockerze również przeszła.
- Przyszłe zabezpieczenia crawlera (SSRF, DNS rebinding, robots, limity) pozostają wymaganiami etapu 03. W etapie 01 nie istnieje endpoint pobierający podane przez użytkownika adresy.

## Pliki dodane lub zmienione

Ścieżki względem korzenia repozytorium:

- `.gitignore`
- `projekt/.env.example`
- `projekt/IMPLEMENTATION_PLAN.md`
- `projekt/README.md`
- `projekt/backend/.dockerignore`
- `projekt/backend/Dockerfile`
- `projekt/backend/alembic.ini`
- `projekt/backend/app/__init__.py`
- `projekt/backend/app/core/__init__.py`
- `projekt/backend/app/core/config.py`
- `projekt/backend/app/database.py`
- `projekt/backend/app/main.py`
- `projekt/backend/migrations/env.py`
- `projekt/backend/migrations/script.py.mako`
- `projekt/backend/migrations/versions/0001_bootstrap.py`
- `projekt/backend/pyproject.toml`
- `projekt/backend/requirements.lock`
- `projekt/backend/tests/test_bootstrap.py`
- `projekt/backend/uv.lock`
- `projekt/docker-compose.yml`
- `projekt/docs/API.md`
- `projekt/docs/ARCHITECTURE.md`
- `projekt/docs/PHASE_01.md`
- `projekt/frontend/.dockerignore`
- `projekt/frontend/Dockerfile`
- `projekt/frontend/components.json`
- `projekt/frontend/e2e/bootstrap.spec.ts`
- `projekt/frontend/index.html`
- `projekt/frontend/package-lock.json`
- `projekt/frontend/package.json`
- `projekt/frontend/playwright.config.ts`
- `projekt/frontend/src/App.test.tsx`
- `projekt/frontend/src/App.tsx`
- `projekt/frontend/src/components/health-panel.tsx`
- `projekt/frontend/src/components/ui/button.tsx`
- `projekt/frontend/src/index.css`
- `projekt/frontend/src/lib/api.test.ts`
- `projekt/frontend/src/lib/api.ts`
- `projekt/frontend/src/lib/utils.ts`
- `projekt/frontend/src/main.tsx`
- `projekt/frontend/src/test/setup.ts`
- `projekt/frontend/tsconfig.json`
- `projekt/frontend/vite.config.ts`
