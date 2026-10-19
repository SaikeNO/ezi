# WebCrawler Studio

Polskojęzyczna aplikacja do badania struktury WWW. **Etap 02 ukończony:** działający szkielet aplikacji oraz zapisywanie, listowanie, odczyt, edycja i usuwanie sesji z konfiguracją w SQLite. Funkcje crawlowania nie są jeszcze dostępne.

## Uruchomienie w Dockerze

W katalogu `projekt/` (nie w nadrzędnym katalogu repozytorium):

```powershell
Copy-Item .env.example .env
docker compose up --build -d --wait
```

Nie nadpisuj istniejącego `.env` przy kolejnych uruchomieniach. Otwórz [aplikację](http://localhost:5173), [health](http://localhost:8000/health) lub [Swagger UI](http://localhost:8000/docs). Compose uruchamia migracje przed API i czeka na zdrowy backend. Obie usługi mają healthcheck. Frontend korzysta z serwera deweloperskiego Vite; konfiguracja służy do pracy lokalnej. Porty hosta są dostępne tylko na loopback.

```powershell
docker compose ps
docker compose logs backend frontend
docker compose down
```

SQLite znajduje się w nazwanym wolumenie `crawler-data`, w kontenerze pod `/app/data/webcrawler.db`. Zwykłe `down` zachowuje bazę. Nie używaj `down -v`, jeśli chcesz zachować dane. Zmiana kodu wymaga ponownego `up --build`; źródła nie są montowane do kontenerów.

## Uruchomienie lokalne

Wymagane: Python 3.12+, uv, Node.js 22.12+ z linii 22 lub 24 (ewentualnie >=26), npm. Sprawdzono Windows/Python 3.14.4/Node 22.23.2 oraz kontenery Linux/Python 3.12/Node 22. Jeśli Docker zajmuje porty 8000/5173, zatrzymaj go poleceniem `docker compose down`.

Z `projekt/`, skopiuj `.env.example` do `.env` jak wyżej. Terminal backendu:

```powershell
cd backend
uv sync --locked
uv run alembic upgrade head
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Drugi terminal, również startując z `projekt/`:

```powershell
cd frontend
npm ci
npm run dev
```

Wejdź na `http://localhost:5173`. Przerwij procesy przez Ctrl+C. Lokalne SQLite: `projekt/data/webcrawler.db`; ścieżki względne są liczone od katalogu `projekt/`, niezależnie od bieżącego katalogu procesu. API nie tworzy tabel domenowych przy starcie — schemat obsługuje Alembic. Migracja `0002_sessions` tworzy tabele sesji, konfiguracji, stron, linków, eksperymentów i ich członkostw. Po aktualizacji z etapu 01 wykonaj ponownie `uv run alembic upgrade head`; istniejący plik SQLite i wolumen pozostają zachowane.

## Praca z sesjami (etap 02)

Otwórz **Sesje**, podaj publiczny HTTP/HTTPS URL i wybierz konfigurację. **Utwórz sesję** zapisuje ją w SQLite i otwiera szczegóły. Można wrócić do listy, filtrować po statusie, przechodzić między stronami, edytować oczekującą konfigurację i usuwać sesję po potwierdzeniu. Odświeżenie strony lub restart backendu zachowuje zapis.

Sesje mają teraz status „Oczekująca”. Przycisk uruchamiania crawlera pojawi się dopiero w etapie 03. Bieżąca implementacja nie pobiera start URL ani nie generuje metryk. Parametry dodatkowe obejmują timeout, opóźnienie, limit czasu całej sesji, rozmiaru odpowiedzi, redirectów, współbieżność i robots.txt. Reguły walidacji i pełne przykłady kontraktów: [docs/API.md](docs/API.md).

W Swagger UI dostępne są POST/GET/PATCH/DELETE `/api/sessions`. PATCH edytuje wyłącznie sesję `queued` i zastępuje cały przekazany blok `config` (domyślne wartości uzupełniają pominięte pola). DELETE usuwa również wyniki tej sesji; nie jest dostępne dla statusu `running`.

## Konfiguracja

Wspólny plik `projekt/.env` czytają backend, Vite i Compose. Zmiany wymagają ponownego uruchomienia usług.

| Zmienna | Znaczenie |
|---|---|
| `DATABASE_URL` | SQLAlchemy URL do pliku SQLite; domyślnie `sqlite:///./data/webcrawler.db`. Compose używa stałej ścieżki wolumenu zamiast lokalnej wartości. |
| `CORS_ORIGINS` | Lista originów JSON; domyślnie localhost i 127.0.0.1 na porcie 5173. Bez wildcardów, ścieżek i danych logowania. |
| `VITE_API_BASE_URL` | Adres API widziany przez przeglądarkę, domyślnie `http://localhost:8000`. To publiczna konfiguracja — nie umieszczaj sekretów w zmiennych `VITE_*`. |

Frontend używa bezpośrednio REST API; sprawdza strukturę odpowiedzi, kończy żądanie po 5 sekundach i pozwala ponowić próbę. Stan bazy pochodzi z `SELECT 1` wykonywanego przez backend. Nie ma sztucznych metryk ani fikcyjnych sesji.

## Testy i build

Z `projekt/backend/`:

```powershell
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv lock --check
uv run alembic check
```

Z `projekt/frontend/`:

```powershell
npm test
npm run build
npm audit
npx playwright install chromium
npm run test:e2e
```

Playwright sam uruchamia rzeczywisty backend i frontend na osobnych portach **18000/15173**, z osobną bazą `projekt/data/e2e.db` i konfiguracją CORS. Nie wymaga zatrzymania Compose. Porty testowe muszą być wolne. Testy obejmują odczyt prawdziwego statusu SQLite, ponowienie, nawigację, odświeżenie podstrony, widok mobilny i niedostępność API. Etap 02 dodaje tworzenie, utrwalenie po odświeżeniu, edycję i usunięcie sesji oraz odrzucanie prywatnych URL.

Wyniki bieżącego etapu i pełna lista plików: [docs/PHASE_02.md](docs/PHASE_02.md); wcześniejszy raport: [etap 01](docs/PHASE_01.md). Backend: **113 testów OK**; frontend: **18 testów OK**; Playwright: **4 testy OK**. Build, Ruff i Compose sprawdzone. `npm audit`: 0 podatności.

## Struktura

- `backend/app/`: FastAPI, typowany health, konfiguracja i SQLAlchemy.
- `backend/migrations/`: Alembic i migracja bazowa.
- `backend/tests/`: testy API, CORS, konfiguracji i migracji.
- `frontend/src/`: React/TypeScript, Tailwind v4, komponent Button shadcn/ui, polski interfejs.
- `frontend/e2e/`: Playwright, integracja z rzeczywistym API.
- `docker-compose.yml`, `.env.example`: lokalne środowisko.

Zależności backendu przypina `uv.lock`; eksport produkcyjny `requirements.lock` jest używany przez Docker. Po zmianie zależności odtwórz go w `backend/` przez `uv export --no-dev --no-emit-project --no-hashes --output-file requirements.lock`. Frontend przypina `package-lock.json`.

## Dokumentacja i dalszy zakres

- [Reguły projektu](../AGENTS.md)
- [Plan etapów](IMPLEMENTATION_PLAN.md)
- [Prompty](CODEX_PROMPTS.md)
- [Architektura](docs/ARCHITECTURE.md)
- [API](docs/API.md)
- [Wymagania laboratorium](docs/LAB_REQUIREMENTS.md)

Crawler, ochrona transportu SSRF/robots/rate limiting, ekstrakcja, graf, CSV, porównania i raporty pozostają w etapach 03–08. Cytoscape.js i Recharts będą dodane wraz z funkcjami, które ich potrzebują. Nawigacja do przyszłych sekcji wyświetla jawne informacje o ich planowanym etapie. Nie wykonuje żadnych żądań crawlowania.

Konfiguracja UI oparta na oficjalnych instrukcjach [Tailwind + Vite](https://tailwindcss.com/docs/installation/using-vite) i [shadcn/ui + Vite](https://ui.shadcn.com/docs/installation/vite). Button wygenerowano CLI shadcn, następnie dopasowano importy do lokalnego `cn` i `@radix-ui/react-slot`.
