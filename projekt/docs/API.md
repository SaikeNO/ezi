# Planowane API REST i SSE

> Status: etapy 01–02 implementują `/health` i CRUD `/api/sessions` opisany poniżej. Endpointy crawlera, stron, grafu, CSV, eksperymentów i SSE pozostają planowane. Aktualny kontrakt działającego API: `/openapi.json`, interaktywna dokumentacja: `/docs`.

## Health — wdrożone w etapie 01

`GET /health` wykonuje zapytanie `SELECT 1` do skonfigurowanej bazy SQLite.

- HTTP 200: `{"status":"ok","database":"ok"}`.
- HTTP 503: `{"status":"error","database":"unavailable"}` przy błędzie SQLAlchemy. Szczegóły błędu trafiają do logów, nie do klienta.
- Sprawdza połączenie z bazą; nie potwierdza wykonania migracji ani dostępności funkcji późniejszych etapów.
- Lokalny CORS dopuszcza wyłącznie jawnie skonfigurowane originy oraz metody GET, POST, PATCH i DELETE. Nagłówek `Location` jest dostępny dla przeglądarki.


## Sesje — wdrożone w etapie 02

| Metoda | Ścieżka | Odpowiedź / reguły |
|---|---|---|
| POST | `/api/sessions` | 201, obiekt sesji; `Location: /api/sessions/{uuid}`. Tworzy sesję i konfigurację w jednej transakcji. |
| GET | `/api/sessions?offset=0&limit=20&status=queued` | `{items, total, offset, limit}`; `status` opcjonalny; offset 0–2147483647, limit 1–100. Porządek malejący po `created_at`, następnie `id`. |
| GET | `/api/sessions/{uuid}` | 200, obiekt sesji lub 404. Niepoprawny UUID → 422. |
| PATCH | `/api/sessions/{uuid}` | 200, obiekt po zmianie; tylko `queued`, inne statusy → 409. |
| DELETE | `/api/sessions/{uuid}` | 204, bez treści; usuwa konfigurację, strony, linki i członkostwa eksperymentów. `running` → 409; brak sesji → 404. |

Identyfikatory to UUID. Obiekt odczytu zawiera `id`, `start_url`, `status`, `created_at`, `started_at`, `finished_at`, `discovered_count`, `fetched_count`, `error_count`, `error` oraz pełną `config`. Czas jest zapisywany jako UTC i zwracany w ISO 8601 z oznaczeniem strefy. Liczniki nowej sesji wynoszą 0; czasy rozpoczęcia/zakończenia i błąd są `null`.

POST przyjmuje `start_url` i opcjonalną `config` (domyślnie pełen zestaw wartości poniżej). Nie pozwala ustawiać ID, statusu, liczników ani czasów. PATCH przyjmuje `start_url`, `config` lub oba pola; pusta treść i jawne `null` są odrzucane. **Przekazana `config` zastępuje całą konfigurację**, z domyślnymi wartościami dla pominiętych pól; bez pola `config` poprzednia konfiguracja pozostaje bez zmian. Błędne żądanie nie zmienia zapisanej sesji.

Statusy przechowywane w bazie: `queued`, `running`, `completed`, `failed`, `cancelled`. W etapie 02 każda nowa sesja otrzymuje `queued`; API nie udostępnia ręcznej zmiany statusu. Przejścia i uruchamianie/anulowanie należą do etapu 03. Usunięcie nieistniejącej sesji, także ponowne, zwraca 404.

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

`follow_external_urls=true` jest zapisywane również przy `scope=server`, ale nie znosi semantyki tego zakresu: podążanie poza host wymaga `scope=web`. `process_one_page` nie zmienia pozostałych zapisanych limitów. Limity są teraz walidowane i przechowywane; ich egzekwowanie przy pobieraniu należy do etapu 03.

### Walidacja URL

Wymagany absolutny HTTP/HTTPS URL (maksymalnie 2048 znaków wejścia), port 80 lub 443, bez danych logowania, whitespace, znaków sterujących i backslashy. Host musi być poprawną nazwą DNS z co najmniej dwiema etykietami lub publicznym IP. Blokowane są m.in. localhost, `.local`, `.internal`, `.lan`, `.home`, adresy prywatne/loopback/link-local, multicast i IPv6 z identyfikatorem interfejsu i obfuskowane zapisy IP normalizowane do takich adresów. HttpUrl kanonizuje schemat/host, IDNA i domyślny port; fragment jest usuwany.

**Zapis sesji nie wykonuje DNS ani żądań HTTP do start URL.** Ta walidacja nie jest pełnym zabezpieczeniem SSRF: weryfikacja wszystkich odpowiedzi DNS, faktycznego celu połączenia i redirectów jest obowiązkowa w etapie 03.

### Błędy wdrożonego API

Przykład 404:

```json
{"code":"session_not_found","message":"Nie znaleziono sesji","details":[]}
```

Walidacja → 422, `code=validation_error`, `details=[{location,message,type}]`; szczegóły nie zawierają wejściowych wartości ani kontekstu wyjątków. Konflikt edycji → 409/`session_not_editable`; konflikt usunięcia → 409/`session_running`. Błędy SQLAlchemy → 503/`database_unavailable`, bez szczegółów bazy w odpowiedzi. Health zachowuje osobny format z etapu 01. Jeśli pominięto migrację, health może działać mimo 503 dla sesji: uruchom `alembic upgrade head`.

## Pełny kontrakt projektu (częściowo planowany)

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

## Odpowiedź grafu (format docelowy)

```json
{
  "nodes": [{"id": "page-1", "url": "https://example.com", "depth": 0, "fetched": true}],
  "edges": [{"id": "link-1", "source": "page-1", "target_url": "https://example.com/about", "kind": "hyperlink", "is_external": false}]
}
```

## Eksport CSV

`GET /api/sessions/{id}/export?fields=url,keywords,title&separator=comma` (przykładowa konwencja). Backend powinien walidować nazwy pól i separator, zapewniać poprawny `Content-Disposition`, UTF-8 i ochronę przed CSV injection.

## Błędy

Zwracaj standardowe statusy HTTP i przewidywalną strukturę błędu (np. `code`, `message`, `details`). Błędne parametry → 422; brak sesji → 404; konflikt statusu → 409. Operacje start/cancel muszą być bezpieczne wobec wielokrotnych wywołań.

## SSE

Minimalny zestaw zdarzeń: `progress`, `page_discovered`, `page_fetched`, `page_failed`, `completed`, `cancelled`. Udokumentuj politykę wznowienia/reconnect i atomowość zapisu przed wysłaniem zdarzenia.
