# Etap 07 — Experiments & Comparison

Data: 2026-10-19. Zakres: wyłącznie etap 07. Bez commita.

## Zaimplementowane funkcje

- Atomowe tworzenie Experiment i 2–4 niezależnych queued sesji wspólnego start URL, z pełnymi konfiguracjami i stabilną kolejnością created_at/id. Lista/paginacja, szczegóły, start grupy i usunięcie grupy. Istniejące modele/relacje wystarczają, bez nowej migracji.
- Start wariantów przez dotychczasowy CrawlManager: ta sama ochrona SSRF, robots, throttling, limity i anulowanie. Running/terminal nie startują drugi raz. Zajęci pracownicy dają jawne błędy per wariant, queued pozostają do ręcznego ponowienia. Nie ma ukrytego schedulera ani automatycznego odtwarzania zadań po restarcie.
- Konfiguracje członków grupy są niezmienne także przed startem; SessionRead.configuration_locked pochodzi z relacji bazy, API blokuje PATCH, UI ukrywa edycję. Zwykłe queued sesje nadal edytowalne. Usunięcie grupy zachowuje sesje i aktywne zadania, a usunięcie sesji zachowuje grupę z pozostałymi członkami. Grupa z mniej niż dwiema sesjami ma incomplete.
- POST /api/compare porównuje 2–4 różne terminalne sesje o identycznym zapisanym znormalizowanym start URL, w jednym snapshotcie SQLite. Pierwsza sesja jest bazą, pozostałe porównywane względem niej. Można porównywać grupę lub istniejące niezależne sesje.
- Osobne zbiory wspólnych/unikalnych odkrytych URL i pobranych HTML. Tożsamość strony to normalized_url żądania, bez scalania po final_url. Typowana krawędź to source URL/target URL/kind, z oddzielną różnicą liczby wystąpień; nie opieramy porównania na różnych UUID dwóch sesji.
- Różnice pełnej treści title/description/keywords/body wspólnie pobranych stron przez SHA-256 UTF-8, długość i podgląd do 500 znaków. Null i pusty string są różne. Zmiana poza podglądem nadal jest wykrywana. Zapisana głębokość, kolejność prób, konfiguracja, dostępność pól i liczby błędów są pokazane jawnie.
- Czas to zapisany finished_at-started_at, bez wymyślania czasu dla brakujących timestampów. Liczniki ze zbiorów Page/Link, nie z deklarowanych parametrów ani testowych danych. Częściowe wyniki/limity/błędy są oznaczone.
- Bounded comparison: 20000 Page, 80000 Link, 64 MiB treści pól i budżet analizy 30 s, błędy 413/503 zamiast fałszywie kompletnej odpowiedzi. Listy mają dokładne total i wspólną partię offset/limit (domyślnie 25); metryki obejmują całość. Czytamy duże teksty po jednym rekordzie, zachowując skróty/podglądy, linki partiami.
- Polski interfejs Porównania: konfigurator 2–4 wariantów, lista eksperymentów, odczyt statusów i polling podczas pracy, start/retry, odnośniki do sesji/anulowania/grafu/danych, potwierdzenie usunięcia grupy i porównanie istniejących sesji. Recharts pokazuje osobno liczniki i sekundy z tabelą alternatywną, bez zastępowania null zerem.
- Obserwacje podają zmierzone wspólne/unikalne strony oraz zmienione metadane. Nie zakładamy różnych pełnych grafów BFS/DFS ani przyczynowości samych ustawień; nie wskazujemy automatycznie najlepszego wariantu. Nie wykonujemy funkcji raportu/dashboardu etapu 08.

## Kontrole

Wszystkie CLI poza sandboxem. Testy używają zmigrowanych tymczasowych baz i kontrolowanej witryny TCP; nie opierają liczników na publicznym serwisie.

| Środowisko | Polecenie / scenariusz | Wynik |
|---|---|---|
| Windows, backend | uv run pytest -q | **304 passed**, 1 deprecjacja Starlette/httpx |
| Linux, Python 3.12, efemeryczny kontener | python -m pytest -q, źródła/testy read-only, pytest 9.1.1 | **304 passed**, ta sama deprecjacja |
| backend, nowe testy | uv run pytest tests/test_comparison.py -q --tb=short | **14 passed** |
| backend, regresja sesji podczas implementacji | uv run pytest tests/test_sessions.py -q | **83 passed** |
| backend | uv run ruff check .; uv run ruff format --check . | OK po formatowaniu, 40 plików |
| backend | uv run alembic check; uv lock --check | Brak różnic schematu, lock OK |
| frontend | npm test | **38 passed** |
| frontend | npm run build | TypeScript + Vite: OK, osobny fragment eksperymentów/Recharts |
| frontend | npm run test:e2e | **12 passed**, rzeczywisty backend, TCP i Chromium |
| frontend, nowe scenariusze | npx playwright test e2e/experiments.spec.ts | **2 passed** |
| frontend | npm audit | 0 podatności |
| Compose | docker compose up --build -d --wait | Oba obrazy zbudowane, oba serwisy healthy |
| kontener backendu | alembic current; alembic check | 0003_crawler (head), brak operacji |
| działający Compose | Własna grupa queued → GET → cancel bez crawlowania → compare pustych wyników → usunięcie grupy i sesji; frontend /experiments | PASS, brak sztucznego czasu/null zachowane, HTTP 200, dane smoke usunięte |
| repozytorium | git diff --check | OK |

Backend weryfikuje równy pełny graf BFS/DFS przy różnej kolejności, zbiory zmienione przez limit stron, głębokość, scope/follow external i tryby hiperłącza/obrazy/all links. Porównanie tego samego zapisu daje identyczny wynik także po restarcie aplikacji. Sprawdzane są null a pusty string, zmiana poza 500-znakowym podglądem, pełny skrót, duplikaty i różnice depth, dokładny czas z zapisanych timestampów, paginacja i niezmienne totals. Testy obejmują atomową walidację, konfiguracje, usunięcie/odblokowanie, incomplete, 404/409/422/413/503, częściowe wyniki, limit czterech pracowników, częściowy start/retry i brak zduplikowanych sesji/zadań.

Vitest sprawdza metryki API, czytelność różnic konfiguracji, literalny niezaufany HTML w metadanych, null, stronicowanie w zachowanej kolejności ID, retry i anulowanie odczytu. Renderer wykresu jest w tych jednostkowych testach zastąpiony; rzeczywisty Recharts sprawdza browser.

Playwright tworzy dwa warianty formularzem, uruchamia BFS/DFS z limitem trzech prób, czeka na zakończenie i pokazuje faktyczne różnice: tylko A ma /b, tylko B ma /a1 w pobranych HTML. Sprawdza SVG wykresów, sześć słupków liczników, rozwijane listy URL, reload i mobile 375 px bez przepełnienia całej strony. Drugi scenariusz porównuje dwie niezależne zapisane sesje hyperlinks/all_links i trzy dodatkowe typowane krawędzie. Zrzuty desktop/mobile obejrzane; tabele przewijają się lokalnie. Artefakty są w ignorowanym frontend/test-results/phase07-comparison-*.png.

## Poprawki podczas weryfikacji

- Wstępne uwagi Ruff i formatowanie poprawiono; generyczne listy Pydantic używają składni typów Pythona 3.12, sprawdzonej również na tej wersji.
- Pierwszy pełny E2E dał 11 passed / 1 failed: ogólny selektor SVG trafiał także w trzy ikony legendy. Test zawężono do dostępnej roli application właściwego wykresu i dodano sprawdzenie rzeczywistej liczby słupków. Nowe scenariusze 2/2, następnie pełne 12/12 przeszły.
- Dodano configuration_locked w odpowiedziach i UI, aby członkowie eksperymentu nie sugerowali możliwości zmiany konfiguracji przed startem. Semantyka usunięcia sesji/grupy pozostaje jawna i testowana.

## Ograniczenia i dalszy zakres

- Reprodukowalne są zapisane konfiguracje i analiza tego samego zapisu. Nowe crawle publicznej witryny mogą mieć inną treść i czas. Środowisko, robots, opóźnienia, współdzielony limiter i obciążenie wpływają na pomiar; nie wyciągamy rankingu ani przyczynowych wniosków bez dodatkowego eksperymentu.
- Porównanie wymaga terminalnych sesji tego samego start URL; nie jest widokiem live. Grupy startują queued warianty w miarę wolnych miejsc, bez rezerwowania wszystkich miejsc atomowo. Błędy startu są widoczne, ponowienie ręczne. Zakończonych sesji nie uruchamia się drugi raz.
- Usunięcie sesji usuwa jej członkostwo, więc grupa może stać się incomplete; etykiety A–D dotyczą pozostałej kolejności. UUID identyfikuje wariant. Nie zapisujemy osobnego nieusuwalnego manifestu ani kopii wyników po usunięciu sesji.
- Pary to baza A względem pozostałych, nie wszystkie pary. Typowana krawędź uwzględnia kind, unikalne relacje grafu etapu 05 nie uwzględniają kind — oba kontrakty są opisane. Zmiany is_followed nie są odrębnym zbiorem krawędzi; wpływ podążania widać w próbach i pobranych stronach.
- Metadane porównywane dla wspólnie pobranego HTML; skróty nie są testem semantycznej równości treści. Do odpowiedzi trafia jawny podgląd, pełne body nadal w API stron. Zmiany HTTP status/content-type/encoding nie są osobną listą zmian metadanych; rekordy źródłowe pozostają dostępne.
- Czas 30 s jest sprawdzany podczas analizy stron, nie jest przerywającym timeoutem pojedynczego SELECT. Duże zapytania/snapshoty wymagają zasobów; brak benchmarku największego dopuszczalnego porównania na każdym sprzęcie. Listy są stronicowane, pełne totals zachowane.
- Recharts jest zależnością frontendową; lazy import nie obciąża pierwszego widoku przeglądu/grafu. Pozostaje znane ostrzeżenie Starlette/httpx, pośredniego whatwg-encoding i Windows asyncio WinError 10054 w E2E. Wszystkie końcowe kontrole przechodzą.
- Nie rozpoczęto etapu 08. Nie wykonano commita.

## Pliki dodane lub zmienione

- projekt/IMPLEMENTATION_PLAN.md
- projekt/README.md
- projekt/backend/app/api.py
- projekt/backend/app/main.py
- projekt/backend/app/models.py
- projekt/backend/app/schemas.py
- projekt/backend/app/comparison.py
- projekt/backend/app/experiments.py
- projekt/backend/tests/test_comparison.py
- projekt/docs/API.md
- projekt/docs/ARCHITECTURE.md
- projekt/docs/PHASE_07.md
- projekt/frontend/package.json
- projekt/frontend/package-lock.json
- projekt/frontend/src/App.tsx
- projekt/frontend/src/App.test.tsx
- projekt/frontend/src/pages/sessions.tsx
- projekt/frontend/src/types/sessions.ts
- projekt/frontend/src/pages/experiments.tsx
- projekt/frontend/src/lib/comparison-api.ts
- projekt/frontend/src/components/comparison-results.tsx
- projekt/frontend/src/components/comparison-results.test.tsx
- projekt/frontend/e2e/experiments.spec.ts

Źródło techniczne: [oficjalne API Recharts BarChart](https://recharts.github.io/en-US/api/BarChart/).
