# Planowane API REST i SSE

> Status: etapy 01–05 implementują `/health`, CRUD sesji, start/cancel, SSE, odczyt stron/metadanych/odnośników oraz graf i statystyki. CSV i eksperymenty pozostają planowane. Aktualny kontrakt działającego API: `/openapi.json`, interaktywna dokumentacja: `/docs`.

## Health — wdrożone w etapie 01

`GET /health` wykonuje zapytanie `SELECT 1` do skonfigurowanej bazy SQLite.

- HTTP 200: `{"status":"ok","database":"ok"}`.
- HTTP 503: `{"status":"error","database":"unavailable"}` przy błędzie SQLAlchemy. Szczegóły błędu trafiają do logów, nie do klienta.
- Sprawdza połączenie z bazą; nie potwierdza wykonania migracji ani dostępności funkcji późniejszych etapów.
- Lokalny CORS dopuszcza wyłącznie jawnie skonfigurowane originy oraz metody GET, POST, PATCH i DELETE. Nagłówek `Location` jest dostępny dla przeglądarki; CORS akceptuje `Last-Event-ID`.


## Sesje — wdrożone w etapie 02

| Metoda | Ścieżka | Odpowiedź / reguły |
|---|---|---|
| POST | `/api/sessions` | 201, obiekt sesji; `Location: /api/sessions/{uuid}`. Tworzy sesję i konfigurację w jednej transakcji. |
| GET | `/api/sessions?offset=0&limit=20&status=queued` | `{items, total, offset, limit}`; `status` opcjonalny; offset 0–2147483647, limit 1–100. Porządek malejący po `created_at`, następnie `id`. |
| GET | `/api/sessions/{uuid}` | 200, obiekt sesji lub 404. Niepoprawny UUID → 422. |
| PATCH | `/api/sessions/{uuid}` | 200, obiekt po zmianie; tylko `queued`, inne statusy → 409. |
| DELETE | `/api/sessions/{uuid}` | 204, bez treści; usuwa konfigurację, strony, linki i członkostwa eksperymentów. `running` → 409; brak sesji → 404. |

Identyfikatory to UUID. Obiekt odczytu zawiera `id`, `start_url`, `status`, `created_at`, `started_at`, `finished_at`, `discovered_count`, `fetched_count`, `error_count`, `error` oraz pełną `config`. Etap 03 dodaje `link_count`, `stop_reason`, `crawler_version`, `user_agent` (dwa ostatnie ustawiane przy starcie). Czas jest zapisywany jako UTC i zwracany w ISO 8601 z oznaczeniem strefy. Liczniki nowej sesji wynoszą 0; czasy rozpoczęcia/zakończenia i błąd są `null`.

POST przyjmuje `start_url` i opcjonalną `config` (domyślnie pełen zestaw wartości poniżej). Nie pozwala ustawiać ID, statusu, liczników ani czasów. PATCH przyjmuje `start_url`, `config` lub oba pola; pusta treść i jawne `null` są odrzucane. **Przekazana `config` zastępuje całą konfigurację**, z domyślnymi wartościami dla pominiętych pól; bez pola `config` poprzednia konfiguracja pozostaje bez zmian. Błędne żądanie nie zmienia zapisanej sesji.

Statusy przechowywane w bazie: `queued`, `running`, `completed`, `failed`, `cancelled`. W etapie 02 każda nowa sesja otrzymuje `queued`; API nie udostępnia ręcznej zmiany statusu. Etap 03 realizuje przejścia przez start/cancel i pracownika opisanego poniżej. Usunięcie nieistniejącej sesji, także ponowne, zwraca 404.

### Konfiguracja i granice

Nieznane pola są zabronione. Liczby całkowite nie przyjmują booli, ułamków ani stringów; boole są ścisłe. Timeout musi być skończoną liczbą JSON.

| Pole | Domyślnie | Dopuszczalne wartości |
|---|---|---|
| `strategy` | `bfs` | `bfs`, `dfs` |
| `scope` | `server` | `server`, `web` |
| `link_types` | `hyperlinks` | `hyperlinks`, `images_and_hyperlinks`, `all_links` |
| `max_depth` | 3 | 0–20 |
| `max_pages` | 100 | 1–10000 |
| `timeout_seconds` | 10 | 1–60, także ułamki |
| `request_delay_ms` | 500 | 100–60000 |
| `max_duration_seconds` | 300 | 1–3600 |
| `max_response_bytes` | 2097152 | 1024–10485760 |
| `max_redirects` | 5 | 0–10 |
| `concurrency` | 2 | 1–8 |
| `respect_robots` | true | boolean |
| `follow_external_urls` | false | boolean |
| `process_one_page` | false | boolean |

`follow_external_urls=true` jest zapisywane również przy `scope=server`, ale nie znosi semantyki tego zakresu: podążanie poza host wymaga `scope=web`. `process_one_page` nie zmienia pozostałych zapisanych limitów. Limity są walidowane, przechowywane i egzekwowane podczas pobierania. `concurrency` jest górną granicą: w wersji 0.3 pobieranie w pojedynczej sesji jest sekwencyjne (efektywna współbieżność 1), aby zachować deterministyczną kolejność BFS/DFS.

### Walidacja URL

Wymagany absolutny HTTP/HTTPS URL (maksymalnie 2048 znaków wejścia), port 80 lub 443, bez danych logowania, whitespace, znaków sterujących i backslashy. Host musi być poprawną nazwą DNS z co najmniej dwiema etykietami lub publicznym IP. Blokowane są m.in. localhost, `.local`, `.internal`, `.lan`, `.home`, adresy prywatne/loopback/link-local, multicast i IPv6 z identyfikatorem interfejsu i obfuskowane zapisy IP normalizowane do takich adresów. Normalizacja kanonizuje schemat/host, IDNA, domyślny port, końcową kropkę hosta, segmenty kropkowe i niezastrzeżone escape procentowe; fragment jest usuwany. Kolejność parametrów query i odrębność `/a` oraz `/a/` są zachowane.

**Zapis sesji nie wykonuje DNS ani żądań HTTP do start URL.** Przy zapisie działa ta sama polityka składni/publicznych IP co przy pobieraniu. Etap 03 dodatkowo weryfikuje DNS, przypina adres połączenia i sprawdza jego faktycznego partnera. Wewnętrzne nazwy `.arpa`/`.onion`, adresy tunelowe IPv6, specjalne zakresy IETF i znane adresy usług chmurowych również są blokowane.

### Błędy wdrożonego API

Przykład 404:

```json
{"code":"session_not_found","message":"Nie znaleziono sesji","details":[]}
```

Walidacja → 422, `code=validation_error`, `details=[{location,message,type}]`; szczegóły nie zawierają wejściowych wartości ani kontekstu wyjątków. Konflikt edycji → 409/`session_not_editable`; konflikt usunięcia → 409/`session_running`. Błędy SQLAlchemy → 503/`database_unavailable`, bez szczegółów bazy w odpowiedzi. Health zachowuje osobny format z etapu 01. Jeśli pominięto migrację, health może działać mimo 503 dla sesji: uruchom `alembic upgrade head`.

## Crawler i postęp — wdrożone w etapie 03

| Metoda | Ścieżka | Zachowanie |
|---|---|---|
| POST | `/api/sessions/{uuid}/start` | 200 z obiektem sesji. `queued` → `running`; ponowienie dla `running` nie tworzy drugiego zadania. Sesja terminalna → 409/`session_already_finished`. Limit 4 zadań → 429/`crawler_busy`, sesja pozostaje queued. |
| POST | `/api/sessions/{uuid}/cancel` | 200 z obiektem. Queued/running → cancelled; zamyka aktywne HTTP i nie rozpoczyna następnych żądań. Ponowienie lub sesja terminalna zwraca bieżący stan bez zmian. |
| GET | `/api/sessions/{uuid}/events?after=0` | `text/event-stream`, utrwalone zdarzenia w kolejności ID. Wspiera `Last-Event-ID`. |

Start/cancel, edycja i usunięcie są bezpieczne wobec konkurencyjnych operacji: zmiana statusu/konfiguracji jest serializowana transakcją zapisu SQLite. Zakończonej sesji nie uruchamia się ponownie; utwórz nową, aby zachować niezależne wyniki.

### Zakończenie i liczniki

`completed` oznacza zakończenie pracy, także przez limit lub z błędami pojedynczych stron. `failed` oznacza brak pobranego HTML przy błędach strony startowej, awarię pracownika albo przerwanie przez nagły restart. `cancelled` zachowuje częściowe wyniki; zwykłe wyłączenie serwera zapisuje powód `server_shutdown`.

`stop_reason`: `frontier_exhausted`, `page_limit`, `time_limit`, `user_cancelled`, `server_shutdown`, `interrupted`, `start_failed`, `internal_error`, `link_limit`, `discovery_limit`, `origin_limit`. Błąd pojedynczej strony zapisuje się w Page.error i zdarzeniu page_failed, bez zatrzymania pozostałej kolejki (z wyjątkiem budżetów globalnych).

- `discovered_count`: liczba unikalnych adresów kandydatów HTML (start + cele hiperłączy), również poza zakresem/głębokością lub zablokowanych przed pobraniem. Zasoby obrazów/CSS/JS nie są stronami.
- `fetched_count`: liczba odebranych, mieszczących się w limitach odpowiedzi HTML 2xx. Może obejmować stronę, której późniejsza analiza linków zakończyła się błędem/limitem.
- `error_count`: błędy stron, w tym robots, polityka adresów, HTTP, timeout, nie-HTML i analiza linków. Anulowane żądanie nie jest sztucznie dopisywane jako błąd strony.
- `link_count`: wszystkie zapisane wystąpienia obsługiwanych odnośników HTTP/HTTPS; powtórzenia nie są agregowane.
- Page.fetch_order oznacza kolejność prób, także zablokowanych przed HTTP; `max_pages` ogranicza takie próby. Robots i redirecty nie zwiększają tego licznika, lecz podlegają osobnym limitom, opóźnieniom i czasowi sesji.
- Link.is_followed oznacza wybór celu hiperłącza do próby crawlowania; nie dowodzi udanego żądania HTTP. Page.final_url zapisuje końcowy URL udanej odpowiedzi po przekierowaniach.

### Zdarzenia SSE i reconnect

Każda ramka ma `id`, `event` i JSON `data` z bieżącymi licznikami/statusami; zdarzenia strony dodają jej ID/URL/głębokość lub kod błędu. Typy: `progress`, `page_discovered`, `page_fetched`, `page_failed`, `completed`, `cancelled`, `failure`.

Zdarzenie i opisany krok DB zatwierdzane są w tej samej transakcji **przed** wysłaniem. Odbiór HTML i odkrywanie jego odnośników to osobne zatwierdzone kroki: page_fetched może poprzedzać aktualizację link_count. Nie obiecuje atomowości całej sesji.

Po reconnect zwracane są rekordy z ID większym od `max(after, Last-Event-ID)`, partiami do 200. Kursor jest właściwy dla danej sesji; nie przenoś go pomiędzy sesjami. `retry: 2000`, heartbeat co 15 sekund bezczynności. Strumień zamyka się po opróżnieniu historii sesji terminalnej; UI zamyka EventSource i dodatkowo odczytuje REST co sekundę podczas running. Historia przeżywa restart i jest usuwana razem z sesją. Brak sesji przed otwarciem → 404; niepoprawny/ujemny kursor → 422; usunięcie podczas streamu kończy połączenie.

Po nagłym restarcie zadania running otrzymują failed/interrupted z zachowaniem danych i zdarzeniem failure. Brak automatycznego wznowienia frontier. Działa jeden proces API na plik SQLite; blokada plikowa odrzuca drugiego pracownika.

## Strony i ekstrakcja — wdrożone w etapie 04

| Metoda | Ścieżka | Odpowiedź |
|---|---|---|
| GET | `/api/sessions/{uuid}/pages?offset=0&limit=20` | `{items,total,offset,limit}`, porządek `discovery_order`, następnie `id`. |
| GET | `/api/sessions/{uuid}/pages/{page_uuid}` | Pełny rekord strony z tekstem `body`. |
| GET | `/api/sessions/{uuid}/pages/{page_uuid}/links?offset=0&limit=20` | `{items,total,offset,limit}` wszystkich zapisanych wystąpień linków tej strony; porządek `id`, nie kolejność DOM. |

Paginacja: offset 0–2147483647, limit 1–100, domyślnie 20. Niepoprawne UUID/parametry → 422. Brak sesji → 404 `session_not_found`; brak strony w podanej sesji (także ID strony innej sesji) → 404 `page_not_found`. Pusta sesja lub offset poza wynikiem daje pustą listę. Dane są dostępne również podczas pracy i po anulowaniu; odczyty kolejnych stron paginacji w aktywnej sesji nie stanowią jednego snapshotu.

Lista stron zawiera `id`, `session_id`, `normalized_url`, `original_url`, `final_url`, `depth`, `discovery_order`, `fetch_order`, `http_status`, `content_type`, `encoding`, `title`, `description`, `keywords`, `error`. `body` jest odczytywane wyłącznie w szczegółach, aby nie pobierać wszystkich tekstów przy listowaniu. Lista obejmuje także odkryte, lecz niepobrane cele hiperłączy; ich metadane są null. Zasoby obrazów/CSS/JS występują w linkach, nie w liście stron.

Link zawiera `id`, `source_page_id`, `target_url`, `target_page_id` (null dla zasobów), `kind`, `is_external`, `is_followed`. Powtórzenia celów zachowują osobne ID. Znaczenie `is_followed` i liczników nie zmienia się względem etapu 03.

Ekstrakcja zapisuje pierwszy title i pierwsze meta o nazwie description/keywords z atrybutem content (nazwy bez rozróżniania wielkości liter). Encje HTML są dekodowane, whitespace normalizowany; keywords pozostaje tekstem, bez sztucznego dzielenia na tablicę. Brak pola → null, jawnie puste pole → pusty string. Body to tekst wewnątrz body; dla fragmentu bez body — tekst dokumentu poza head/title/script/style/template/noscript. Pomija komentarze i dodaje odstępy między elementami blokowymi. Inline zachowuje ciągłość tekstu. Nie jest to renderowanie CSS ani wykonywanie JavaScript.

Kodowanie: BOM UTF-8/16/32 ma pierwszeństwo przed poprawnym HTTP charset, następnie deklaracja HTML rozpoznana przez BeautifulSoup w początkowych maksymalnie 4096 bajtach, domyślnie UTF-8. Nieznane/nieobsługiwane kodowanie jest pomijane; błędne sekwencje zastępuje U+FFFD. `encoding` po analizie to kanoniczna nazwa użytego kodeka, np. cp1250. Brak zgadywania statystycznego. `content_type` zawiera MIME bez parametrów, `http_status` status odebranej strony. Akceptowane dokumenty: HTML/XHTML 2xx; pozostałe odpowiedzi zachowują dotychczasową obsługę błędów strony.

Odbiór HTTP, zapis metadanych oraz zapis odnośników są osobnymi krokami. Limit globalnego odkrywania może zachować metadane bez linków bieżącej strony. Błąd/limit samego parsera pozostawia pola treści null oraz zapisany błąd; nie publikuje częściowo przeanalizowanych danych. Starsze wyniki nie są automatycznie ponownie pobierane ani uzupełniane. Filtrowanie, wyszukiwanie i ekran eksploratora należą do etapu 06.

## Graf i statystyki — wdrożone w etapie 05

`GET /api/sessions/{uuid}/graph` zwraca `{session_id,status,nodes,edges,summary,per_depth}`. `GET /api/sessions/{uuid}/stats` zwraca `{session_id,status,summary,per_depth,per_page}`. Oba endpointy działają dla wszystkich statusów, w tym queued/running i częściowych wyników; nie uruchamiają crawlowania ani połączeń z witrynami. Brak sesji → 404, błędny UUID → 422. Każda odpowiedź jest jednym snapshotem zapisanych rekordów, niezależnym od liczników CrawlSession.

Node: `id` (page:UUID lub target:SHA256), `page_id` (UUID lub null dla celu bez Page), `url`, `title` (maks. 500 znaków), `depth`, `fetched`, `is_external`, `http_status`, `error`, `in_degree`, `out_degree`, `unique_in_degree`, `unique_out_degree`. Fetched oznacza zapisany final_url po udanym odbiorze HTML, również gdy późniejsza analiza miała błąd. Pełne title/body/metadane pobiera się przez istniejący endpoint szczegółów strony. Zasób nie jest sztucznie oznaczany jako pobrany.

Edge: `id` (link:UUID), `source`, `target` (identyfikatory w nodes), `target_url`, `kind`, `is_external`, `is_followed`. Zachowuje wszystkie wystąpienia i pętle; każdy target ma węzeł, także zewnętrzny i niepobrany. URL celu odpowiada jego węzłowi; różne final_url nie zmieniają tożsamości zapisanych URL żądań.

Summary:

- node_count, page_count, resource_target_count: wszystkie węzły, rekordy Page, pozostałe cele bez Page.
- fetched_pages, errored_pages: strony z odebranym HTML, strony z niepustym error (zbiory mogą się nakładać).
- reached_depth, discovered_depth: maksimum głębokości pobranego HTML i wszystkich Page; null dla pustego zbioru. Poziom wizualny celu zasobu nie zwiększa tych maksimów.
- link_count, unique_relations: wystąpienia Link i unikalne pary źródło–cel, niezależnie od kind.
- internal_links, external_links: wystąpienia według zapisanego is_external, względem hosta startowego.
- root_links, subpage_links: wystąpienia ze źródeł na depth 0 oraz pozostałych Page.
- root_unique_targets, subpage_unique_targets: liczby różnych celów w każdej grupie (nie sumy per-page).

Per_depth: `{depth,pages,fetched_pages,outgoing_links}`, tylko poziomy rekordów Page, rosnąco. Per_page: `{page_id,url,depth,fetched,in_degree,out_degree,unique_in_degree,unique_out_degree}` w kolejności odkrywania. Stopnie liczą wszystkie rodzaje krawędzi, unikalne stopnie — różnych sąsiadów. Pętla liczy się raz w każdym kierunku.

Graph odrzuca wizualizację powyżej 5000 węzłów lub 20000 linków: 413 `graph_too_large`. Nie zwraca uciętego grafu. Stats nadal obejmuje cały zapisany zbiór. UI automatycznie odczytuje stats po 413; dla pozostałych błędów pokazuje błąd i ponowienie. Widok odświeża użytkownik, nie zmienia się automatycznie podczas interakcji. Search na grafie obejmuje URL i skrócone title; lista wyboru pokazuje do 30 dopasowań z jawną liczbą wszystkich trafień, bez filtrowania metryk.

## Zestawienie endpointów

| Metoda | Ścieżka | Działanie |
|---|---|---|
| GET | `/health` | Status backendu |
| POST | `/api/sessions` | Utworzenie sesji i konfiguracji |
| GET | `/api/sessions` | Lista sesji (stronicowanie) |
| GET | `/api/sessions/{id}` | Szczegóły sesji |
| PATCH | `/api/sessions/{id}` | Edycja oczekującej sesji |
| DELETE | `/api/sessions/{id}` | Usunięcie sesji i wyników |
| POST | `/api/sessions/{id}/start` | Start crawlowania |
| POST | `/api/sessions/{id}/cancel` | Anulowanie |
| GET | `/api/sessions/{id}/events` | SSE: progress/page/failure/completed/cancelled |
| GET | `/api/sessions/{id}/pages` | Strony, filtry, stronicowanie |
| GET | `/api/sessions/{id}/graph` | Węzły i krawędzie |
| GET | `/api/sessions/{id}/stats` | Zagregowane i per-page statystyki |
| GET | `/api/sessions/{id}/export` | CSV (wybrane pola, separator) |
| POST | `/api/compare` | Porównanie sesji |
| POST | `/api/experiments` | Utworzenie eksperymentu / zestawu wariantów |
| GET | `/api/experiments/{id}` | Status i wyniki eksperymentu |

## Przykładowa konfiguracja tworzenia sesji

```json
{
  "start_url": "https://example.com",
  "config": {
    "strategy": "bfs",
    "scope": "server",
    "link_types": "hyperlinks",
    "max_depth": 3,
    "max_pages": 100,
    "timeout_seconds": 10,
    "request_delay_ms": 500,
    "follow_external_urls": false,
    "process_one_page": false
  }
}
```

## Przykład elementów grafu (pozostałe pola opisane powyżej)

```json
{
  "nodes": [{"id": "page:uuid-a", "url": "https://example.com/", "depth": 0, "fetched": true}, {"id": "page:uuid-b", "url": "https://example.com/about", "depth": 1, "fetched": false}],
  "edges": [{"id": "link:uuid-c", "source": "page:uuid-a", "target": "page:uuid-b", "target_url": "https://example.com/about", "kind": "hyperlink", "is_external": false}]
}
```

## Eksport CSV

`GET /api/sessions/{id}/export?fields=url,keywords,title&separator=comma` (przykładowa konwencja). Backend powinien walidować nazwy pól i separator, zapewniać poprawny `Content-Disposition`, UTF-8 i ochronę przed CSV injection.

## Błędy

Zwracaj standardowe statusy HTTP i przewidywalną strukturę błędu (np. `code`, `message`, `details`). Błędne parametry → 422; brak sesji → 404; konflikt statusu → 409. Operacje start/cancel muszą być bezpieczne wobec wielokrotnych wywołań.

## SSE

Wdrożony protokół i politykę reconnect opisuje sekcja „Crawler i postęp” powyżej. Zdarzenia nie są wysyłane przed zatwierdzeniem opisanego kroku w bazie.
