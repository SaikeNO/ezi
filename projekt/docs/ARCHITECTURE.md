# Architektura i semantyka crawlera

## Stan po etapie 07

Działa monorepo, CRUD sesji i rzeczywisty crawler BFS/DFS, metadane, graf Cytoscape, eksplorator i CSV. Etap 07 dodaje zapisane grupy 2–4 konfiguracji wspólnego URL, uruchamianie wariantów oraz porównanie zakończonych sesji z wykresami Recharts. Wszystkie liczniki i wnioski pochodzą z zapisanych danych; raporty laboratoryjne/dashboard pozostają w etapie 08.

### Eksperymenty i porównania

Istniejące Experiment/experiment_sessions i osobne CrawlConfig wystarczają: bez nowej migracji. Utworzenie grupy i 2–4 queued sesji jest atomowe. Sesje są uporządkowane created_at/id; tworzenie nadaje im kolejne mikrosekundy jednego timestampu, zachowując kolejność wariantów wejścia. Konfiguracje członków są niezmienne także przed startem (configuration_locked wyliczane z relacji, PATCH → 409). Zwykłe niezwiązane queued sesje pozostają edytowalne. Usunięcie grupy zachowuje sesje i nie anuluje aktywnych zadań. Dotychczasowe usuwanie sesji zachowuje grupę, lecz usuwa członkostwo; mniej niż dwa pozostałe warianty daje incomplete. Etykiety A–D oznaczają aktualną kolejność pozostałych sesji, nie trwałą tożsamość — identyfikatorem jest UUID.

Start grupy próbuje uruchomić queued warianty istniejącym CrawlManager, bez obejścia ochrony sieci, throttlingu ani limitu czterech pracowników. Running/terminal są pomijane. Każda nieudana próba ma jawny błąd per wariant w odpowiedzi; 429 pozostawia queued i wymaga ręcznego ponowienia. Nie ma ukrytego schedulera/wznowienia po awarii. UI odświeża działającą grupę co sekundę; anulowanie pojedynczego wariantu odbywa się przez szczegóły sesji.

POST compare wymaga 2–4 różnych sesji terminalnych z identycznym zapisanym znormalizowanym start_url. Jeden jawny snapshot SQLite obejmuje wszystkie sesje, konfiguracje, strony i linki. Pierwsza sesja jest bazą A, a wynik zawiera pary A względem każdej kolejnej (nie wszystkie kombinacje). Failed/cancelled i zakończenia przez limit są porównywalne, ale jawnie oznaczone jako częściowe. Nie utożsamiamy braku URL z nieosiągalnością strony.

Porównujemy oddzielnie zbiory odkrytych URL i odebranych HTML (final_url obecny). Tożsamość strony to normalized_url żądania; final_url nie scala stron. Typowana krawędź to trójka source URL, target URL, kind, niezależna od ID bazy. Zbiory krawędzi są deduplikowane do porównania, a Counter osobno wykazuje zmienioną liczbę wystąpień, również zera dla brakującej krawędzi. To precyzyjniejsza tożsamość niż para źródło–cel w unikalnych relacjach grafu etapu 05; obie wielkości są jawnie nazwane.

Title/description/keywords/body porównuje się tylko dla URL pobranych w obu sesjach, po pełnym SHA-256 UTF-8; null i pusty string pozostają różne. Odpowiedź zawiera do 500 znaków podglądu, pełny skrót, długość i flagę skrócenia; nie udaje pełnej treści. Pełny tekst nadal udostępnia Page API. Głębokość jest porównywana dla wspólnie odkrytych stron, kolejność to zapisany fetch_order prób (także nieudanych). Czas to finished_at-started_at; brak albo ujemny przedział daje null, nie zero. Liczniki liczone z rekordów Page/Link, nie skopiowane z licznika sesji.

Budżety łączne dla całego żądania: 20000 Page, 80000 Link, 64 MiB treści pól tekstowych, 30 s sprawdzane podczas analizy stron. Przekroczenie daje 413/503 bez pozornej częściowej odpowiedzi. Duże pola czytane po jednym rekordzie, linki partiami; przechowywane skróty/podglądy zamiast pełnego body. Listy mają wspólny offset/limit 0–2147483647 / 1–100 (domyślnie 25), dokładne total i brak ukrytego ucinania. Globalna partia zmienia każdą listę niezależnie, metryki zawsze obejmują cały snapshot.

Recharts jest ładowany z widokiem porównań, pokazuje osobno liczniki oraz sekundy, z tabelą alternatywną i obsługą klawiatury. Nie imputuje brakującego czasu zerem. Obserwacje podają konkretne liczby wspólne/unikalne i zmienione metadane. Zmiana treści witryny, współdzielony limiter i obciążenie nie pozwalają przypisać każdej różnicy wyłącznie konfiguracji. BFS/DFS nie musi zmieniać pełnego grafu; brak automatycznego rankingu najlepszego wariantu.

### Eksplorator i CSV

Lista Page oraz eksport używają jednego PageFilters: dosłowny fragment URL/metadanych (bez body), dokładny depth/HTTP status, fetched i has_error. SQLite otrzymuje deterministyczną funkcję casefold na każdym połączeniu, dlatego wyszukiwanie nie ogranicza się do ASCII i obsługuje m.in. ŁÓDŹ/łódź. Zapytania są parametryzowane; % i _ są zwykłymi znakami. Lista wykonuje count i paginację w jednym jawnym snapshotcie, a CSV eksportuje wszystkie pasujące rekordy w kolejności discovery_order/id. Osobne żądania podczas pracy crawlera mogą widzieć różne stany.

Eksport czyta wyłącznie wybrane kolumny, po jednym rekordzie; csv.writer odpowiada za quoting, podwajanie cudzysłowów i CRLF. Kodowanie UTF-8 z opcjonalnym BOM, separatory comma/semicolon/tab, jawne nagłówki i kolejność pól. Null i pusty string mają tę samą reprezentację pustej komórki CSV; baza pozostaje bez zmian. Podejrzane prefiksy formuł są zabezpieczane apostrofem przed oryginalną zawartością, również po whitespace/znakach sterujących/formatach Unicode. Nie ma przełącznika wyłączającego zabezpieczenie.

Plik jest przygotowywany przed wysłaniem nagłówków HTTP, w SpooledTemporaryFile (do 1 MiB RAM, następnie dysk). Limit 64 MiB i budżet 30 s sprawdzany między rekordami dają odpowiednio 413/503 zamiast pozornie poprawnego, uciętego pliku. Snapshot bazy jest zwalniany przed przesyłaniem pliku po 64 KiB. Generator i BackgroundTask zamykają plik po pobraniu/przerwaniu; wyjątki przygotowania także sprzątają zasoby. Body pojedynczego rekordu nadal podlega limitowi odpowiedzi crawlera; nie jest ucinane do CSV.

Widok /data wybiera sesję, /data/{id} ma serwerowe filtrowanie, tabelę 10 rekordów, szczegóły z pełnym body i ustawienia pobierania. Formularz filtrów wymaga Zastosuj; CSV używa zastosowanych filtrów, nie niezapisanej treści formularza i nie tylko bieżącej strony. Pola eksportu zachowują kolejność zaznaczenia. Pobieranie przez fetch sprawdza status błędu przed zapisem, ogranicza plik do limitu serwera, daje anulowanie, sprząta object URL oraz anuluje żądania po opuszczeniu widoku. Nie powstaje kopia wyników w localStorage.

### Projekcja grafu i statystyk

GET graph/stats rozpoczyna jawną transakcję odczytu SQLite przed pierwszym SELECT (także w legacy transaction mode Pythona 3.12). Status, strony i linki w pojedynczej odpowiedzi pochodzą z tego samego snapshotu. Dwa oddzielne żądania podczas crawlowania mogą różnić się stanem; UI używa summary z odpowiedzi grafu i odświeża ją na żądanie.

Każdy Page jest węzłem `page:{uuid}`. Docelowy URL bez Page otrzymuje stabilny identyfikator `target:{sha256(url)}`. Jeden URL ma jeden węzeł, również gdy występuje jako hiperłącze i obraz; rodzaj nadal jest właściwością krawędzi. Nie łączymy różnych URL żądań według final_url. Każdy Link to osobna skierowana krawędź, także duplikaty i pętle. Utrwalone wyniki nie są modyfikowane.

Stopnie in/out liczą wystąpienia; unikalne stopnie liczą różnych sąsiadów. Pętla zwiększa oba stopnie o jeden. Unikalne relacje to pary źródło–cel niezależnie od kind. Wewnętrzność linku to zapisany is_external względem hosta startowego, nie hosta strony źródłowej. Osiągnięta głębokość obejmuje tylko HTML z final_url; maksymalna odkryta głębokość obejmuje Page także niepobrane. Zasoby mają wyłącznie poziom wizualny min(głębokość źródła + 1), nie zwiększają głębokości HTML. Puste maksima są null.

Projekcja nie pobiera body/description/keywords; title jest ograniczany w SQL do 500 znaków, pełna treść dostępna przez API szczegółów. Linki są odczytywane partiami. Statystyki nie budują listy krawędzi odpowiedzi. Wizualizacja ma limit 5000 węzłów / 20000 wystąpień linków: większa sesja zwraca jawne 413, bez losowego/ukrytego ucięcia, a UI pobiera pełne stats. Limit nie zmienia wyników crawlowania. Reprezentacja stats jest ograniczona istniejącymi budżetami sesji i może być kosztowna dla największych sesji.

Frontend ładuje Cytoscape dopiero przy wejściu na graf. Układ preset rozmieszcza poziomy według zapisanej głębokości, nie wylicza nowej ścieżki zamiast crawlera. ResizeObserver aktualizuje rozmiar, unmount usuwa instancję grafu i anuluje odczyty. Wybór przez canvas lub tekstową listę prowadzi do tego samego panelu; nie pobieramy zdalnych ikon/obrazów ani nie renderujemy zaufanego HTML z witryn.

Migracja `0003_crawler` rozszerza sesję o link_count, stop_reason, wersję crawlera i User-Agent, stronę o final_url oraz dodaje crawl_events z FK CASCADE i indeksem `(session_id, id)`. Zachowuje dane etapu 02; aplikacja nie używa create_all. SQLite 3.35+ jest wymagane do bezpiecznego downgrade kolumn bez odtwarzania tabel nadrzędnych. Sprawdzono migrację w obu kierunkach z istniejącymi stronami/linkami.

- Każda sesja ma własną konfigurację i wyniki; statusy zmienia pracownik. Transakcje BEGIN IMMEDIATE chronią start/edycję/usunięcie przed wyścigami. Konfiguracja pozostaje niezmienna po starcie.
- Jeden proces API na plik SQLite (egzekwowany blokadą OS), maksymalnie cztery aktywne sesje. Każda pobiera sekwencyjnie; concurrency jest górną granicą, efektywnie 1. Chroni to kolejność BFS/DFS przed wyścigami odpowiedzi.
- Ograniczony, porcjowany HTMLParser w jednym przejściu odkrywa nawigację i metadane bez wykonywania pobranego kodu. BeautifulSoup rozpoznaje deklaracje kodowania; BOM/HTTP/meta/UTF-8 mają jawną kolejność opisaną w API.md. Parser toleruje brakujące zamknięcia tagów, nie obiecuje naprawy DOM identycznej z przeglądarką. Łącza względne odnoszą się do końcowego URL i pierwszego base z atrybutem href (także pustym). Niepoprawny base daje fallback do końcowego URL. Zasoby są celami linków, nie są dodawane do kolejki HTML.
- Deduplikacja dotyczy znormalizowanych URL żądań. Różne adresy przekierowujące na tę samą stronę mogą wymagać osobnych prób; final_url zachowuje ich znaczenie. Query nie jest sortowane, zastrzeżone kodowania nie są dekodowane.
- DFS po znalezieniu krótszej ścieżki aktualizuje znaną głębokość i ponownie rozwija zapisane odnośniki bez drugiego pobrania strony. Przy ograniczeniach/błędach głębokość to minimum poznanych przejść, nie obietnica pełnego grafu.
- Strony pozostają unikalne po `(session_id, normalized_url)`. Linki zachowują wszystkie wystąpienia. FK pilnują zgodności sesji źródła/celu. Usunięcie sesji kaskadowo usuwa konfigurację, strony, linki, zdarzenia i członkostwa eksperymentów, zachowując inne sesje i rekord eksperymentu.
- Metadane HTTP i zdarzenie page_fetched zapisywane są od razu po odbiorze HTML. Po udanej analizie zapisuje się pola treści, potem osobno linki/nowe strony/progress. Dzięki temu anulowanie lub limit odkrywania nie usuwa już zapisanych wyników. Błąd samego parsera nie publikuje częściowej treści. Etap 04 używa istniejących kolumn Page z migracji 0002; nowa migracja nie jest potrzebna. Historyczne null nie są uzupełniane wstecz.

### Obsługiwane odnośniki

- hyperlinks: a[href], area[href].
- images_and_hyperlinks: powyższe oraz img[src].
- all_links: powyższe oraz link[href] (stylesheet, gdy rel zawiera ten token, inaczej other), script[src], audio/video/source/track/embed[src] (media), video[poster] (image), iframe[src] (other), object[data] (other), input[type=image][src] (image).

Każde wystąpienie HTTP/HTTPS jest normalizowane i zapisane; fragmenty są usuwane, powtórzenia zachowane. Wykrycie prywatnego celu nie daje zgody na pobranie — nadal obowiązuje walidacja sieci etapu 03. Nie obsługujemy srcset, CSS url(), linków generowanych przez JS ani dodatkowego pobierania zasobów. Dokładne reguły brakujących pól i tekstu body opisuje API.md.

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
