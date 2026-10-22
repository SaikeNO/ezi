# Osiem wymagań — scenariusze akceptacyjne

Stan: etap 08. Źródło oczekiwań: `LAB_REQUIREMENTS.md`. Dane testowe są jawnie kontrolowaną witryną; żaden licznik nie jest wstawiany do crawlera ani produkcyjnego UI.

## Witryna i warianty

`backend/tests/lab_site.py` definiuje root `/lab/`, 3 działy (depth 1), 6 tematów (depth 2), 12 artykułów (depth 3): **22 poprawne wewnętrzne HTML, w tym 21 podstron**. Dodatkowo: jeden zewnętrzny HTML `other.example`, jedna odpowiedź 503, powtórzone hiperłącze z różnymi fragmentami, cykle, obraz, CSS, JS, polskie znaki, brakujące/puste keywords i wartość przypominająca formułę. Serwer HTTP jest deterministyczny; czas i identyfikatory sesji pozostają rzeczywistymi zmiennymi pomiarami.

`site_fixture.website` uruchamia prawdziwy serwer TCP na losowym porcie loopback. Testowy transport mapuje wyłącznie `site.example` i `other.example` na ten serwer. `e2e_app.py` udostępnia go crawlerowi w osobnej aplikacji testowej. Obraz produkcyjny nie kopiuje `tests`; brak przełącznika pozwalającego na prywatne IP.

Wariant A: BFS/server/hyperlinks/depth 3, max_pages 100, request_delay_ms 100, robots true, one-page false. A-DFS zmienia tylko strategię. A-images zmienia tylko link_types na images_and_hyperlinks; A-all na all_links. B: BFS/web/hyperlinks/depth 2, follow_external true, pozostałe jak A.

| Wariant | Odebrane HTML | Odkryte Page | Linki | Głębokość HTML | Błędy |
|---|---:|---:|---:|---:|---:|
| A / A-DFS | 22 | 24 | 39 | 3 | 1 |
| A-images | 22 | 24 | 40 | 3 | 1 |
| A-all | 22 | 24 | 42 | 3 | 1 |
| B | 11 | 24 | 27 | 2 | 1 |

W A: start ma 6 wystąpień / 5 unikalnych celów; podstrony 33 wystąpienia / 19 unikalnych celów. 38 wewnętrznych i 1 zewnętrzny link; 38 unikalnych relacji. Poziomy odebranego HTML: 1/3/6/12. Keyword: 16 obecnych (w tym 6 pustych), 6 brakujących. B pobiera root + 3 działy + 6 tematów + zewnętrzny HTML. Artykuły są odkryte, ale nie pobrane.

## Macierz dowodów i ręczna akceptacja

| Punkt | Automatyczny dowód | Scenariusz w UI / kryterium |
|---|---|---|
| I.1 | `test_reporting.py::test_all_eight_lab_requirements_real_tcp_report_csv_comparison_and_restart`, `test_graph.py`, `e2e/graph.spec.ts`, `e2e/reports.spec.ts` | Uruchom A na `/lab/`. Otwórz graf: 22 HTML, osiągnięta głębokość 3. Węzły/linki i stopnie zgadzają się ze stats; start 6 linków, podstrony 33. Wybierz węzeł, powiększ/przesuń, wyszukaj URL. |
| I.2 | Ten sam test laboratoryjny; `test_crawler_engine.py` (BFS/DFS, scope, typy); `test_comparison.py::test_parameter_variants_have_measured_set_differences` | Zachowaj A-DFS, A-images, A-all i B. BFS/DFS: różna kolejność, ten sam pełny zbiór. Linki 39/40/42. Zewnętrzny HTML jest pobierany tylko przez web+follow_external. |
| I.3 | `test_comparison.py`, test laboratoryjny i E2E eksperymentów/raportów | Porównaj A/B: wspólne HTML 10, tylko A 12, tylko B 1. Sprawdź zmienione parametry, linki, głębokość i rzeczywiste czasy. Wykresy i tabele używają danych API. |
| I.4 | Test laboratoryjny asercje sekcji raportu + kontrola raportu w E2E | Pobierz raport porównania. Dla analizy jednego hosta wybierz zakres server i oceń 22 HTML/1 błąd; B daje zewnętrzny HTML przy mniejszym depth, ale pomija 12 artykułów. Uzasadnij wybór celem, zasięgiem i kosztami. Raport nie ogłasza uniwersalnego zwycięzcy. |
| II.5 | Test laboratoryjny: zachowana konfiguracja B, CSV URL/Keyword/średnik; `test_explorer.py`; `e2e/explorer.spec.ts` | Utwórz B: depth 2, follow external true, one-page false. Eksportuj URL/Keyword, średnik, BOM. Nagłówek `URL;Keyword`, 24 rekordy (w tym odkryte niepobrane), polskie litery. Sprawdź import tekstowy UTF-8; formuły zabezpieczone. |
| II.6 | Raport pokrycia metadanych (asercja Keyword 16/6), testy ekstrakcji/CSV | Raport A i eksplorator rozróżniają obecne/puste/brakujące pola. Opisz URL/Keyword jako indeks tematyczny, ograniczenia metadanych i potrzebę Title/Description/Body. CSV stron nie przechowuje relacji grafu. |
| II.7 | Niezależne sesje/config, zamknięcie i ponowne otwarcie aplikacji w teście laboratoryjnym; testy sesji/porównań; reload w E2E | Utwórz B oraz A-all z tego samego start URL. Obie sesje i różne konfiguracje pozostają po restarcie. Nie nadpisuj poprzedniej sesji. |
| II.8 | Test laboratoryjny B/A-all: tylko B 1, tylko A-all 12; `test_comparison.py` (treść, hashe, null/pusty, multiplicity); `e2e/reports.spec.ts` | Porównaj B/A-all: wspólne/unikalne HTML i typowane krawędzie, schemat pól i pokrycie metadanych, pełne hashe i podglądy zmienionych treści. Niezmieniona deterministyczna wspólna treść daje 0 zmian — nie fabrykuj różnic. Raport wyjaśnia zastosowania indeksu i grafu. |

## Wykonanie

Z `projekt/backend`: `uv run pytest tests/test_reporting.py -q` wykonuje pełny scenariusz laboratoryjny (pięć prawdziwych crawlów), bezpieczeństwo raportu, statusy, dashboard i budżety. `uv run pytest` obejmuje też wszystkie poprzednie etapy: normalizację, BFS/DFS, głębokość, scope, extraction, CSV, comparison, SSRF/robots/redirecty, anulowanie i migracje.

Z `projekt/frontend`: `npm test`, `npm run build`, `npm run test:e2e`. Playwright uruchamia własny backend/witrynę/frontend, pobiera rzeczywiste pliki HTML/CSV, renderuje raporty, porównuje liczniki z API oraz sprawdza desktop i telefon. Osobny test pustego dashboardu świadomie przechwytuje pustą odpowiedź API, ponieważ inne testy zachowują sesje; pełny pusty stan rzeczywistej DB sprawdza test backendu. Wyniki konkretnego uruchomienia i pozostałe ograniczenia: `PHASE_08.md`.
