# Etap 08 — Reports, QA & Documentation

Ukończono 2026-10-22. Zakres ograniczony do etapu 08; bez commita i bez nowych etapów.

## Dostarczone zachowanie

- Dashboard całej bazy: statusy, odkryte Page, odebrane HTML, strony z błędem, Link i pięć najnowszych sesji. Jeden jawny snapshot SQLite; brak danych i awaria mają oddzielne stany. Liczniki nie korzystają z fixture ani z potencjalnie nieaktualnych liczników CrawlSession.
- Raport HTML jednej sesji: konfiguracja, ID/status/stop/błąd/wersja/UA, rzeczywisty czas lub brak, metryki grafu, poziomy, stopnie i pokrycie metadanych. Obsługuje także pustą/aktywną/częściową sesję. Limit grafu zwraca błąd przed publikacją pliku.
- Raport HTML 2–4 porównywanych sesji: zapisane pomiary, konfiguracje i zmiany parametrów, pokrycie metadanych, tabele wspólnych/unikalnych URL/krawędzi, obserwacje oraz rozwijane szczegóły JSON z różnicami treści/głębokości/krotności/kolejności. Używa istniejącego silnika compare i jego budżetów, nie pobiera witryn ponownie.
- Samodzielny HTML do otwarcia offline, CSS do druku i przewijane tabele mobilne. Escapowanie wszystkich niezaufanych wartości, nagłówki CSP/nosniff/no-store/attachment. Pobieranie obsługuje błędy, anulowanie, wyjście z widoku i zwolnienie object URL.
- Deterministyczna witryna: 22 poprawne wewnętrzne HTML (root + 21 podstron) na głębokościach 0–3, dodatkowo zewnętrzny HTML, 503, duplikat, cykle, zasoby i zróżnicowane metadane. Prawdziwy TCP/HTTP w izolacji testowej; produkcyjna polityka SSRF i obraz Docker pozostają bez opcji dostępu do loopback.
- Instrukcja użytkownika, aktualne API/architektura/README i macierz dowodów ośmiu punktów I.1–II.8. Historyczne Source WebSite/Dirs i URL/MetaTag mają jawną interpretację, bez deklaracji pełnej zgodności z dawną aplikacją.

## Faktyczne wyniki kontroli

Środowisko: Windows, Python 3.14.4, Node 22.23.2, npm 12.1.0, uv 0.11.11. Komendy uruchamiane poza sandboxem, zgodnie z instrukcją użytkownika.

| Katalog / komenda | Wynik |
|---|---|
| backend: `uv sync --locked` | PASS; 33 zależności sprawdzone |
| backend: `uv run alembic upgrade head` | PASS; istniejący schemat aktualny; także osobna DB laboratorium |
| backend: `uv run pytest` | **315 passed**, 1 ostrzeżenie, końcowy przebieg 86.43 s |
| backend: `uv run pytest tests/test_reporting.py -q` | **11 passed**; pełny lab, dashboard, statusy, XSS, błędy i limity, restart |
| backend: `uv run ruff check .` | PASS |
| backend: `uv run ruff format --check .` | PASS, 43 pliki |
| backend: `uv lock --check` | PASS |
| backend: `uv run alembic check` | PASS, brak nowych operacji migracji |
| frontend: `npm ci` | PASS po zatrzymaniu Vite; 211 zainstalowanych pakietów, audyt 212 |
| frontend: `npm test` | **45 passed**, 9 plików; po świeżej instalacji |
| frontend: `npm run build` | PASS (TypeScript + Vite); po świeżej instalacji |
| frontend: `npm audit` | PASS, **0 vulnerabilities**; także audyt przy npm ci |
| frontend: `npm run test:e2e` | **14 passed**, końcowy przebieg 42.7 s; Chromium, rzeczywisty backend i serwer HTTP |
| projekt: `docker compose config --quiet` | PASS; Docker daemon odpowiada (29.8.2) |
| `git diff --check` | PASS |
| Standardowe uruchomienie 8000/5173 | PASS, `/health`: status/database ok, `/api/dashboard`: rzeczywista pusta baza, frontend HTTP 200 |
| Ręczne laboratorium: API 18008 / UI 15178 | PASS uruchomienie/migracja/health i HTTP 200; crawl tej samej aplikacji/transportu zweryfikowany w pytest/E2E |

Nie uruchamiano ponownie budowy/uruchomienia kontenerów Docker ani automatycznego PDF. Chromium był już zainstalowany; komendy instalacji przeglądarki nie powtarzano. Nie testowano importu przez natywną aplikację Excel; CSV zweryfikowano parserem i pobraniem w przeglądarce.

Pierwsze pełne uruchomienie frontendowych testów trafiło na timeout dynamicznego importu widoku porównań pod obciążeniem. Test otrzymał jawne oczekiwanie na import i końcowy pełny przebieg przeszedł. Pierwszy test pustego dashboardu w E2E błędnie zakładał brak sesji pozostawionych przez inne testy: zmieniono go na jawnie przechwyconą pustą odpowiedź. Faktycznie pustą bazę osobno sprawdza test backendu; normalne raporty i metryki E2E pochodzą z rzeczywistych crawlów.

Pierwsze `npm ci` przy działającym Vite otrzymało Windows EPERM na natywnej bibliotece lightningcss. Zatrzymano własny proces Vite, powtórzono instalację, wykonano build/testy i przywrócono aplikację. `npm.ps1` z npm 12 odrzucał argument `--host`; sprawdzona komenda Windows używa `npm.cmd run dev -- --host ...`. Ograniczenie automatycznej akceptacji zablokowało próbę odłączonego uruchomienia frontendu; logowana komenda pierwszoplanowa uruchomiła go poprawnie.

Ostrzeżenia zależności: Starlette TestClient sygnalizuje przyszłe odejście od httpx; zachowano wymagany stos httpx. npm zgłasza deprecated whatwg-encoding oraz blokadę skryptu postinstall esbuild przez lokalne ustawienia allowScripts. Nie zmieniano polityki instalacji; esbuild, build i testy działają z zainstalowanym pakietem binarnym. Playwright wypisuje ostrzeżenie NO_COLOR/FORCE_COLOR; nie wpływa na wyniki. Brak nieudanych kontroli w końcowych przebiegach.

## Dowody laboratoryjne i QA wizualne

Pełny test pięciu konfiguracji mierzy, zamiast seedować wyniki: 22 HTML/depth 3, 39/40/42 linków dla hyperlinks/images/all_links, 11 HTML dla depth-2/web; BFS/DFS ma tę samą pełną zawartość i różną kolejność. Zapis i ponowne otwarcie aplikacji zachowują konfiguracje/wyniki. CSV ma żądany nagłówek, separator, polskie znaki i ochronę formuł. Szczegóły każdego z ośmiu wymagań: [ACCEPTANCE.md](ACCEPTANCE.md).

Playwright pobrał raporty sesji i porównania, odczytał rzeczywiste pliki HTML i renderował je w przeglądarce. Sprawdzono liczniki/Keyword, brak skryptów, mobilny brak overflow dokumentu, graf, CSV, odświeżenie oraz niedostępność dashboardu. Screenshoty wygenerowane w ignorowanym `frontend/test-results/` i obejrzane podczas QA:

- `phase08-report-desktop.png`, `phase08-report-mobile.png`;
- `phase08-comparison-desktop.png`, `phase08-comparison-mobile.png`;
- `phase08-dashboard-mobile.png`.

Na telefonie szerokie tabele raportu przewijają się we własnym kontenerze; nie ściskają tekstu do pojedynczych liter. Końcowe E2E sprawdziło także standardowe funkcje etapów 01–07. Timestampy/UUID/czasy na screenshotach są zmienne i nie stanowią stałych oczekiwań testów.

## Zmienione pliki

| Obszar | Pliki (względem `projekt/`) |
|---|---|
| Backend | `app` w `backend/`: nowy `reporting.py`, rejestracja routera w `main.py` |
| Backend QA | `backend/tests/lab_site.py`, `backend/tests/test_reporting.py`, `backend/tests/e2e_app.py` |
| Frontend | `frontend/src/App.tsx`, `frontend/src/pages/sessions.tsx`, `frontend/src/components/comparison-results.tsx`, nowe `components/dashboard.tsx`, `components/report-download.tsx` |
| Frontend QA | `frontend/src/App.test.tsx`, nowe `components/dashboard.test.tsx`, `components/report-download.test.tsx`, `frontend/e2e/reports.spec.ts` |
| Dokumentacja | `README.md`, `IMPLEMENTATION_PLAN.md`, `docs/API.md`, `docs/ARCHITECTURE.md`, `docs/LAB_REQUIREMENTS.md`, nowe `docs/USER_GUIDE.md`, `docs/ACCEPTANCE.md`, `docs/PHASE_08.md` |

Bez zmian schematu danych i zależności; migracja nie jest potrzebna dla wyłącznie odczytywanych projekcji. Lokalne bazy/logi, dist i screenshoty pozostają ignorowanymi artefaktami, nie źródłami wyników produkcyjnych.

## Pozostałe ograniczenia / prace odroczone

- PDF opcjonalny, bez endpointu/generatora; wydruk zależy od przeglądarki. Testy nie gwarantują układu PDF ani natywnego importu do konkretnego arkusza.
- Raport sesji: do 5000 węzłów / 20000 linków. Większy zbiór wymaga stats/CSV. Raport porównania: pierwsze 100 elementów każdej kategorii, pełne total, dalsze partie przez API; podglądy treści 500 znaków i pełne hashe. Budżety porównania 20000 Page / 80000 Link / 64 MiB / 30 s pozostają egzekwowane. Tabele konfiguracji i szczegóły JSON zachowują techniczne nazwy pól API.
- Dashboard sumuje rekordy we wszystkich sesjach i odświeża się ręcznie. Raport nie jest archiwizowany w DB; kolejne generowanie ma nowy timestamp. Trwałe konfiguracje/wyniki są źródłem odtwarzalności.
- Testowa witryna jest celowo izolowana; nie jest wdrożonym publicznym serwisem ani opcją produkcyjnego dostępu do prywatnej sieci. Żaden test nie gwarantuje powtarzalności zmiennej publicznej witryny.
- Dotychczasowe ograniczenia pozostają jawne: jeden worker SQLite, do czterech aktywnych sesji, sekwencyjne pobieranie per sesja, brak automatycznego wznowienia frontier po restarcie, brak wykonywania JS/renderowania CSS, restrykcyjne robots/limity/SSRF i ograniczony zestaw tagów ekstrakcji.
- Docker runtime i drugi system operacyjny nie zostały ponownie zweryfikowane w etapie 08; aktualne testy integracyjne/E2E wykonano lokalnie na Windows.

Żadna wymagana funkcja etapu 08 nie jest odroczona; dalsze rozszerzenia wymagają nowego zlecenia. Nie wykonano commita.
