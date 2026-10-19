# WebCrawler Studio

Polskojęzyczna aplikacja do badania struktury WWW. **Etap 07 ukończony:** crawler, metadane, graf, eksplorator/CSV oraz eksperymenty 2–4 konfiguracji i porównania rzeczywiście zapisanych wyników z wykresami. Raport laboratoryjny/dashboard pozostaje w etapie 08.

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
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 --timeout-graceful-shutdown 5
```

Drugi terminal, również startując z `projekt/`:

```powershell
cd frontend
npm ci
npm run dev
```

Wejdź na `http://localhost:5173`. Przerwij procesy przez Ctrl+C. Lokalne SQLite: `projekt/data/webcrawler.db`; ścieżki względne są liczone od katalogu `projekt/`, niezależnie od bieżącego katalogu procesu. API nie tworzy tabel domenowych przy starcie — schemat obsługuje Alembic. Migracje do `0003_crawler` tworzą schemat sesji/wyników oraz trwały dziennik postępu. Po aktualizacji z wcześniejszych etapów wykonaj ponownie `uv run alembic upgrade head`; istniejący plik SQLite i wolumen pozostają zachowane.

## Sesje i crawler (etap 03)

Otwórz **Sesje**, podaj publiczny HTTP/HTTPS URL, wybierz BFS/DFS, zakres i limity. **Utwórz sesję** zapisuje konfigurację i otwiera szczegóły. **Uruchom crawler** rozpoczyna pobieranie; **Anuluj sesję** przerywa aktywne żądanie i zachowuje wyniki. Liczniki i powód zakończenia pochodzą z backendu. UI odbiera SSE i podczas pracy dodatkowo ponawia REST, aby odtworzyć postęp po problemie z połączeniem.

Strona startowa ma głębokość 0. Zakres server podąża tylko po tym samym hoście; web wymaga włączenia zewnętrznych URL. process_one_page nadal zapisuje odnośniki strony startowej. Obrazy/CSS/JS są odkrywane jako cele grafu, ale nie pobierane jako HTML. Limit stron liczy próby, również zablokowane przez robots lub zakończone błędem; licznik „Pobrane HTML” oznacza rzeczywiste odpowiedzi HTML 2xx. To odrębne wielkości.

BFS/DFS w wersji 0.3 pobiera **sekwencyjnie**, aby zachować deterministyczną kolejność. concurrency jest górną granicą, efektywnie 1. Maksymalnie cztery aktywne sesje; współdzielą opóźnienia per origin. Większe limity konfiguracji nie wymuszają równoległości.

Domyślnie robots.txt jest respektowane. Błąd jego odczytu blokuje pobranie (404/410 oznacza brak reguł). Każdy URL/redirect i wszystkie odpowiedzi DNS są sprawdzane; połączenie jest przypięte do publicznego IP, rzeczywisty adres sprawdzany, TLS weryfikuje nazwę hosta. Nie ma przełącznika „zezwól na prywatną sieć”. Proxy z otoczenia są wyłączone. Niektóre witryny mogą zostać bezpiecznie pominięte przez restrykcyjną politykę robots, kompresji lub rozmiaru/analizy.

Oczekującą sesję można edytować/usunąć. Po starcie konfiguracja jest zamrożona; sesji running nie można usunąć. Zakończonego zadania nie uruchamia się ponownie — utwórz nową sesję. Po zwykłym wyłączeniu serwera zadania stają się cancelled/server_shutdown; po nagłym restarcie running otrzymują failed/interrupted, bez automatycznego wznowienia kolejki. Zapisane strony/linki/zdarzenia pozostają. Flaga timeout-graceful-shutdown 5 kończy również otwarte SSE podczas wyłączania, aby pracownik mógł zapisać stan i zwolnić blokadę. Compose daje kontenerowi 30 s; ręczny restart backendu wykonuj przez `docker compose restart --no-deps --timeout 30 backend`.

Uruchamiaj **jeden proces API na plik SQLite** (bez --workers >1 i bez współdzielenia DB przez drugi serwer). Blokada plikowa egzekwuje własność; sam plik .worker.lock może pozostać po zamknięciu — blokadę utrzymuje otwarty uchwyt OS, nie istnienie pliku. Wymagane SQLite 3.35+ dla natywnego downgrade kolumn. Szczegółowe limity, reguły linków, liczniki i SSE: [API](docs/API.md), [architektura](docs/ARCHITECTURE.md).

## Odczyt wyników ekstrakcji (etap 04)

W [Swagger UI](http://localhost:8000/docs) wywołaj `GET /api/sessions/{id}/pages`, potem `GET /api/sessions/{id}/pages/{page_id}` dla pełnego body. `GET /api/sessions/{id}/pages/{page_id}/links` zwraca odkryte odnośniki; obie listy przyjmują offset/limit (domyślnie 0/20, maksymalnie 100 elementów). Dane pochodzą wyłącznie z zapisanej sesji, także po restarcie. Lista stron nie zawiera body; szczegóły zawierają cały zapisany tekst. Starsze sesje zachowują null, bez automatycznego ponownego pobierania.

Parser obsługuje względne URL i pierwszy base href, encje, BOM/HTTP/meta charset oraz toleruje błędny HTML. Brak metadanych daje null, puste pole daje pusty string. Tekst body pomija head, skrypty, style i template/noscript; nie wykonuje kodu ani renderowania CSS. Dokładne reguły i obsługiwane tagi: [API](docs/API.md), [architektura](docs/ARCHITECTURE.md). Raport i pliki: [etap 04](docs/PHASE_04.md).

## Interaktywny graf (etap 05)

W szczegółach sesji wybierz **Otwórz graf sesji** lub otwórz **Graf witryny** w menu i wybierz zapisaną sesję. Graf pokazuje wszystkie zapisane strony oraz cele zasobów. Kolor odpowiada głębokości, koło oznacza Page, romb cel zasobu, jasny węzeł niepobrany HTML, czerwona obwódka błąd, a przerywany kontur/link cel zewnętrzny. Pociągnij tło, użyj kółka/gestu albo przycisków skali; **Dopasuj graf** przywraca cały widok.

Kliknij węzeł lub wyszukaj URL/tytuł i wybierz wynik z listy, aby odczytać metadane, body i in/out-degree. Wyszukiwanie nie zmienia statystyk. **Odśwież graf** pobiera nowy snapshot; widok nie przestawia się automatycznie podczas interakcji. Statystyki rozróżniają wystąpienia linków, unikalne relacje, pobrane HTML i odkryte strony. Zasoby nie zwiększają osiągniętej głębokości HTML.

Wizualizacja obsługuje do 5000 węzłów i 20000 wystąpień linków. Większy graf daje jawny komunikat oraz pełne statystyki, bez ukrytego ucinania danych. API: `GET /api/sessions/{id}/graph` i `/stats`; [kontrakt](docs/API.md), [semantyka](docs/ARCHITECTURE.md), [raport etapu 05](docs/PHASE_05.md). Nie rozpoczęto eksportu/eksploratora etapu 06.

## Dane i CSV (etap 06)

W menu **Dane i CSV** wybierz sesję albo użyj **Dane i eksport CSV** w jej szczegółach. Tabela pokazuje zapisane URL, Title, Keyword, Description, poziom i HTTP. Szczegóły odczytują pełne metadane/body. Filtruj po fragmencie URL/metadanych (także polskie litery, bez body), głębokości, pobranym HTML, błędzie i statusie HTTP; wybierz **Zastosuj filtry**. **Odśwież dane** pobiera nowszy zapis, a paginacja obejmuje po 10 stron.

W **Eksport CSV** zaznacz pola w żądanej kolejności, wybierz przecinek/średnik/tabulator i opcjonalny BOM UTF-8. Domyślnie pobierane są URL oraz Keyword z BOM. Eksport obejmuje **wszystkie dopasowania zastosowanych filtrów**, nie tylko widoczne 10 rekordów ani niezastosowany tekst formularza. CSV zachowuje polskie litery, cudzysłowy i nowe linie; komórki przypominające formuły dostają prefiks apostrofu. Puste komórki nie odróżniają null od pustego tekstu. Baza pozostaje bez zmian.

W arkuszu importuj jako UTF-8 z wybranym separatorem; BOM ułatwia rozpoznanie kodowania. Automatyczny separator zależy od ustawień regionalnych. Duże eksporty mają jawny limit 64 MiB i budżet przygotowania 30 s sprawdzany między rekordami — zawęź filtry lub ogranicz pola, gdy otrzymasz komunikat o limicie. Pobieranie można anulować; błędy nie są zapisywane jako CSV. [Kontrakt API](docs/API.md), [raport i lista plików etapu 06](docs/PHASE_06.md).

## Porównania i eksperymenty (etap 07)

W **Porównania** podaj nazwę, wspólny start URL i ustaw 2–4 warianty. Formularz udostępnia BFS/DFS, server/web, rodzaje linków, głębokość, limity i przełączniki. Domyślnie porównuje BFS z DFS. **Utwórz eksperyment** zapisuje niezależne queued sesje; **Uruchom oczekujące warianty** w szczegółach rozpoczyna pracę istniejącym bezpiecznym crawlerem. Konfiguracje wariantów pozostają niezmienne. Przy braku wolnych pracowników UI pokazuje błąd dla każdego niewystartowanego wariantu; ponów przyciskiem startu, gdy zwolni się miejsce. Anulowanie jest dostępne w szczegółach każdej sesji.

Po zakończeniu/anulowaniu wybierz **Porównaj warianty**. Można też wskazać 2–4 już istniejące terminalne sesje tego samego URL w sekcji **Porównaj istniejące sesje**. Pierwsza jest bazą A; kolejne są porównywane względem niej. Tabele/wykresy pokazują zapisane strony, linki, głębokość i zmierzony czas. Rozwijane listy pokazują wspólne/unikalne URL i typowane krawędzie, powtórzenia, różnice depth oraz metadanych. Podgląd dużego pola jest ograniczony do 500 znaków, lecz SHA-256 obejmuje całość; null i pusty string są rozróżniane. Listy mają partie po 25, z jawnym total.

Wyniki częściowe/limity/błędy są oznaczane; brak URL nie oznacza, że strona jest nieosiągalna. Pełne zbiory BFS/DFS mogą być identyczne. Czas obejmuje opóźnienia/robots/sieć/analizę i współdzielone zasoby, więc nie dowodzi przewagi algorytmu ani przyczyny zmiany treści. Nie wybieramy automatycznie najlepszego ustawienia.

Usunięcie grupy zachowuje sesje i nie zatrzymuje ich pracy; usunięcie sesji usuwa ją z grupy, a mniej niż dwa pozostałe warianty oznacza incomplete. Dane i konfiguracje przetrwają restart, ale aktywna kolejka crawlera nie jest automatycznie wznawiana. Porównanie ma limit łącznie 20000 Page, 80000 Link, 64 MiB treści i budżet analizy 30 s — duże wyniki dają jawny błąd. [API](docs/API.md), [semantyka](docs/ARCHITECTURE.md), [raport etapu 07](docs/PHASE_07.md).

## Zmienne środowiska

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

Playwright sam uruchamia rzeczywisty backend, kontrolowaną witrynę HTTP i frontend na osobnych portach **18000/15173**, z osobną bazą `projekt/data/e2e.db` i konfiguracją CORS. Testowy backend jest wstrzykiwany wyłącznie w `tests/e2e_app.py`; obraz produkcyjny nie zawiera katalogu tests ani takiej opcji środowiskowej. Nie wymaga zatrzymania Compose. Porty testowe muszą być wolne. Testy obejmują odczyt prawdziwego statusu SQLite, ponowienie, nawigację, odświeżenie podstrony, widok mobilny i niedostępność API. Testy obejmują też CRUD sesji, rzeczywiste pobieranie z witryny fixture, limit stron, zachowanie wyników po odświeżeniu i anulowanie. Deterministyczne testy nie zależą od zmiennych publicznych witryn.

Wyniki i lista plików etapu 07: [raport](docs/PHASE_07.md). Wcześniejsze kontrole: [etap 06](docs/PHASE_06.md), [etap 05](docs/PHASE_05.md), [etap 04](docs/PHASE_04.md), [etap 03](docs/PHASE_03.md), [etap 02](docs/PHASE_02.md), [etap 01](docs/PHASE_01.md).

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

Ekstrakcja, graf, eksplorator/CSV i porównania są wdrożone. Cytoscape.js obsługuje graf, Recharts wykresy pomiarów porównania. Raport laboratoryjny i dashboard pozostają w etapie 08.

Konfiguracja UI oparta na oficjalnych instrukcjach [Tailwind + Vite](https://tailwindcss.com/docs/installation/using-vite) i [shadcn/ui + Vite](https://ui.shadcn.com/docs/installation/vite). Button wygenerowano CLI shadcn, następnie dopasowano importy do lokalnego `cn` i `@radix-ui/react-slot`.
