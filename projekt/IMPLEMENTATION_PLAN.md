# Plan implementacji — WebCrawler Studio

## Zasady prowadzenia prac

Implementuj etapy **kolejno**. Po każdym etapie: wykonaj testy, popraw wykryte błędy, zaktualizuj dokumentację, wypisz pliki zmienione i ograniczenia. Nie przechodź do kolejnego etapu bez nowego polecenia. Nie zastępuj działania makietą.

## Etap 01 — Project Bootstrap

**Status:** ukończony 2026-10-18. Wyniki w `docs/PHASE_01.md`.

**Zadania:** monorepo backend/frontend; FastAPI `/health`; React + TypeScript + Vite; Tailwind + shadcn/ui; SQLite i konfiguracja SQLAlchemy/Alembic; CORS dla lokalnego frontendu; `.env.example`; Docker Compose; podstawowy układ nawigacji.

**Definition of Done:** frontend uruchamia się, wyświetla status backendu, endpoint `/health` odpowiada, kontenery/komendy deweloperskie zostały sprawdzone, README opisuje rzeczywiste uruchomienie.

## Etap 02 — Database & Sessions

**Status:** ukończony 2026-10-19. Wyniki w `docs/PHASE_02.md`.

**Zadania:** modele `CrawlSession`, `CrawlConfig`, `Page`, `Link`, `Experiment`; indeksy i relacje; migracje; CRUD sesji; statusy `queued/running/completed/failed/cancelled`; walidacja konfiguracji.

**Definition of Done:** można utworzyć, odczytać, wylistować i usunąć sesję; dane przetrwają restart; testy migracji i API przechodzą.

## Etap 03 — Crawler Engine

**Status:** ukończony 2026-10-19. Wyniki i ograniczenia w `docs/PHASE_03.md`.

**Zadania:** BFS (FIFO), DFS (LIFO); ograniczenia głębokości, liczby stron, czasu i opóźnień; zakres `server`/`web`; przełącznik `follow_external_urls`; `process_one_page`; wybór `hyperlinks`, `images_and_hyperlinks`, `all_links`; URL normalization, canonicalizacja fragmentów, deduplikacja, obsługa cykli; `robots.txt`; ochrona SSRF (DNS, przekierowania, adresy prywatne); start/anulowanie, zdarzenia postępu, utrwalanie częściowych wyników.

**Definition of Done:** kontrolowana witryna testowa daje zgodne z oczekiwaniami wyniki BFS/DFS; anulowanie działa; niebezpieczne docelowe adresy są blokowane; błędy pojedynczych stron nie przerywają całej sesji.

## Etap 04 — HTML & Metadata Extraction

**Status:** ukończony 2026-10-19. Ekstrakcja, API i wyniki kontroli w `docs/PHASE_04.md`.

**Zadania:** parsowanie `URL`, `title`, `meta description`, `meta keywords`, tekstu `body`; obsługa `base href`, URL relatywnych i absolutnych; odnośniki `<a>`, `<img>`, `<link>` i innych elementów w zależności od trybu; status HTTP, content-type, encoding, brakujące pola, błędny HTML.

**Definition of Done:** testy parsera na fixture'ach pokrywają wszystkie tryby ekstrakcji; wyniki można pobrać przez API.

## Etap 05 — Interactive Graph

**Zadania:** API węzłów/krawędzi, Cytoscape.js; powiększanie, przesuwanie, wyszukiwanie, wybór węzła; kolory głębokości; panel szczegółów; statystyki: osiągnięta głębokość, strony, relacje, linki na stronie głównej i podstronach, wewnętrzne/zewnętrzne, in/out-degree.

**Definition of Done:** graf odpowiada zapisanym wynikom; statystyki zgadzają się z wyliczeniami na grafie; działa interakcja z węzłem.

## Etap 06 — Data Explorer & CSV

**Zadania:** tabela z filtrowaniem i wyszukiwaniem; konfiguracja eksportowanych pól (`URL`, `Keyword`, `Title`, `Description`, `Body` itd.), separatora i BOM; poprawne quoting CSV; zabezpieczenie przed formula/CSV injection; eksport wybranej sesji.

**Definition of Done:** plik CSV odczytuje się poprawnie w arkuszu, znaki polskie, przecinki i nowe linie zachowują się prawidłowo; testy eksportu przechodzą.

## Etap 07 — Experiments & Comparison

**Zadania:** uruchomienie wariantów parametrów dla jednego start URL; porównania BFS/DFS, server/web, typów linków i głębokości; różnice zbiorów stron/krawędzi, zawartości metadanych, głębokości i czasu; wizualizacja metryk; wnioski oparte wyłącznie na zmierzonych danych.

**Definition of Done:** dwie sesje z różnymi ustawieniami dają porównanie z listami elementów wspólnych/unikalnych; metryki są powtarzalne na deterministycznym serwisie testowym.

## Etap 08 — Reports, QA & Documentation

**Zadania:** raport do sprawozdania (HTML; PDF opcjonalnie), dashboard, obsługa stanów pustych/błędów, testowa witryna z >=20 podstronami i >=3 poziomami głębokości, unit/integration/E2E, dokumentacja użytkownika i testy wymagań I.1–II.8.

**Definition of Done:** wszystkie osiem punktów ćwiczenia ma dowód działania i scenariusz akceptacyjny; build, testy i instrukcja uruchomienia są zweryfikowane.

## Kolejność priorytetów

**MVP:** etapy 01–06 (w tym prawdziwy crawler i eksport). **Pełna wersja:** etapy 07–08. W razie zmian zakresu nie pomijaj bezpieczeństwa ani trwałego przechowywania wyników.

## Kryteria globalne

- Obsługa strony startowej oraz >=20 podstron i >=3 poziomów głębokości.
- Co najmniej BFS/DFS, server/web, wymagane grupy linków oraz follow external.
- Graf pokazuje zarówno węzły jak i relacje z rzeczywistego crawlowania.
- Eksport CSV pozwala wybrać pola i separator.
- Dwie różne sesje można zachować, przeanalizować i porównać.
- Brak nieograniczonego crawlowania oraz połączeń do prywatnych IP.
