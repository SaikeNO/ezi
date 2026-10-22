# Instrukcja użytkownika — etap 08

## Codzienna praca

1. Uruchom backend i frontend według README. Na **Przeglądzie** sprawdź health oraz dashboard. **Odśwież dashboard** odczytuje jeden snapshot całej bazy: sesje według statusu, odkryte strony, odebrane HTML, linki, błędy i pięć najnowszych sesji. Ten sam URL w dwóch sesjach liczy się dwa razy. Dashboard nie uruchamia pobierania. Przy błędzie nie pokazuje wymyślonych zer.
2. W **Sesjach** podaj publiczny URL, ustaw konfigurację i utwórz sesję. Zapis nie rozpoczyna HTTP. W szczegółach wybierz **Uruchom crawler**; podczas działania dostępne jest anulowanie. Strona startowa ma depth 0. `max_pages` liczy próby, także błędy; HTML to osobny licznik.
3. W szczegółach wybierz graf: wyszukaj URL, wybierz węzeł, sprawdź stopnie, metadane, poziomy i statystyki. Zasób obrazu/CSS/JS może być celem grafu bez pobrania HTML. Odświeżaj wynik ręcznie. Błąd 413 oznacza przekroczony limit wizualizacji, a nie usunięte dane; pełne statystyki pozostają dostępne.
4. Otwórz **Dane i CSV**, zastosuj filtry, przejrzyj strony i body. W eksporcie wybierz pola w kolejności, separator oraz BOM. Eksport obejmuje wszystkie dopasowania zastosowanych filtrów. Dla ćwiczenia wybierz URL i Keyword, średnik, UTF-8 BOM. W arkuszu użyj importu UTF-8 i tego samego separatora; komórki przypominające formuły mają ochronny apostrof.
5. W **Porównaniach** utwórz 2–4 warianty tego samego start URL albo zaznacz istniejące zakończone/anulowane sesje. Pierwsza jest bazą A. Utworzenie eksperymentu zachowuje niezależne konfiguracje; następnie uruchom oczekujące warianty. Po zakończeniu wybierz porównanie. Zapisane sesje można porównać ponownie po restarcie bez ponownego HTTP.
6. W szczegółach sesji wybierz **Pobierz raport sesji HTML**. W gotowym porównaniu wybierz **Pobierz raport porównania HTML**. Otwórz pobrany plik w przeglądarce. Raport działa offline, zawiera datę wygenerowania UTC, identyfikatory, konfiguracje i zapisane pomiary. Tabele przewijają się poziomo na telefonie. Wydruk jest dostępny przez przeglądarkę; automatyczny eksport PDF nie jest implementowany ani gwarantowany.

## Jak oceniać wyniki

Raport sesji pokazuje strony i zasoby oddzielnie, głębokość, wystąpienia i unikalne relacje, linki startu/podstron, linki wewnętrzne/zewnętrzne, stopnie per page oraz obecność/brak metadanych. Puste Keyword jest obecnym polem, choć nie daje informacji tematycznej. Brak i pusty tekst różnią się w bazie, lecz mają identyczną pustą komórkę CSV. URL/Keyword nadaje się na prosty indeks; do analizy nawigacji potrzebny jest graf, do analizy treści również Title/Description/Body.

Raport porównania przedstawia metryki, zmiany parametrów, zbiory URL i typowanych krawędzi wspólne/unikalne oraz zmiany metadanych, liczby wystąpień, głębokości i kolejności. Rozwiń **Szczegóły zbiorów i treści (JSON)**, aby odczytać konkretne elementy. Każda lista pokazuje maksymalnie pierwsze 100 elementów i pełne `total`; kolejne partie są dostępne przez API porównania. Podgląd pola ma 500 znaków, SHA-256 obejmuje całość. Raport nie zawiera pełnego body wszystkich stron; pełna treść jest w eksploratorze/API/CSV.

Do analizy jednego hosta praktycznym punktem startu jest BFS/server/hyperlinks z jawnie dobranymi limitami. Oceń zmierzone pokrycie i błędy; zwiększaj depth dla większego zakresu, web+follow_external dla innych hostów, images/all_links dla analizy zasobów. Są to kompromisy celu i kosztu, nie automatyczny ranking szybkości. BFS/DFS może dać identyczny pełny graf. Różnice czasu obejmują robots, limiter, sieć i analizę; nie dowodzą przewagi samego algorytmu. Brak URL przy limicie lub błędzie nie dowodzi nieosiągalności.

## Interpretacja historycznych ustawień ćwiczenia

„Source WebSite/Dirs” interpretujemy jako badanie strony i jej osiągalnych podstron przez URL HTTP/HTTPS. Nie importujemy katalogów z dysku i nie naśladujemy historycznego formatu bazy. `server` oznacza ten sam host, nie prefiks katalogu URL; `web` wymaga `follow_external_urls=true`, aby pobierać inne hosty. Metadane są zawsze analizowane przy odebraniu HTML; nie ma osobnego przełącznika „URL/MetaTag”. CSV jest eksportem zapisanej sesji, a nie zapisem do arkusza podczas crawlowania. `process_one_page=false` umożliwia przechodzenie po odnośnikach. Te decyzje zachowują odtwarzalność ćwiczenia bez obietnicy identyczności z dawnym narzędziem.

## Stany i problemy

- Brak sesji: utwórz pierwszą. Pusta sesja queued daje pusty graf/CSV z nagłówkiem i raport z zerami pochodzącymi z bazy oraz oznaczeniem niepełnego wyniku.
- Brak backendu/błąd DB: sprawdź proces, migracje i `/health`, użyj przycisku ponowienia. Dashboard i raport pokazują własne błędy niezależnie od health.
- `completed` może obejmować błędy i limity. Sprawdź `stop_reason` i błędy stron. Failed/cancelled zachowują częściowe wyniki. Raporty jawnie oznaczają takie stany.
- Porównanie queued/running zwraca 409; poczekaj lub anuluj. Inne start URL też dają 409. Nie można ponownie uruchomić terminalnej sesji; utwórz nową.
- Raport sesji ma limit 5000 węzłów / 20000 linków (413). Dla większych sesji użyj stats/CSV. Porównanie/raport porównania: łącznie 20000 Page / 80000 Link / 64 MiB treści / 30 s analizy. Błędy limitów nie są zapisywane jako HTML. Pobieranie raportu można anulować.
- Publiczna aplikacja blokuje localhost, prywatne adresy i niedozwolone porty. Witryna laboratoryjna działa przez osobną aplikację testową opisaną w README; nie zmieniaj ochrony produkcyjnej ani pliku hosts.
- Jeden worker API na SQLite; sekwencyjne pobieranie w sesji, do czterech aktywnych sesji. Nagły restart zachowuje dane, oznacza przerwane zadania jako failed i nie wznawia kolejki.
