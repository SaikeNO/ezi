# Architektura i semantyka crawlera

## Stan po etapie 02

Działa monorepo, health API/SQLite i pełna obsługa zapisu, odczytu, listowania, edycji oraz usuwania sesji. Polski interfejs korzysta z REST API i przechowuje w SQLite wszystkie parametry konfiguracji. Nie ma jeszcze wykonywania crawlowania.

Schemat wdraża migracja `0002_sessions`: `sessions`, `crawl_config`, `pages`, `links`, `experiments` i tabela członkostw `experiment_sessions`. `Base` zawiera pełną typowaną metadokumentację SQLAlchemy. Schemat zmienia Alembic; aplikacja nie wywołuje `create_all`.

- Każda sesja ma własną konfigurację (PK/FK `session_id`), status, czasy UTC i liczniki. Nowa sesja jest `queued`; nie można podać statusu/liczników w JSON tworzenia ani edycji.
- Konfigurację można zmienić tylko przed uruchomieniem, co zachowuje odtwarzalność przyszłych wyników. PATCH zastępuje przekazany blok konfiguracji. Wyniki i start/cancel należą do następnych etapów.
- SQLite ma włączone `foreign_keys`. Usunięcie sesji kaskadowo usuwa jej konfigurację, strony, linki i członkostwa eksperymentów; sam eksperyment i inne sesje pozostają. Sesji `running` nie można usunąć.
- Strony są unikalne po `(session_id, normalized_url)`. Pole `fetch_order=null` oznacza brak pobrania; wykrycie strony i pobranie nie są utożsamiane.
- Linki zachowują **każde wystąpienie**, także powtórzenia tego samego celu. Są indeksowane po sesji/źródle i sesji/URL celu. Miary unikalnych krawędzi w etapie 05 będą liczone osobno.
- Złożone FK pilnują zgodności sesji linku i strony źródłowej/docelowej. Usunięcie strony docelowej zeruje opcjonalne `target_page_id` i zachowuje `target_url`; kontrola docelowego FK jest odroczona do końca transakcji. Relacje źródła/celu i lista linków wychodzących są widokami ORM; zapis Link używa jawnych ID.
- Eksperyment może odnosić się do wielu sesji, a sesja do wielu eksperymentów. W tym etapie istnieje model i relacje, bez API eksperymentów.
- SQLite przechowuje naiwne daty UTC; `UTCDateTime` wymaga strefy przy zapisie i odtwarza świadome UTC przy odczycie.
- Walidacja wejścia obejmuje skończone limity, enumy i składnię/publiczne literały IP start URL. Nie ma rozwiązywania DNS ani zdalnych żądań przy tworzeniu sesji. Pełne zabezpieczenia transportu zostaną wdrożone wraz z crawlerem.

Pozostałe komponenty poniżej stanowią plan kolejnych etapów. Limity konfiguracji i wdrożone kontrakty opisuje `API.md`.

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
