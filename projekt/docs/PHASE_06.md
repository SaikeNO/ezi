# Etap 06 — Data Explorer & CSV

Data: 2026-10-19. Zakres: wyłącznie etap 06. Bez commita.

## Funkcje

- Eksplorator /data i /data/{uuid}: wybór sesji z paginacją, tabela 10 rekordów, pełne metadane/body po wyborze strony, puste/błędne wyniki, ponowienie i ręczne odświeżanie. Odnośnik z sesji oraz menu Dane i CSV.
- Wspólne filtry listy i CSV: fragment URL/title/description/keywords, depth, pobrany HTML, błąd strony i HTTP status. Unicode casefold obejmuje m.in. polskie litery; %/_ są dosłowne, zapytania parametryzowane. Body nie jest przeszukiwane. Każda lista count/items jest jednym snapshotem SQLite.
- GET /api/sessions/{uuid}/export: wybrane i uporządkowane pola, separatory comma/semicolon/tab, opcjonalny BOM UTF-8 (domyślnie true), poprawny Content-Disposition/Length i format błędów. Pusty zbiór daje nagłówek. Wspiera wszystkie statusy sesji i eksportuje wszystkie pasujące strony, niezależnie od paginacji tabeli.
- Pola: URL, Keyword, Title, Description, Body, Original URL, Final URL, Depth, HTTP Status, Content-Type, Encoding i Error. Domyślnie URL oraz Keyword. Checkboxy zachowują kolejność zaznaczenia, UI jawnie pokazuje kolejność i zakres zastosowanych filtrów.
- csv.writer zachowuje znaki polskie, cudzysłowy, separatory, TAB i nowe linie wewnątrz komórek; CRLF oddziela rekordy. Null i pusty string stają się pustą komórką. Baza pozostaje bez zmian.
- Ochrona formuł we wszystkich eksportowanych komórkach: apostrof przed oryginalną treścią dla =/+/-/@ oraz odpowiedników pełnej szerokości, również po whitespace i znakach sterujących/formatach Unicode. Wiodący TAB/CR/LF także jest zabezpieczany. Quoting CSV zapobiega tworzeniu dodatkowych komórek przez cudzysłowy/separatory. Brak opcji wyłączenia ochrony.
- Plik przygotowany przed HTTP 200 w SpooledTemporaryFile (1 MiB w RAM, potem dysk), odczyt wyłącznie wybranych kolumn po jednym rekordzie, limit 64 MiB, budżet 30 s sprawdzany między rekordami. Przekroczenie daje 413/503 JSON, bez pobierania uciętego pliku. Snapshot jest zwalniany przed sieciowym przesyłaniem. Zamknięcie pliku po sukcesie/wyjątku/przerwaniu.
- Frontend sprawdza odpowiedź przed zapisem pliku, pokazuje błąd/retry, umożliwia anulowanie i przerywa żądania po opuszczeniu widoku; object URL jest zwalniany. Dane witryny renderowane jako tekst. Widok ładowany osobno, bez dodatkowych zależności.
- Nie ma zmiany schematu ani migracji: istniejące Page wystarczają. casefold jest funkcją rejestrowaną przy każdym połączeniu aplikacji, nie kolumną bazy.

## Kontrole

Wszystkie polecenia CLI poza sandboxem. Fixture wyłącznie w testach; nie są dostarczane jako wyniki aplikacji.

| Środowisko | Polecenie / scenariusz | Wynik |
|---|---|---|
| Windows, backend | uv run pytest -q | **290 passed**, 1 deprecjacja Starlette/httpx |
| Linux, Python 3.12, efemeryczny kontener | python -m pytest -q, źródła/testy read-only, pytest 9.1.1 | **290 passed**, ta sama deprecjacja |
| backend, początkowe nowe testy | uv run pytest tests/test_explorer.py -q | **53 passed**; następnie dodano test pozostałych pól do pełnego przebiegu |
| backend | uv run ruff check .; uv run ruff format --check . | OK, 37 plików |
| backend | uv run alembic check; uv lock --check | Brak różnic schematu, lock OK |
| frontend | npm test | **34 passed** |
| frontend | npm run build | TypeScript + Vite: OK, osobny fragment eksploratora |
| frontend | npm run test:e2e | **10 passed**, Chromium, rzeczywisty backend i witryna TCP |
| frontend | npm audit | 0 podatności |
| Compose | docker compose up --build -d --wait | Oba serwisy zbudowane i healthy |
| kontener backendu | alembic current; alembic check | 0003_crawler (head), brak operacji |
| działający Compose | Własna queued sesja → filtrowana lista/CSV średnik bez BOM → usunięcie; frontend /data | PASS, nagłówek URL;Keyword i CRLF zgodne, HTTP 200, własna sesja usunięta |
| repozytorium | git diff --check | OK |

Testy eksportu pokrywają round-trip przez csv.reader dla trzech separatorów i BOM on/off, kolejność i wszystkie mapowania pól, polskie litery, przecinki/średniki/TAB, cytowanie, LF/CRLF wewnątrz komórki, null, formuły i ukryte prefiksy, puste pliki, filtry, paginację a pełny eksport, izolację sesji, restart, 404/422/413/503 i poprawne nagłówki. Używają rzeczywiście zmigrowanych baz SQLite.

Vitest sprawdza filtry serwerowe, reset offsetu, literalny HTML, wybór kolejności/separatora/BOM, odróżnienie formularza od zastosowanych filtrów, blokadę braku pól, błędy/retry i anulowanie pobierania. Istniejące testy sesji/crawlera/grafu pozostają aktywne.

Playwright uruchamia prawdziwy crawl 13-stronicowej witryny /csv, przechodzi przez szczegóły sesji do eksploratora, paginuje, odczytuje body/metadane, filtruje ZAŻÓŁĆ, pobiera plik i sprawdza jego faktyczne bajty/BOM/nazwę, średniki, quoting polskiego title, apostrof przed =1+1 i brak odfiltrowanych URL. Drugi scenariusz sprawdza chooser, pusty wynik i błąd pobrania usuniętej sesji. Zrzuty desktop/375 px obejrzane, bez przepełnienia całej strony; tabela przewija się lokalnie. Zrzuty: ignorowane frontend/test-results/phase06-explorer-*.png.

## Wykryte i poprawione problemy

- Wstępne uwagi Ruff poprawiono. Pierwszy build po dodaniu testów odrzucił opcję exact z Playwright przeniesioną do Testing Library; usunięto nieobsługiwaną opcję, końcowy build i 34 testy przeszły.
- Dodano zamknięcie przygotowanego pliku także przy błędzie zwalniania transakcji. OpenAPI jawnie opisuje binarną odpowiedź text/csv.
- Dane zaimportowane historycznie nie są ponownie pobierane. Eksport zachowuje zapisane wartości, poza jawną ochroną formuł i reprezentacją null.

## Ograniczenia i dalszy zakres

- CSV nie odróżnia null i pustego tekstu. Apostrof ochronny może być widoczny w czytniku tekstowym; jest zamierzoną zmianą wartości eksportowanej, nie bazy.
- Import arkusza wymaga UTF-8 i właściwego separatora. Automatyczne rozpoznanie separatora zależy od programu/locale. Sprawdzono round-trip i rzeczywiste pobranie w Chromium; nie wykonywano ręcznej walidacji w Microsoft Excel.
- Budżet przygotowania jest sprawdzany między rekordami, nie przerywa długiego pojedynczego zapytania SQL w połowie. Przy dużych metadanych wyszukiwanie wykonuje skan; brak indeksu pełnotekstowego. Plik ma jawny limit 64 MiB i nie jest potajemnie przycinany.
- Snapshot eksportu może różnić się od poprzedniej strony tabeli przy aktywnym crawlerze. Formularz filtrów wymaga Zastosuj; nowe wejście na widok przywraca domyślne ustawienia, bez zapisu preferencji w bazie/localStorage.
- CSV obejmuje Page, nie osobne wiersze zasobów lub krawędzi Link. Pełny graf/linki pozostają dostępne w API poprzednich etapów.
- Pozostaje deprecjacja Starlette/httpx i znany Windows asyncio WinError 10054 podczas zrywania połączeń E2E; testy przechodzą. Compose nadal jest środowiskiem lokalnym.
- Etap 07 i raporty laboratoryjne etapu 08 nie zostały rozpoczęte. Nie wykonano commita.

## Pliki dodane lub zmienione

- projekt/IMPLEMENTATION_PLAN.md
- projekt/README.md
- projekt/backend/app/api.py
- projekt/backend/app/database.py
- projekt/backend/app/explorer.py
- projekt/backend/tests/site_fixture.py
- projekt/backend/tests/test_explorer.py
- projekt/docs/API.md
- projekt/docs/ARCHITECTURE.md
- projekt/docs/PHASE_06.md
- projekt/frontend/src/App.tsx
- projekt/frontend/src/lib/sessions-api.ts
- projekt/frontend/src/lib/explorer-api.ts
- projekt/frontend/src/pages/sessions.tsx
- projekt/frontend/src/pages/explorer.tsx
- projekt/frontend/src/pages/explorer.test.tsx
- projekt/frontend/e2e/explorer.spec.ts
