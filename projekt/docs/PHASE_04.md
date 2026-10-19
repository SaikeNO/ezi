# Etap 04 — HTML & Metadata Extraction

Data: 2026-10-19. Zakres: wyłącznie etap 04. Bez commita.

## Zaimplementowane funkcje

- Jeden ograniczony przebieg HTMLParser zbiera title, meta description, meta keywords, tekst body i typowane odnośniki. BeautifulSoup rozpoznaje deklaracje kodowania. Nie jest budowany drugi, nieograniczony DOM.
- Zapis do istniejących kolumn Page: URL żądania i końcowy URL, status HTTP, MIME, użyte kodowanie, tytuł, opis, keywords, body. Link zachowuje każde wystąpienie, rodzaj i docelowy URL; zasoby nie stają się pobranymi stronami HTML.
- Encje HTML, normalizacja whitespace, pierwszy title/meta content, null dla brakujących pól i pusty string dla jawnie pustych. Body pomija head/title/script/style/template/noscript i komentarze; fragmenty bez body również dają tekst.
- Kodowanie BOM > HTTP charset > deklaracja HTML > UTF-8. Obsługa m.in. UTF-8/16/32, Windows-1250 i ISO-8859-2, nieznanych kodeków i błędnych bajtów. Fetcher przekazuje tylko faktyczny charset HTTP, więc domyślne UTF-8 biblioteki nie zasłania deklaracji meta.
- Pierwszy base[href], także pusty; relatywne/absolutne/protocol-relative URL, fragmenty i powtórzenia. Niedozwolone schematy są pomijane. Pełna lista obsługiwanych tagów i trybów znajduje się w ARCHITECTURE.md.
- Typowane, stronicowane API listy stron, szczegółów z body i linków źródłowej strony. Walidacja UUID/paginacji, 404, izolacja sesji, puste wyniki i zachowanie duplikatów. Lista nie ładuje body z bazy.
- Metadane są zatwierdzane przed rozwijaniem linków, dzięki czemu globalny limit odkrywania nie usuwa już przeanalizowanej treści. Dotychczasowe limity parsera, współpracujące anulowanie i ochrona sieci pozostają aktywne.
- Brak zmiany schematu: wymagane kolumny istnieją od migracji 0002. Alembic check potwierdza zgodność. Starsze wyniki nie są uzupełniane wstecz.

## Uruchomione kontrole

Wszystkie polecenia CLI poza sandboxem. Testy ekstrakcji korzystają z lokalnych fixture HTML i kontrolowanej witryny TCP; nie wymagają publicznej sieci.

| Środowisko | Polecenie / scenariusz | Wynik |
|---|---|---|
| Windows, backend | `uv run pytest -q` | **231 passed**, 1 deprecjacja Starlette/httpx |
| Linux, Python 3.12, efemeryczny kontener | `python -m pytest -q`, tests zamontowane tylko do odczytu, pytest 9.1.1 | **231 passed**, ta sama deprecjacja |
| backend | `uv run ruff check .`; `uv run ruff format --check .` | OK, 33 pliki |
| backend | `uv run alembic upgrade head`; `uv run alembic check`; `uv lock --check` | OK, brak różnic schematu i zależności |
| frontend | `npm run build` | TypeScript i Vite: OK |
| frontend | `npm test` | **23 passed** |
| frontend | `npm run test:e2e` | **6 passed**, Chromium i rzeczywisty backend |
| Compose | `docker compose up --build -d --wait backend` | Obraz zbudowany, backend healthy |
| Compose | `alembic current`; `alembic check`; HTTP health/OpenAPI | 0003_crawler (head), brak zmian, health OK, trzy endpointy stron dostępne |
| repozytorium | `git diff --check` | OK |

Nowe testy sprawdzają wszystkie trzy tryby selekcji i rodzaje odnośników, względny/absolutny/pusty/niepoprawny base, Unicode/encje, priorytety kodowania, nieobsługiwany kodek, nieprawidłowe bajty, brakujące/puste metadane, błędny HTML i ciągłość słów/encji między fragmentami parsera. Integracja TCP sprawdza także HTTP charset, meta bez charset HTTP, XHTML, przekierowanie i końcowy URL, zachowanie częściowej treści po limicie odkrywania, zapis SQLite i identyczne odczyty metadanych/linków po restarcie aplikacji. Regresja nadal obejmuje BFS/DFS, bezpieczeństwo, anulowanie i SSE.

Wstępne asercje etapu 03 oczekujące body=null zostały zaktualizowane. Błędnie umieszczoną asercję treści w teście odzyskiwania ręcznie utworzonej strony przeniesiono do testu limitów odkrywania; końcowy pełny przebieg przeszedł. `npm test -- --run` odrzucono przez lokalny npm (EUNKNOWNCONFIG); poprawne `npm test` przeszło. Początkowe uwagi Ruff usunięto.

## Ograniczenia i dalsze prace

- Parser nie wykonuje JS/CSS i nie odtwarza DOM przeglądarki. Nie obiecujemy identycznej naprawy dowolnego błędnego HTML ani tekstu widocznego po renderowaniu CSS. Nie zgadujemy statystycznie kodowania.
- Bez srcset, CSS url() i linków generowanych przez JavaScript. Dotychczasowe limity odpowiedzi, tagów, tokenów, linków i czasu mogą bezpiecznie odrzucić dokument. Błąd samego parsera zachowuje HTTP/error, bez częściowych metadanych.
- API służy do odczytu zapisanych wyników. Ekran eksploratora, filtrowanie/wyszukiwanie i CSV pozostają w etapie 06; graf w 05, porównania/raporty w 07–08. Frontend nie został rozszerzony o te późniejsze funkcje.
- Starsze sesje zachowują null w niewypełnionych polach. Dla nowych danych utwórz nową sesję. Metadane traktowane są jako niezaufany tekst, nigdy jako wykonywalny HTML.
- Znane ostrzeżenie Starlette TestClient/httpx pozostaje. Windows asyncio podczas zrywania połączeń E2E loguje WinError 10054; wszystkie sześć scenariuszy przechodzi.
- Etapu 05 nie rozpoczęto. Nie wykonano commita.

## Pliki dodane lub zmienione

Ścieżki od korzenia repozytorium:

- `projekt/IMPLEMENTATION_PLAN.md`
- `projekt/README.md`
- `projekt/backend/app/api.py`
- `projekt/backend/app/crawler/discovery.py`
- `projekt/backend/app/crawler/engine.py`
- `projekt/backend/app/crawler/fetcher.py`
- `projekt/backend/app/schemas.py`
- `projekt/backend/tests/fixtures/extraction.html`
- `projekt/backend/tests/site_fixture.py`
- `projekt/backend/tests/test_crawler_engine.py`
- `projekt/backend/tests/test_extraction.py`
- `projekt/backend/tests/test_pages_api.py`
- `projekt/docs/API.md`
- `projekt/docs/ARCHITECTURE.md`
- `projekt/docs/PHASE_04.md`
