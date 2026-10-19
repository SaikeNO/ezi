# Architektura i semantyka crawlera

## Stan po etapie 03

Działa monorepo, CRUD sesji i rzeczywisty crawler z kolejką BFS/stosem DFS, start/cancel, zapisanymi częściowymi wynikami i trwałym dziennikiem SSE. Interfejs pokazuje liczniki wyłącznie z API i pozwala uruchamiać/anulować sesje. Tytuły, meta description/keywords/body oraz API eksploratora pozostają w etapie 04; graf, CSV i porównania w dalszych etapach.

Migracja `0003_crawler` rozszerza sesję o link_count, stop_reason, wersję crawlera i User-Agent, stronę o final_url oraz dodaje crawl_events z FK CASCADE i indeksem `(session_id, id)`. Zachowuje dane etapu 02; aplikacja nie używa create_all. SQLite 3.35+ jest wymagane do bezpiecznego downgrade kolumn bez odtwarzania tabel nadrzędnych. Sprawdzono migrację w obu kierunkach z istniejącymi stronami/linkami.

- Każda sesja ma własną konfigurację i wyniki; statusy zmienia pracownik. Transakcje BEGIN IMMEDIATE chronią start/edycję/usunięcie przed wyścigami. Konfiguracja pozostaje niezmienna po starcie.
- Jeden proces API na plik SQLite (egzekwowany blokadą OS), maksymalnie cztery aktywne sesje. Każda pobiera sekwencyjnie; concurrency jest górną granicą, efektywnie 1. Chroni to kolejność BFS/DFS przed wyścigami odpowiedzi.
- HTMLParser odkrywa nawigację bez wykonywania pobranego kodu. Nie wypełnia metadanych treści. Łącza względne odnoszą się do końcowego URL i pierwszego base href. Zasoby są celami linków, nie są dodawane do kolejki HTML.
- Deduplikacja dotyczy znormalizowanych URL żądań. Różne adresy przekierowujące na tę samą stronę mogą wymagać osobnych prób; final_url zachowuje ich znaczenie. Query nie jest sortowane, zastrzeżone kodowania nie są dekodowane.
- DFS po znalezieniu krótszej ścieżki aktualizuje znaną głębokość i ponownie rozwija zapisane odnośniki bez drugiego pobrania strony. Przy ograniczeniach/błędach głębokość to minimum poznanych przejść, nie obietnica pełnego grafu.
- Strony pozostają unikalne po `(session_id, normalized_url)`. Linki zachowują wszystkie wystąpienia. FK pilnują zgodności sesji źródła/celu. Usunięcie sesji kaskadowo usuwa konfigurację, strony, linki, zdarzenia i członkostwa eksperymentów, zachowując inne sesje i rekord eksperymentu.
- Metadane HTTP i zdarzenie page_fetched zapisywane są od razu po odbiorze HTML; linki, nowe strony i progress w następnym kroku. Dzięki temu anulowanie lub błąd analizy nie usuwa już odebranej strony.

### Polityka sieci

Każde żądanie i każdy redirect przechodzi tę samą walidację HTTP/HTTPS, portów i hosta. DNS zwraca ograniczony zbiór A/AAAA: choćby jeden niepubliczny adres odrzuca całość. Połączenie jest wykonywane do zatwierdzonego literału IP (bez drugiego lookup nazwy), a getpeername/server_addr jest weryfikowane przed wysłaniem HTTP i przy I/O. TLS używa oryginalnej nazwy SNI oraz weryfikacji certyfikatu. Połączenia keep-alive i proxy z otoczenia są wyłączone; zdalne cookies nie są przenoszone do następnych żądań.

Wspólny limiter obejmuje robots, DNS, redirecty i odbiór odpowiedzi. Blokada origin trwa do końca żądania, po czym następne czeka co najmniej max(opóźnienie konfiguracji, robots). Zapobiega grupowaniu ruchu po wolnym DNS. Origin to schemat/host/port; zakres server nadal oznacza ten sam host.

Robots jest domyślnie włączone, pobierane raz na origin/sesję bez rekurencyjnego odczytu robots. 404/410 pozwala; 401/403, pozostałe błędy, nieprawidłowe UTF-8/reguły, zły typ odpowiedzi i niebezpieczny redirect blokują. Redirect robots poza origin jest niedozwolony. Obsługiwane: wybór najdokładniejszego User-agent i łączenie grup, Allow/Disallow z najdłuższym dopasowaniem (Allow wygrywa remis), `*`, końcowe `$`, Crawl-delay i Request-rate. Nie deklarujemy pełnej zgodności z historycznymi crawlerami ani wszystkich rozszerzeń robots.

User-Agent: WebCrawlerStudio/0.3 (educational crawler; respects robots.txt). Brak opcji wyłączania ochrony SSRF w konfiguracji lub zmiennych środowiska. Testy wstrzykują osobny backend wyłącznie w Pythonie z katalogu tests; nie jest dostarczany w obrazie.

### Budżety i anulowanie

Oprócz limitów konfiguracji: 50000 kandydatów stron, 200000 wystąpień linków/sesję, 5000 referencji/stronę, 100000 elementów HTML, 65536 znaków niedomkniętego tokena/bloku i limit czasu analizy. Robots ma limit min(limit odpowiedzi, 512 KiB). Kompresja jest odrzucana mimo Accept-Encoding identity, aby nie dopuścić bomb dekompresyjnych. Limit bajtów jest sprawdzany na Content-Length i podczas strumieniowania.

Budżet sesji obejmuje robots, opóźnienia, DNS, odpowiedzi i analizę. Anulowanie przerywa oczekiwania/HTTP; parser w wątku sprawdza sygnał między ograniczonymi fragmentami. Krótkie, ograniczone kroki zapisu SQLite kończą transakcję, zanim zapisany zostanie stan terminalny. Przy limicie odkrywania krok odkrywania bieżącej strony jest wycofywany, lecz odebrane HTML i poprzednie wyniki pozostają. SSE nie ma rosnących kolejek w RAM — odczytuje zapisany dziennik partiami.

Proces Docker używa exec, Uvicorn ma 5 s grace dla otwartych odpowiedzi, a kontener 30 s stop_grace_period. Ręczny restart wymaga jawnego --timeout 30, aby CLI nie skróciło okna. Zwykłe wyłączenie zapisuje cancelled/server_shutdown. Nagły restart oznacza running jako failed/interrupted; nie wznawia automatycznie nieutrwalonej kolejki. Semantykę liczników, błędów i reconnect opisuje API.md.

## Przepływ

`React UI` → `FastAPI REST` → `Crawler Engine` → `httpx / HTML Parser` → `SQLite`. Backend publikuje zdarzenia postępu przez SSE; frontend pobiera graf, statystyki i tabelę wyników po API. `Analysis/Comparison Service` odczytuje zapisane sesje i generuje porównania.

## Komponenty

- **Crawler engine:** kolejka/stack frontier, stan odwiedzin, limitowanie, wykrywanie cykli, anulowanie.
- **URL/scope/security:** normalizacja, ograniczenie zakresu, walidacja DNS/IP i przekierowań.
- **Extractor:** HTML → metadane i typowane odnośniki.
- **Persistence:** SQLAlchemy + Alembic, transakcje i indeksy.
- **Graph/Statistics:** budowanie skierowanych węzłów i krawędzi, stopnie oraz statystyki per depth.
- **Comparison:** zbiór URL i krawędzi wspólnych/unikalnych, pola metadanych i parametry.
- **Export:** kodowanie i bezpieczna serializacja CSV.

## Model logiczny

- `sessions`: ID, start URL, created/started/finished at, status, counters, error.
- `crawl_config`: session ID, strategy, scope, link selection, depth, page limit, timeout, delay, follow external, one-page-only.
- `pages`: ID, session ID, normalized URL, original URL, depth, discovery/fetch order, HTTP status, title, description, keywords, body, error.
- `links`: ID, session ID, source page ID, target URL (opcjonalnie target page ID), link type, is external, is followed.
- `experiments`: ID, nazwa, start URL, odniesienia do porównywanych sesji/wariantów.

Indeks unikalny `(session_id, normalized_url)` dla pobranych stron. `links` powinny umożliwiać wiele wystąpień tego samego docelowego adresu na stronie lub jawnie dokumentować agregację; dla miar grafowych wyliczaj dodatkowo unikalne krawędzie.

## Semantyka (jawne decyzje projektowe)

- Start URL = **depth 0**. Maksymalna głębokość N oznacza pobieranie stron osiągalnych w co najwyżej N przejściach po hiperłączach.
- BFS używa FIFO, DFS używa LIFO. Przy ograniczeniach lub błędach mogą odkryć różne podzbiory. Bez ograniczeń i przy statycznej stronie ich pełne zbiory osiągalnych stron mogą być takie same.
- `server`: śledzenie wyłącznie tego samego hosta startowego; `web`: może obejmować inne hosty, gdy `follow_external_urls = true`.
- `hyperlinks`: hiperłącza HTML prowadzące do nawigacji; `images_and_hyperlinks`: dodatkowo odwołania obrazów; `all_links`: dodatkowo pozostałe obsługiwane referencje HTML (np. CSS, skrypty, media). Udokumentuj konkretne tagi i atrybuty.
- Obrazy i pozostałe zasoby nie-HTML mogą być odkrywane i zapisywane jako cele linków, ale domyślnie nie są przetwarzane jako strony HTML.
- `process_one_page` pobiera jedynie dokument startowy, ale wciąż może analizować jego linki.
- `follow_external_urls` steruje **podążaniem**, nie samym wykrywaniem i zapisywaniem linków zewnętrznych.
- Linki na stronie głównej i podstronach raportuj jako liczbę wszystkich znalezionych wystąpień oraz odrębnie liczbę unikalnych celów. Nie mieszaj tych wartości.

## Bezpieczeństwo i ograniczenia

- Waliduj każdy docelowy URL przed żądaniem: tylko HTTP/HTTPS, wykluczenie userinfo, lokalnych i prywatnych adresów IP, wewnętrznych nazw, niedozwolonych portów w zależności od polityki.
- Sprawdzaj wszystkie rekordy DNS i **rzeczywisty adres połączenia**; nie dopuszczaj DNS rebinding. Waliduj osobno każdy redirect i ogranicz ich liczbę.
- `robots.txt` domyślnie włączone, z bezpiecznym trybem na błędy; opisany User-Agent; opóźnienie per origin; ograniczenie współbieżności, liczby stron, głębokości, rozmiaru odpowiedzi i całkowitego czasu.
- Nie wykonuj kodu pobranego ze stron. W UI renderuj treści jako tekst, a nie zaufany HTML. Zabezpiecz CSV przed formułami.

## Deterministyczne testy

Fixture witryny z >=20 HTML podstronami, >=3 głębokościami, linkami cyklicznymi, zewnętrznymi, zasobami graficznymi, błędami HTTP i różnymi metatagami. Testy crawlera w kontrolowanym środowisku; nie wymagaj stałych wyników na zmiennych publicznych witrynach.
