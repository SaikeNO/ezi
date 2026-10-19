# Planowane API REST i SSE

> Status: etap 01 implementuje wyłącznie `GET /health`. Pozostałe endpointy są kontraktem projektowym i nie są jeszcze dostępne. Aktualny kontrakt działającego API: `/openapi.json`, interaktywna dokumentacja: `/docs`.

## Health — wdrożone w etapie 01

`GET /health` wykonuje zapytanie `SELECT 1` do skonfigurowanej bazy SQLite.

- HTTP 200: `{"status":"ok","database":"ok"}`.
- HTTP 503: `{"status":"error","database":"unavailable"}` przy błędzie SQLAlchemy. Szczegóły błędu trafiają do logów, nie do klienta.
- Sprawdza połączenie z bazą; nie potwierdza wykonania migracji ani dostępności funkcji późniejszych etapów.
- Lokalny CORS dopuszcza wyłącznie jawnie skonfigurowane originy i metodę GET. Uprawnienia dla kolejnych endpointów zostaną rozszerzone przy ich implementacji.


| Metoda | Ścieżka | Działanie |
|---|---|---|
| GET | `/health` | Status backendu |
| POST | `/api/sessions` | Utworzenie sesji i konfiguracji |
| GET | `/api/sessions` | Lista sesji (stronicowanie) |
| GET | `/api/sessions/{id}` | Szczegóły sesji |
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
