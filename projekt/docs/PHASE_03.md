# Etap 03 — Crawler Engine

Data: 2026-10-19. Zakres: wyłącznie etap 03. Bez commita.

## Działające funkcje

- Rzeczywisty BFS/FIFO i DFS/LIFO, kolejność DOM, start na depth 0, normalizacja URL, deduplikacja i cykle. DFS rozwija odnośniki ponownie po odkryciu krótszej ścieżki, bez ponownego pobrania tej strony.
- Limity głębokości, prób stron, czasu sesji/żądania, odpowiedzi, redirectów, odkrywania i analizy. Server/web, podążanie za zewnętrznymi, process_one_page i trzy grupy odnośników.
- Zapis wszystkich wystąpień linków. Zasoby nie-HTML pozostają celami, nie są pobierane jako strony. W tym etapie analizowana jest nawigacja, bez title/description/keywords/body.
- Ochrona SSRF: wspólna walidacja URL, wszystkie zwrócone A/AAAA, odrzucenie mieszanego zbioru publicznych/prywatnych IP, przypięcie TCP do sprawdzonego IP, kontrola faktycznego partnera przed HTTP i przy I/O, zachowanie SNI i weryfikacji TLS, osobna kontrola każdego redirectu. Wyłączone proxy z otoczenia i przenoszenie cookies.
- Domyślne robots, bezpieczna polityka błędów, identyfikator WebCrawlerStudio, najdłuższe reguły Allow/Disallow, wildcard i końcowe $, Crawl-delay/Request-rate. Wspólne odstępy po zakończeniu żądania obejmują DNS/odpowiedź, robots i redirecty.
- Start/cancel, idempotencja dla powtórzonych operacji, serializacja zmian SQLite, maksymalnie cztery aktywne sesje, blokada jednego procesu na DB. Przerwanie aktywnego HTTP i parsera, częściowe wyniki, odzyskanie statusu po restarcie.
- Migracja 0003_crawler: dziennik zdarzeń, wersja/UA/powód zakończenia/link_count, final_url. Zachowuje istniejące wyniki; downgrade sprawdzony z istniejącymi stronami i linkami.
- Trwałe SSE z kursorem i reconnect. Zdarzenia są publikowane po zatwierdzeniu opisanego kroku. Polski interfejs start/cancel, rzeczywiste liczniki i powód zakończenia; REST uzupełnia SSE po przerwaniu połączenia.
- Docker przekazuje sygnał do procesu API przez exec; Uvicorn ma 5 s grace, a kontener 30 s. Ręczny restart korzysta z --timeout 30.

## Uruchomione kontrole

Wszystkie CLI poza sandboxem. Testy nie wymagają publicznej witryny.

| Środowisko | Polecenie / scenariusz | Wynik |
|---|---|---|
| Windows, Python 3.14 | uv run pytest | 199 passed, 1 ostrzeżenie zależności |
| Windows, po poprawce buforowania między wersjami | uv run pytest tests/test_crawler_engine.py -q | 28 passed |
| Linux, Python 3.12, efemeryczny kontener | python -m pytest -q z testami i źródłem zamontowanymi tylko do odczytu | 199 passed |
| backend | uv run ruff check .; uv run ruff format --check . | OK |
| backend | uv run alembic upgrade head; uv run alembic check; uv lock --check | 0003_crawler, brak różnic schematu, lock poprawny |
| backend | uv export --no-dev --no-emit-project --no-hashes --output-file requirements.lock | OK, httpcore przypięte jako bezpośrednia zależność |
| frontend | npm run build | TypeScript + Vite: OK |
| frontend | npm test | 23 passed |
| frontend | npm run test:e2e | 6 passed, Chromium i kontrolowana rzeczywista witryna HTTP |
| frontend | npm audit | 0 podatności |
| Compose | docker compose up --build -d --wait | Oba obrazy zbudowane, obie usługi healthy |
| kontener backendu | alembic current; alembic check | 0003_crawler (head), brak nowych operacji |
| Compose, aktywne SSE | Restart --timeout 30 z pracującą sesją i otwartym strumieniem | PASS: cancelled/server_shutdown, zachowany rekord strony, sprzątnięta własna sesja |
| Chromium | Zrzuty desktop oraz 375 px mobile | Obejrzane, bez przepełnienia i kolizji elementów |
| repozytorium | git diff --check | OK |
| produkcyjny transport w Compose | Bounded HTTPS smoke do example.com, robots włączone, max_pages 1 | completed, 1 HTML, 0 błędów, 0 hiperłączy w odebranej wersji strony; trwałe SSE i liczniki zgodne |

Smoke był pojedynczą, ograniczoną weryfikacją połączenia, nie deterministycznym testem publicznej treści. Własna sesja została usunięta. Żadne fixture ani stałe oczekiwane liczniki nie są dostarczane do aplikacji produkcyjnej.

Testy obejmują m.in. BFS/DFS na kontrolowanym TCP, głębokość i krótsze ścieżki DFS, scope/follow external, cykle/duplikaty, selekcję zasobów, błędy pojedynczych stron, przekierowania, robots, opóźnienia, limity czasu/rozmiaru/odkrywania, anulowanie bez następnych żądań, trwałość/replay SSE, konkurencyjny start, blokadę edycji/usuwania, limit pracowników, wyłączenie serwera i odzyskanie przerwanego zadania.

Testy transportu sprawdzają DNS z prywatnym rekordem, rebinding, pinning IP, fałszywy lub brakujący rzeczywisty adres połączenia, brak HTTP przed weryfikacją partnera, SNI/certyfikaty, prywatny DNS po redirect, obfuskowane/specjalne IP, kompresję, body limit i błędy robots. Parser ma niezależny od buforowania biblioteki licznik nieprzetworzonego wejścia.

## Wykryte i poprawione problemy podczas weryfikacji

- Dopasowanie robots do zakodowanych znaków URL było niespójne: ujednolicono kodowanie ścieżki i wzorca.
- Spacing wyłącznie przed DNS pozwalałby zgrupować HTTP po wolnym lookup. Slot origin obejmuje całe żądanie i odstęp po jego zakończeniu.
- Python 3.12 buforuje fragmenty HTML inaczej niż 3.14. Kontrola samego rawdata nie mierzyła całego oczekującego wejścia; zastąpiono ją licznikiem znaków podanych i skonsumowanych.
- Pierwsze uruchomienie pytest jako skryptu w obrazie załadowało zainstalowany wheel zamiast źródła i nie znalazło konfiguracji migracji. Poprawny harness używa python -m pytest z katalogu backendu. Następny przebieg wykrył różnicę parsera; po poprawce wszystkie 199 testów Linux przeszły.
- Wstępne kontrole Ruff poprawiono. Pierwszy przebieg browser testów przeszedł; kolejne uruchomienia przy równoległym obciążeniu miały timeout startu, potem 3/6 timeoutów testów. Jeden worker, 120 s startu i 60 s testu dały końcowe 6/6. Asercje funkcjonalne pozostały bez zmian.

- Pierwszy test restartu z otwartym SSE miał zbyt krótkie okno Docker CLI: odzyskanie failed/interrupted zachowało częściowy rekord. Ustawiono 30 s grace kontenera i jawne --timeout 30; powtórzony test potwierdził cancelled/server_shutdown.

## Ograniczenia i dalszy zakres

- Pobieranie w sesji jest sekwencyjne. Concurrency jest górną granicą, efektywnie 1; gwarantuje przewidywalne BFS/DFS. Nie deklarujemy równoległości odpowiadającej wartości konfiguracji.
- Jedna instancja API na plik SQLite. Nie ma wznowienia frontier po awarii: pozostają częściowe wyniki i failed/interrupted. Zwykłe wyłączenie zapisuje cancelled/server_shutdown.
- Restrykcyjna polityka błędów robots, kompresji i limitów może bezpiecznie pominąć część witryn. Różne URL przekierowujące na ten sam dokument mogą wymagać osobnych prób.
- Stan terminalny oznacza zakończenie zaplanowanej pracy lub limit, nie pełne pokrycie dowolnej witryny. Znaczenia liczników i is_followed są jawnie opisane w API.md.
- Nie rozpoczęto etapu 04: brak ekstrakcji title/meta/body i endpointu eksploratora stron. Nie ma jeszcze interaktywnego grafu, eksportu CSV, porównania ani raportów laboratoryjnych.
- Pozostaje deprecjacja Starlette TestClient/httpx i pośredniego whatwg-encoding. Windows asyncio przy zrywaniu połączeń testowych może logować niekrytyczny WinError 10054; końcowe testy przechodzą.
- Compose pozostaje środowiskiem deweloperskim.

## Odnośniki techniczne

[HTTPX transports](https://www.python-httpx.org/advanced/transports/), [httpcore network backends](https://www.encode.io/httpcore/network-backends/), [Python ipaddress](https://docs.python.org/3/library/ipaddress.html).

## Pliki dodane lub zmienione

Ścieżki od korzenia repozytorium:

- `projekt/IMPLEMENTATION_PLAN.md`
- `projekt/README.md`
- `projekt/backend/Dockerfile`
- `projekt/backend/app/api.py`
- `projekt/backend/app/crawler/__init__.py`
- `projekt/backend/app/crawler/discovery.py`
- `projekt/backend/app/crawler/engine.py`
- `projekt/backend/app/crawler/events.py`
- `projekt/backend/app/crawler/fetcher.py`
- `projekt/backend/app/crawler/manager.py`
- `projekt/backend/app/crawler/network.py`
- `projekt/backend/app/crawler/ownership.py`
- `projekt/backend/app/crawler/robots.py`
- `projekt/backend/app/crawler/urls.py`
- `projekt/backend/app/main.py`
- `projekt/backend/app/models.py`
- `projekt/backend/app/schemas.py`
- `projekt/backend/migrations/versions/0003_crawler.py`
- `projekt/backend/pyproject.toml`
- `projekt/backend/requirements.lock`
- `projekt/backend/tests/conftest.py`
- `projekt/backend/tests/e2e_app.py`
- `projekt/backend/tests/site_fixture.py`
- `projekt/backend/tests/test_crawler_engine.py`
- `projekt/backend/tests/test_crawler_security.py`
- `projekt/backend/tests/test_models.py`
- `projekt/backend/tests/test_sessions.py`
- `projekt/backend/uv.lock`
- `projekt/docker-compose.yml`
- `projekt/docs/API.md`
- `projekt/docs/ARCHITECTURE.md`
- `projekt/docs/PHASE_03.md`
- `projekt/frontend/e2e/crawler.spec.ts`
- `projekt/frontend/package-lock.json`
- `projekt/frontend/package.json`
- `projekt/frontend/playwright.config.ts`
- `projekt/frontend/src/App.tsx`
- `projekt/frontend/src/components/crawl-controls.test.tsx`
- `projekt/frontend/src/components/crawl-controls.tsx`
- `projekt/frontend/src/lib/sessions-api.ts`
- `projekt/frontend/src/pages/sessions.test.tsx`
- `projekt/frontend/src/pages/sessions.tsx`
- `projekt/frontend/src/types/sessions.ts`
