# Etap 02 — Database & Sessions

Data: 2026-10-19. Zakres: wyłącznie etap 02. Bez wykonywania crawlowania.

## Zaimplementowane funkcje

- Typowane modele SQLAlchemy: `CrawlSession`, `CrawlConfig`, `Page`, `Link`, `Experiment` oraz członkostwa wiele-do-wielu `experiment_sessions`.
- Migracja `0002_sessions`: indeksy, unikalność stron w sesji, CHECK enumów/liczników/limitów, FK i kaskady. Definicja migracji nie importuje bieżących klas modeli.
- Linki zachowują każde wystąpienie. FK zabraniają powiązań stron różnych sesji. Usunięcie strony docelowej zachowuje URL linku; usunięcie sesji zachowuje inne sesje i rekord eksperymentu.
- POST/GET/list/PATCH/DELETE sesji, paginacja, filtr statusu, transakcyjny zapis konfiguracji, czasy UTC, statusy queued/running/completed/failed/cancelled. Nowa sesja jest queued, z zerowymi licznikami i bez rozpoczęcia/zakończenia.
- Edycja tylko queued; blokada usuwania running; przewidywalne błędy 404/409/422/503 bez danych wejściowych i szczegółów bazy.
- Walidacja URL HTTP/HTTPS, publicznych literałów IP i nazw hostów, standardowych portów, poświadczeń i znaków sterujących. Ścisłe typy i skończone limity konfiguracji.
- Polski formularz/lista/szczegóły/edycja/usuwanie, filtr i paginacja. Potwierdzenie usunięcia, stany puste/ładowania/błędów, retry i anulowanie odczytów. Bez fikcyjnych wyników.
- Wersja 0.2.0, dokumentacja API/architektury/uruchomienia, aktualizacja istniejącej lokalnej bazy i wolumenu Compose.

## Weryfikacja

Wszystkie polecenia CLI poza sandboxem.

| Katalog | Polecenie / scenariusz | Wynik |
|---|---|---|
| backend | `uv run pytest` | **113 passed**, 1 ostrzeżenie Starlette/httpx |
| backend | `uv run ruff check .`, `uv run ruff format --check .` | OK |
| backend | `uv lock --check` | OK |
| backend | `uv run alembic upgrade head`, `uv run alembic check` | 0002_sessions; brak różnic schematu |
| backend | `uv export --no-dev --no-emit-project --no-hashes --output-file requirements.lock` | Eksport bez zmiany zależności produkcyjnych |
| frontend | `npm run build` | TypeScript + Vite: OK |
| frontend | `npm test` | **18 passed** |
| frontend | `npm run test:e2e` | **4 passed**, rzeczywisty backend i Chromium |
| frontend | `npm audit` | 0 podatności |
| projekt | `docker compose up --build -d --wait` | Oba obrazy zbudowane, obie usługi healthy |
| projekt | POST sesji → restart backendu → GET | PASS: to samo ID, DFS i głębokość 2; własna sesja smoke usunięta po sprawdzeniu |
| kontener backendu | `alembic current`, `alembic check` | 0002_sessions (head), brak nowych operacji |
| Chromium | Formularz/lista 1440×1100 i 375×812; szczegóły mobilne | Zrzuty obejrzane; brak przepełnienia poziomego |
| repozytorium | `git diff --check` | OK |

Backend używa tymczasowych baz migrowanych przez Alembic. Testy obejmują CRUD, wartości domyślne, pełny zestaw opcji, granice i typy, niepoprawne URL, atomowość błędnej edycji, wszystkie statusy, 404/409/422/503, CORS mutacji, paginację, restart aplikacji, downgrade/upgrade, zgodność metadanych, unikalność i kaskady przy załadowanych/niezaładowanych relacjach. Potwierdzają brak endpointów start/cancel.

Frontend używa fixture wyłącznie w plikach testów. Playwright tworzy rzeczywistą sesję w osobnej bazie `data/e2e.db`, odświeża stronę, edytuje konfigurację, sprawdza API i usuwa sesję z porządkowaniem w finally. Osobny test sprawdza prywatny URL. Testy regresji etapu 01 pozostają aktywne.

Pierwszy E2E: 3 passed / 1 failed przez dokładne dopasowanie getByLabel dla selecta. Zmieniono selektor na rolę combobox z nazwą; ponowny przebieg: 4 passed. Wstępne błędy Ruff poprawiono. Wywołanie npm z katalogu bez package.json dało ENOENT; właściwe polecenia z frontend przeszły.

## Ograniczenia i dalszy zakres

- Nie rozpoczęto etapu 03: brak BFS/DFS, DNS/HTTP do start URL, start/cancel, SSE i automatycznych przejść statusów. Konfiguracja jest zapisywana; crawler jeszcze nie wykonuje jej limitów.
- Walidacja URL przy zapisie nie zastępuje ochrony SSRF. DNS, rzeczywiste adresy połączeń, redirecty, robots i rate limiting należą do etapu 03.
- Page, Link i Experiment mają modele/migrację/relacje; ich API i ekrany wyników pozostają w kolejnych etapach. Testowe rekordy nie są kopiowane do aplikacji użytkownika.
- PATCH zastępuje cały przekazany blok config, uzupełniając pominięte pola domyślnymi wartościami. Brak config zachowuje poprzedni blok. UI przesyła cały formularz.
- Health sprawdza połączenie, nie wersję schematu. Lokalnie wymagane alembic upgrade head; Compose wykonuje to przy starcie.
- Pozostaje ostrzeżenie deprecjacji Starlette TestClient/httpx. Instalacja npm zgłasza deprecjację pośredniego whatwg-encoding; audit czysty.
- Compose pozostaje środowiskiem deweloperskim. Bez commita.

## Pliki dodane lub zmienione

Ścieżki względem korzenia repozytorium:

- `projekt/IMPLEMENTATION_PLAN.md`
- `projekt/README.md`
- `projekt/backend/app/api.py`
- `projekt/backend/app/database.py`
- `projekt/backend/app/errors.py`
- `projekt/backend/app/main.py`
- `projekt/backend/app/models.py`
- `projekt/backend/app/schemas.py`
- `projekt/backend/migrations/env.py`
- `projekt/backend/migrations/versions/0002_sessions_sessions.py`
- `projekt/backend/pyproject.toml`
- `projekt/backend/tests/conftest.py`
- `projekt/backend/tests/test_bootstrap.py`
- `projekt/backend/tests/test_models.py`
- `projekt/backend/tests/test_sessions.py`
- `projekt/backend/uv.lock`
- `projekt/docs/API.md`
- `projekt/docs/ARCHITECTURE.md`
- `projekt/docs/PHASE_02.md`
- `projekt/frontend/e2e/sessions.spec.ts`
- `projekt/frontend/package-lock.json`
- `projekt/frontend/package.json`
- `projekt/frontend/src/App.test.tsx`
- `projekt/frontend/src/App.tsx`
- `projekt/frontend/src/components/session-form.tsx`
- `projekt/frontend/src/lib/sessions-api.ts`
- `projekt/frontend/src/pages/sessions.test.tsx`
- `projekt/frontend/src/pages/sessions.tsx`
- `projekt/frontend/src/types/sessions.ts`

## Odnośniki techniczne

[SQLAlchemy Cascades](https://docs.sqlalchemy.org/en/21/orm/cascades.html), [Alembic Autogenerate / check](https://alembic.sqlalchemy.org/en/latest/autogenerate.html).
