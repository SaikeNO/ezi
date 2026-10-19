# Etap 05 — Interactive Graph

Data: 2026-10-19. Zakres: wyłącznie etap 05. Bez commita.

## Funkcje

- GET `/api/sessions/{uuid}/graph` i `/stats`: typowane odpowiedzi, walidacja UUID, 404 i jawny limit wizualizacji 413. Tylko odczyt zapisanych danych; żadnych nowych żądań do witryn.
- Spójny snapshot SQLite obejmuje status, strony i linki. Graf/stats nie polegają na licznikach sesji. Jawne BEGIN działa także przy legacy transaction mode Pythona 3.12. Schemat nie wymaga migracji.
- Page jako węzeł, pozostałe docelowe URL jako stabilne węzły target:SHA256. Każda krawędź ma zapisany rodzaj i osobne ID. Duplikaty/pętle pozostają; ten sam URL hiperłącza i obrazu daje jeden cel grafu. Niepobrane i zewnętrzne strony oraz zasoby są widoczne, bez udawania pobranego HTML.
- Statystyki: odkryte/pobrane/błędne strony, pozostałe cele, osiągnięta i odkryta głębokość, wszystkie wystąpienia oraz unikalne relacje, linki wewnętrzne/zewnętrzne, liczby linków i różnych celów strony startowej/podstron, stopnie wystąpień i różnych sąsiadów, agregacja per depth i per page.
- Cytoscape.js: kierunek krawędzi, poziomy/kolory głębokości, rozróżnienie stron/zasobów/błędów/zewnętrznych, zoom, pan, przesuwanie węzłów, fit, wybór przez canvas i dostępną tekstową listę. URL i title można wyszukiwać bez zmiany metryk. Panel pokazuje zapisane metadane/body i in/out-degree, jako niezaufany tekst.
- `/graph` wybiera sesję z paginacją; `/graph/{id}` pokazuje jej wyniki. Szczegóły sesji mają odnośnik do grafu. Rzeczywiste stany loading/empty/error/retry; odświeżanie na żądanie zachowuje stabilność widoku podczas pracy użytkownika.
- Cytoscape jest ładowany w osobnym fragmencie aplikacji dopiero przy wejściu na graf. Instancja i ResizeObserver są sprzątane po unmount; odczyty są anulowane po zmianie widoku/wyboru.
- Do wizualizacji maks. 5000 węzłów i 20000 wystąpień linków. Większe wyniki dają jasny komunikat i pełne statystyki, bez ukrytego ucięcia. Preflight sprawdza duże zbiory przed budowaniem grafu; linki są odczytywane partiami, stats nie buduje listy krawędzi. Zapytania nie pobierają body/description/keywords; title ograniczone do 500 znaków w SQL, pełna wersja w API szczegółów.

## Kontrole

Wszystkie polecenia CLI poza sandboxem. Brak testów zależnych od zmiennej treści publicznych witryn.

| Środowisko | Polecenie / scenariusz | Wynik |
|---|---|---|
| Windows, backend | `uv run pytest -q` | **236 passed**, 1 deprecjacja Starlette/httpx |
| Linux, Python 3.12, efemeryczny kontener | `python -m pytest -q`, źródła/testy zamontowane read-only, pytest 9.1.1 | **236 passed**, ta sama deprecjacja |
| backend, końcowe asercje limitów | `uv run pytest tests/test_graph.py -q` | **5 passed** |
| backend | `uv run ruff check .`; `uv run ruff format --check .` | OK, 35 plików |
| backend | `uv run alembic check`; `uv lock --check` | OK, brak różnic schematu i zależności |
| frontend | `npm test` | **29 passed** |
| frontend | `npm run build` | TypeScript + Vite: OK; osobny lazy chunk grafu |
| frontend | `npm run test:e2e` | **8 passed**, Chromium, rzeczywisty backend i witryna TCP |
| frontend, poprawka mobilnej tabeli | `npx playwright test e2e/graph.spec.ts` | **2 passed** |
| frontend | `npm audit` | 0 podatności |
| Compose | `docker compose up --build -d --wait` i aktualizacje backend/frontend | Obrazy zbudowane, oba serwisy healthy |
| kontener backendu | `alembic current`; `alembic check` | 0003_crawler (head), brak operacji |
| działający Compose | Utworzenie własnej queued sesji → graph/stats → usunięcie; frontend `/graph` | PASS, puste wyniki zgodne, HTTP 200, własna sesja usunięta |
| repozytorium | `git diff --check` | OK |

Testy backendu porównują graf i stats z zapisanym crawlem BFS oraz DFS, w tym konkretne oczekiwane liczniki i niezależne sumy stopni/krawędzi. Sprawdzają cykle, duplikaty, samo-pętle, różne rodzaje linków do jednego URL, zasoby, błędy HTTP, cele zewnętrzne, głębokość odkrytą a pobraną, izolację sesji, puste dane, restart, usunięcie i oba limity wizualizacji. Deterministyczna witryna 21 HTML stron osiąga trzy przejścia od startu; zapisany graf ma 21 węzłów i 26 wystąpień linków.

Vitest sprawdza odczyt metryk z API, wyszukiwanie i wybór, literalne wyświetlanie niezaufanego title/body, brak żądania metadanych dla zasobu, retry, empty, null depth, fallback stats po 413 i anulowanie odczytu. Renderer jest w tych testach zastąpiony; rzeczywisty Cytoscape sprawdza Playwright.

E2E potwierdza liczbę rzeczywistych węzłów/krawędzi renderera wobec API, kliknięcie węzła na canvasie, metadane, przyciski zoom in/out i fit, pan myszą, wyszukanie zasobu, wybór węzła na mobile, odświeżenie, puste dane i 404 po usunięciu. Zrzuty desktop i 375 px mobile obejrzano; poprawiono ciasną tabelę głębokości przez lokalne przewijanie. Brak przepełnienia szerokości całej strony. Zrzuty są w ignorowanym `frontend/test-results/phase05-graph-*.png`.

## Problemy wykryte i poprawione

- Pierwsze kliknięcie testowe używało pozycji sprzed ustabilizowania viewportu. Test przewija do canvasu i dopasowuje graf przed odczytem współrzędnych; rzeczywiste kliknięcie nadal jest wymagane. Pierwszy pełny E2E: 7 passed / 1 failed, po korekcie 8 passed.
- Przy optymalizacji odczytu omyłkowo użyto iteratora dla listy stron wymagającej len. Testy natychmiast wykryły błąd; strony pozostają listą, linki strumieniem. Pełne regresje Windows/Linux po poprawce przeszły.
- Uwagi Ruff poprawiono. Dodanie testu canvasu ujawniło brak zawężenia typu NodeSingular w testach TypeScript; poprawiono typ. Duży wspólny bundle podzielono przez lazy import widoku grafu.
- Lokalny npm odrzucił przekazanie --grep przez npm run (EUNKNOWNCONFIG); właściwe polecenie bezpośrednie npx playwright test oraz pełne npm run test:e2e działają.

## Ograniczenia i dalszy zakres

- Graf/stats opisują zapisany snapshot, także częściowy. Nie obiecują pełnego pokrycia witryny. BFS/DFS określa kolejność pobierania, nie gwarantuje różnych pełnych zbiorów węzłów.
- Poziom celu bez Page to min(głębokość źródła + 1), wyłącznie do wizualizacji. Osiągnięta głębokość HTML i per-depth statystyki stron nie uwzględniają zasobów. Final_url nie scala różnych URL żądań.
- Preset układa zapisane poziomy; duże grafy mogą być gęste i wymagają zoom/search. Nie ma benchmarku maksymalnego grafu na każdym urządzeniu. Wyszukiwanie obejmuje URL i pierwsze 500 znaków title; lista pokazuje jawnie pierwsze 30 dopasowań. Metryki obejmują cały snapshot.
- Full stats dla największych dopuszczalnych sesji wymaga pamięci na węzły/zbiory sąsiadów. Limit wizualizacji nie ogranicza ani nie zmienia zapisanych wyników crawlowania.
- Pozostają ostrzeżenia Starlette/httpx, pośredniego whatwg-encoding i Windows asyncio WinError 10054 podczas zrywania połączeń E2E. Końcowe testy przechodzą. Compose nadal jest lokalnym środowiskiem deweloperskim.
- Etap 06 (tabelaryczny eksplorator i CSV), porównania i raporty nie zostały rozpoczęte. Nie wykonano commita.

## Pliki dodane lub zmienione

- `projekt/IMPLEMENTATION_PLAN.md`
- `projekt/README.md`
- `projekt/backend/app/api.py`
- `projekt/backend/app/graph.py`
- `projekt/backend/tests/test_graph.py`
- `projekt/docs/API.md`
- `projekt/docs/ARCHITECTURE.md`
- `projekt/docs/PHASE_05.md`
- `projekt/frontend/package.json`
- `projekt/frontend/package-lock.json`
- `projekt/frontend/src/App.tsx`
- `projekt/frontend/src/App.test.tsx`
- `projekt/frontend/src/lib/sessions-api.ts`
- `projekt/frontend/src/pages/sessions.tsx`
- `projekt/frontend/src/pages/graph.tsx`
- `projekt/frontend/src/pages/graph.test.tsx`
- `projekt/frontend/src/components/graph-canvas.tsx`
- `projekt/frontend/src/types/graph.ts`
- `projekt/frontend/e2e/graph.spec.ts`

Źródło techniczne: [oficjalna dokumentacja Cytoscape.js](https://js.cytoscape.org/).
