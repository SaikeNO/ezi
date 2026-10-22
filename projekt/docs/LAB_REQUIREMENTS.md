# Mapowanie wymagań laboratorium

## I. Struktura sieci WWW

| Punkt | Wymaganie | Funkcja w WebCrawler Studio | Test akceptacyjny |
|---|---|---|---|
| I.1 | Graf witryny z >=3 poziomami, >=20 podstron; głębokość i liczenie linków | Crawl + Graph + Statistics | Testowa witryna osiąga wymagane rozmiary, prawidłowe liczniki per page |
| I.2 | Zmiana BFS; server/web; images+hyperlinks/all links | Konfiguracja strategii, scope i link types | Warianty zmieniają kolejność/zakres/typy wykryć zgodnie ze specyfikacją |
| I.3 | Analiza wpływu parametrów | Eksperymenty i tabele porównawcze | Zmiany liczby stron, krawędzi, linków i czasu są mierzone |
| I.4 | Wybór praktycznej kombinacji | Raport porównawczy i interpretacja | Raport pokazuje kompromisy wydajność/zakres/kompletność; bez automatycznych nieuzasadnionych ocen |

## II. Struktury przechowywania danych

| Punkt | Wymaganie | Funkcja w WebCrawler Studio | Test akceptacyjny |
|---|---|---|---|
| II.5 | Nowa sesja, Source WebSite/Dirs, start URL, zapis CSV, URL/MetaTag, linki zewn., bez one-page, depth 2, pola URL/Keyword | Sesje + Crawler + Extractor + CSV | Ustawienia są zachowane; CSV ma wybrane pola, separator i dane |
| II.6 | Ocena przydatności struktury i danych | Eksplorator danych / raport | Raport ujmuje użyteczność URL/keywords i ograniczenia brakujących metadanych |
| II.7 | Inna baza z tego samego URL, inne parametry | Druga niezależna sesja | Obie sesje są zachowane i odtwarzalne |
| II.8 | Porównanie budowy, treści, zastosowań | Comparison | Pokazuje strony/linki wspólne i unikalne, metadane, schemat pól i zastosowania |

## Scenariusz końcowy

Wykonane dowody, dokładna topologia 22 HTML/depth 3, konfiguracje i oczekiwane liczniki dla wszystkich ośmiu punktów: [ACCEPTANCE.md](ACCEPTANCE.md). Obsługa aplikacji i jawna interpretacja historycznych opcji: [USER_GUIDE.md](USER_GUIDE.md). Wyniki QA: [PHASE_08.md](PHASE_08.md).

1. Uruchom aplikację i lokalną deterministyczną witrynę testową (minimum 21 stron, trzy przejścia od startu).
2. Utwórz sesję A: depth 3, BFS, server, hyperlinks. Uruchom crawl i sprawdź graf/liczniki.
3. Uruchom warianty strategii, zakresu i typu linków. Zapisz wyniki i porównaj.
4. Utwórz sesję B z depth 2, włączonym podążaniem za linkami zewnętrznymi i ekstrakcją metadanych. Eksportuj CSV pól `URL` oraz `Keyword`.
5. Utwórz sesję C z innymi parametrami; porównaj B/C pod względem struktury i treści.
6. Wygeneruj raport zawierający konfigurację, metryki, różnice i uzasadnione wnioski.

## Uwaga o interpretacji

Historyczne aplikacje mogą inaczej rozumieć `server`, `web` i `all links`. Obowiązuje jawna semantyka opisana w `ARCHITECTURE.md`, którą trzeba przedstawić w dokumentacji końcowej. Linki zewnętrzne nie powinny automatycznie znosić ograniczeń bezpieczeństwa.
