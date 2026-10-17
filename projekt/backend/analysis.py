"""Evidence-based comparisons and a self-contained, printable Polish report."""
import html
import json
import math

from .core import csv_export, sqlite_export


def experiments(store, session_id):
    rows = store.query("SELECT id FROM runs WHERE session_id=? ORDER BY created", (session_id,))
    result = []
    for row in rows:
        run = store.get_run(row["id"])
        result.append({**run, "metrics": store.metrics(run["id"])})
    candidates = [r for r in result if r["purpose"] == "experiment" and r["status"] == "completed"]
    best = max(candidates, key=lambda r: (r["metrics"]["pages"] / max(r["metrics"]["requests"], 1),
               r["metrics"]["pages"], -r["metrics"]["failures"]), default=None)
    recommendation = "Brak zakończonych eksperymentów. Uruchom serię 12 wariantów."
    if best:
        c, m = best["config"], best["metrics"]
        recommendation = (f"Najwydajniejszy zmierzony wariant: {c['strategy'].upper()} / {c['scope']} / {c['links']}. "
                          f"Pozyskano {m['pages']} stron przy {m['requests']} żądaniach "
                          f"({m['pages']/max(m['requests'],1):.2f} strony/żądanie), błędy: {m['failures']}. "
                          "Kryterium: strony/żądanie, następnie liczba stron i mniej błędów. "
                          "Wynik dotyczy tego adresu, limitów i czasu badania; nie jest uniwersalną oceną.")
    findings = []
    for key, label in (("strategy", "Strategia"), ("scope", "Zakres"), ("links", "Typy łączy")):
        pairs = []
        for i, a in enumerate(candidates):
            for b in candidates[i+1:]:
                ac, bc = a["config"], b["config"]
                if a["batch_id"] == b["batch_id"] and ac[key] != bc[key] and all(ac[k] == bc[k] for k in ac if k != key):
                    pairs.append(f"{ac[key]} → {bc[key]}: strony {a['metrics']['pages']} → {b['metrics']['pages']}, "
                                 f"łącza {a['metrics']['links']} → {b['metrics']['links']}, "
                                 f"żądania {a['metrics']['requests']} → {b['metrics']['requests']}")
        findings.append({"parameter": key, "label": label, "comparisons": pairs,
                         "note": "Porównania zmieniają tylko jeden parametr; WWW może zmieniać się pomiędzy przebiegami." if pairs else "Brak porównywalnych zakończonych przebiegów."})
    return {"runs": result, "recommendation": recommendation, "findings": findings}


def datasets(store, session_id):
    result = {}
    urls = {}
    for role in ("A", "B"):
        rows = store.query("SELECT id FROM runs WHERE session_id=? AND purpose=? ORDER BY created DESC LIMIT 1", (session_id, f"dataset_{role}"))
        if not rows:
            result[role] = None
            continue
        run = store.get_run(rows[0]["id"])
        records = [p for p in store.records(run["id"]) if p["kind"] == "page" and p["status"] == "ok"]
        urls[role] = {p["url"] for p in records}
        content = csv_export(store, run["id"]) if role == "A" else sqlite_export(store, run["id"])
        result[role] = dict(run_id=run["id"], config=run["config"], status=run["status"], records=len(records), size=len(content),
                            fields=["URL", "Keyword"] if role == "A" else ["pages", "metadata", "links", "run"],
                            completeness={k: sum(bool(p.get(k)) for p in records)/max(len(records), 1) for k in ("title", "description", "keywords", "body")})
    result["comparison"] = None
    if "A" in urls and "B" in urls:
        result["comparison"] = dict(common=len(urls["A"] & urls["B"]), only_a=len(urls["A"]-urls["B"]), only_b=len(urls["B"]-urls["A"]),
                                    usefulness_a="CSV URL/Keyword: prosty indeks adresów i deklarowanych słów kluczowych; bez relacji między stronami. Puste meta keywords ograniczają analizę tematyczną.",
                                    usefulness_b="SQLite: analiza grafu i zawartości, zapytania SQL, połączenia metadanych ze stronami; większy rozmiar i bardziej złożona obsługa.",
                                    caveat="Różnią się zakres, głębokość i format; różnic nie można przypisać wyłącznie strukturze bazy. Zbiory mogą być częściowe.")
    return result


def report(store, session_id):
    session = store.query("SELECT * FROM sessions WHERE id=?", (session_id,))[0]
    study = experiments(store, session_id)
    data = datasets(store, session_id)
    esc = lambda x: html.escape(str(x))
    completed = [r for r in study["runs"] if r["purpose"] == "manual" and r["status"] == "completed"]
    baseline = completed[-1] if completed else next((r for r in study["runs"] if r["purpose"] == "experiment" and r["config"]["strategy"] == "dfs" and r["config"]["scope"] == "server" and r["config"]["links"] == "hyperlinks" and r["status"] == "completed"), None)
    parts = [f"<h1>Badanie struktury WWW</h1><p>{esc(session['name'])} · {esc(session['url'])}</p>"]
    parts.append("<h2>1. Graf i charakterystyka strony</h2>")
    if baseline:
        m = baseline["metrics"]
        parts.append(f"<p>Podstrony HTML: {m['subpages']}; głębokość hiperłączy: {m['depth']}; głębokość przejścia: {m['traversal_depth']}; "
                     f"łącza: {m['links']}; unikalne krawędzie: {m['unique_edges']}. "
                     f"Warunek ≥20 podstron i ≥3 poziomów: {'spełniony' if m['qualifies'] else 'niespełniony'}.</p>")
        parts.append(f"<pre>{esc(json.dumps(baseline['config'], ensure_ascii=False, indent=2))}</pre>")
        graph = store.graph(baseline["id"])
        # Standalone SVG: every observed node shown, labels stay in adjacent table.
        positions = {}
        nodes = graph["nodes"]
        for i, n in enumerate(nodes):
            angle = 2*math.pi*i/max(len(nodes), 1)
            positions[n["url"]] = (400+340*math.cos(angle), 300+240*math.sin(angle))
        svg = ['<svg viewBox="0 0 800 600" role="img" aria-label="Graf odkrytych adresów">']
        for e in graph["edges"]:
            if e["source"] in positions and e["target"] in positions:
                x, y = positions[e["source"]]; tx, ty = positions[e["target"]]
                svg.append(f'<path d="M{x},{y} L{tx},{ty}" stroke="#c1cadb" fill="none"/>')
        for n in nodes:
            x, y = positions[n["url"]]
            color = "#347666" if n["status"] == "ok" else "#a8abb5"
            svg.append(f'<circle cx="{x}" cy="{y}" r="5" fill="{color}"><title>{esc(n["url"])}</title></circle>')
        parts.append("".join(svg)+"</svg>")
        parts.append("<table><tr><th>URL / tytuł</th><th>Status</th><th>Łącza / cele</th><th>Głębokość / dystans</th></tr>")
        for n in nodes:
            parts.append(f"<tr><td>{esc(n['url'])}<br>{esc(n.get('title') or '')}</td><td>{esc(n['status'])}</td><td>{n['outgoing']} / {n['unique_targets']}</td><td>{esc(n.get('depth'))} / {esc(n.get('distance'))}</td></tr>")
        parts.append("</table>")
    else:
        parts.append("<p>Brak zakończonego badania bazowego.</p>")
    parts.append("<h2>2. Zmiany parametrów przeszukiwania</h2><table><tr><th>Wariant</th><th>Status</th><th>Strony</th><th>Głębokość</th><th>Łącza</th><th>Zasoby</th><th>Błędy</th><th>Żądania</th><th>Czas [s]</th><th>Ograniczony</th></tr>")
    exp = [r for r in study["runs"] if r["purpose"] == "experiment"]
    for r in exp:
        c, m = r["config"], r["metrics"]
        parts.append(f"<tr><td>{esc(c['strategy']+' / '+c['scope']+' / '+c['links'])}</td><td>{esc(r['status'])}</td>"+
                     "".join(f"<td>{esc(m[k])}</td>" for k in ("pages", "depth", "links", "resources", "failures", "requests"))+
                     f"<td>{m['elapsed']:.1f}</td><td>{'tak' if m['truncated'] else 'nie'}</td></tr>")
    parts.append("</table>" + ("" if exp else "<p>Brak eksperymentów.</p>"))
    parts.append("<h2>3. Wpływ poszczególnych parametrów</h2>")
    for finding in study["findings"]:
        parts.append(f"<h3>{esc(finding['label'])}</h3><p>{esc(finding['note'])}</p><ul>" + "".join(f"<li>{esc(p)}</li>" for p in finding["comparisons"])+"</ul>")
    parts.append(f"<h2>4. Wariant praktyczny</h2><p>{esc(study['recommendation'])}</p>")
    for number, role, title in ((5, "A", "Pozyskanie danych i CSV URL/Keyword"), (7, "B", "Alternatywna struktura SQLite")):
        parts.append(f"<h2>{number}. {title}</h2>")
        item = data[role]
        if item:
            parts.append(f"<p>Status: {esc(item['status'])}; rekordy HTML: {item['records']}; eksport: {item['size']} B; pola/tabele: {esc(', '.join(item['fields']))}.</p><pre>{esc(json.dumps(item, ensure_ascii=False, indent=2))}</pre>")
        else:
            parts.append("<p>Brak danych. Uruchom przygotowanie zbiorów A/B.</p>")
        if number == 5:
            parts.append("<h2>6. Przydatność CSV</h2><p>Adresy i deklarowane słowa kluczowe pozwalają budować prosty indeks tematyczny. CSV nie zawiera krawędzi grafu ani treści strony. Brak meta keywords nie oznacza braku tematu; nie zastępujemy ich wymyślonymi wartościami.</p>")
    parts.append("<h2>8. Porównanie baz i zastosowań</h2>")
    if data["comparison"]:
        c = data["comparison"]
        parts.append(f"<p>Wspólne URL: {c['common']}; tylko A: {c['only_a']}; tylko B: {c['only_b']}.</p>"+"".join(f"<p>{esc(c[k])}</p>" for k in ("usefulness_a", "usefulness_b", "caveat")))
    else:
        parts.append("<p>Brak dwóch zbiorów do porównania.</p>")
    parts.append("<h2>Ograniczenia i odtwarzalność</h2><p>Analiza statycznego HTML, bez wykonywania JavaScript. robots.txt, błędy, limity i zmiany WWW mogą ograniczyć wynik. Zasoby nie są liczone jako podstrony. Korzeń ma głębokość 0. Dystans to najkrótsza ścieżka hiperłączy w zaobserwowanym grafie; głębokość przejścia opisuje pierwsze pobranie. Wszystkie liczby pochodzą z zapisanych przebiegów. Aplikacja zastępuje funkcje WebSPHINX i Win Web Crawler; nie uruchamia tych programów.</p>")
    return '<!doctype html><html lang="pl"><meta charset="utf-8"><title>Raport EZI</title><style>body{font:15px system-ui;color:#182b40;max-width:1100px;margin:40px auto;padding:24px}h1,h2{color:#1c6659}h2{margin-top:36px}table{border-collapse:collapse;width:100%;font-size:11px}td,th{border:1px solid #d6dce4;padding:7px;text-align:left;overflow-wrap:anywhere}pre{white-space:pre-wrap;background:#f3f5f7;padding:14px}svg{width:100%;max-height:600px}@media print{body{margin:0;padding:0}h2{break-after:avoid}tr{break-inside:avoid}pre{font-size:10px}}</style><body>'+"".join(parts)+"</body></html>"
