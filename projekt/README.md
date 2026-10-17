# EZI — Laboratorium WWW

Lokalna aplikacja do badania grafu WWW i struktur przechowywania treści. Polski interfejs, własny adres startowy, historia SQLite, eksporty i raport obejmujący punkty 1–8 dokumentu **Ps 1-2.pdf**. Zastępuje funkcje WebSPHINX i Win Web Crawler; nie uruchamia tych narzędzi.

## Uruchomienie w Windows

Wymagania: Python 3.11+ i Node.js 22.12+ (sprawdzono na Python 3.14 i Node 22). Z katalogu `C:\studia\ezi\projekt`:

```powershell
.\setup.ps1
.\start.ps1
```

Otwórz http://127.0.0.1:8000. Zatrzymanie serwera: Ctrl+C. W przypadku blokady skryptów można wywołać `powershell -ExecutionPolicy Bypass -File .\setup.ps1`, a następnie analogicznie `start.ps1`. Skrypty nie zmieniają systemowej polityki PowerShell.

## Struktura katalogów

```text
ezi/
├── Ps 1-2.pdf
└── projekt/
    ├── frontend/       # React, TypeScript, Vite, testy przeglądarkowe
    │   ├── src/
    │   ├── tests/browser/
    │   └── dist/       # zbudowany interfejs serwowany przez backend
    ├── backend/        # FastAPI, crawler, eksporty i raporty
    │   ├── tests/      # testy Python i serwery fixture
    │   ├── data/       # lokalna baza SQLite
    │   ├── .venv/      # środowisko Python
    │   └── requirements.txt
    ├── setup.ps1
    └── start.ps1
```

## Przebieg ćwiczenia

1. **Przegląd:** podaj rzeczywisty URL i uruchom bazowy DFS / server / hiperłącza, głębokość 3. Jeżeli witryna jest za mała lub płaska, utwórz sesję z innym adresem. Aplikacja nigdy nie dopisuje brakujących stron. Panel sprawdza ≥20 poprawnie pobranych podstron HTML, bez korzenia, i dystans hiperłączy ≥3.
2. **Graf WWW:** filtruj węzły, przesuwaj i powiększaj graf, klikaj węzły. Tabela podaje liczbę wystąpień łączy, unikalnych celów i oba rodzaje głębokości.
3. **Eksperymenty:** uruchom 12 wariantów (DFS/BFS × server/web × hiperłącza/obrazy+hiperłącza/wszystkie). Wspólne limity pochodzą z konfiguracji w Przeglądzie. Badania wykonują się kolejno; przy domyślnym opóźnieniu pełna seria może trwać długo. Zatrzymanie kończy także kolejkę.
4. **Dane stron:** przygotuj zbiory A/B. A: BFS, web, głębokość 2, wszystkie dostępne podstrony w granicach limitów, CSV dokładnie `URL,Keyword`. B: ten sam URL, BFS, server, głębokość 3, relacyjna baza SQLite. Pozostałe limity wspólne. Porównanie pokazuje pokrycie, kompletność i rozmiar eksportów. Rozwiń konfigurację zbioru, aby zobaczyć parametry.
5. Pobierz oba zbiory. Własny CSV: wybierz pola w menu **Pola CSV**. Pole Keyword to dosłowne meta keywords, bez zgadywania i generowania słów kluczowych.
6. **Raport:** otwórz raport HTML, wydrukuj do PDF przez przeglądarkę lub pobierz samodzielny HTML z osadzonym grafem. Raport oznacza brakujące i częściowe wyniki oraz zawiera wnioski na podstawie rzeczywistych pomiarów.

## Zachowanie crawlera

- Korzeń ma poziom 0. **Głębokość przejścia** opisuje pierwsze pobranie; **dystans hiperłączy** to najkrótsza ścieżka w odkrytym grafie (przekierowania mają koszt 0). Niebędące HTML zasoby nie zwiększają liczby stron wymaganej w zadaniu.
- Server oznacza identyczny hostname i efektywny port (nie wszystkie subdomeny). Web pozwala na adresy zewnętrzne. Każdy skok przekierowania ponownie sprawdza zakres i robots.txt.
- Hiperłącza: `a`, `area`, `frame`, `iframe`. Obrazy + hiperłącza: dodatkowo `img/input src`. Wszystkie: także referencje HTML do zasobów, formularzy i srcset. Brak wykonywania formularzy, JavaScript, parsowania CSS czy pobierania załączników z przeglądarką.
- HTTP/HTTPS, normalizacja hosta i domyślnych portów, usuwanie fragmentów, zachowane query string. Inne schematy są rejestrowane, lecz niepobierane.
- Kolejne żądania mają opóźnienie; domyślnie 1 s, timeout 15 s, limit 200 stron i 500 zasobów, odpowiedź maks. 5 MB. Limity stron/zasobów dotyczą prób pobrania zaplanowanych jako strony/zasoby; rozpoznany typ wynika z Content-Type. Żądania robots i przekierowania są widoczne w koszcie HTTP. Zmniejszenie opóźnienia stosuj tylko na serwerach, na których jest to właściwe.
- robots.txt: 404/inne 4xx poza 401/403 = brak reguł; 401/403, 5xx, przekierowanie robots lub niedostępność = zachowawcza blokada serwera. Używany User-Agent: `EZILab/1.0`. Uwzględniane są także Crawl-delay i Request-rate; mogą zwiększyć opóźnienie ponad ustawioną wartość.
- Jeden aktywny crawl w procesie serwera. Uruchamiaj jeden proces, bez `--workers` i bez autoreload podczas badań. Po restarcie niezakończone przebiegi są oznaczane jako przerwane; wyniki zostają.
- Rekomendacja: największy stosunek pobranych stron do liczby żądań, następnie większa liczba stron, następnie mniej błędów. Porównania wpływu parametrów zestawiają przebiegi z tej samej serii różniące się jednym parametrem.
- Dane w `backend/data/ezi.sqlite`; kopię wykonuj po zatrzymaniu serwera. Nie jest to serwer do publicznego wdrożenia. Działa lokalnie bez kont i kluczy API.

## API i rozwój

Dokumentacja: http://127.0.0.1:8000/docs. API `/api`: sesje, przebiegi, kolejka eksperymentów, przygotowanie A/B, status, anulowanie, graf, rekordy, porównania, CSV, SQLite i raport. Konfiguracje przebiegów są niezmienne. Baza eksportu ma tabele `run`, `pages`, `metadata`, `links`; `metadata.page_id` i `links.source_id` odwołują się do `pages.id`, cel łącza pozostaje URL, również gdy nie został pobrany.

```powershell
# Wszystkie polecenia z katalogu projekt
# Terminal 1
.\backend\.venv\Scripts\python.exe -m uvicorn backend.app:create_app --factory --host 127.0.0.1 --port 8000
# Terminal 2: Vite z proxy /api
npm.cmd --prefix frontend run dev
# Kontrola typów i build
npm.cmd --prefix frontend run build
# Testy backendu, bez zależności od Internetu
.\backend\.venv\Scripts\python.exe -m pytest -c backend/pytest.ini backend/tests -q
# Jednorazowo przeglądarka testowa, następnie test E2E
Push-Location frontend
npx.cmd playwright install chromium
npm.cmd run test:e2e
Pop-Location
```

Serwery fixture istnieją wyłącznie w testach. Nie ma demonstracyjnej witryny w aplikacji. Fonty interfejsu korzystają z lokalnych fontów systemowych; Internet jest potrzebny tylko do instalacji zależności oraz badania wybranej witryny.
