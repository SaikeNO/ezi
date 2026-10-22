"""Deterministic lab graph: root + 3 sections + 6 topics + 12 articles.

22 internal HTML pages; external page and HTTP error are additional targets.
Only test transport maps these virtual hosts to loopback.
"""


def page(title: str, links: str, keywords: str | None = "laboratorium, żółć") -> str:
    meta = "" if keywords is None else f'<meta name="keywords" content="{keywords}">'
    return (
        f'<!doctype html><html lang="pl"><head><meta charset="utf-8">'
        f"<title>{title}</title>{meta}"
        f'<meta name="description" content="Opis: {title}"></head>'
        f"<body><h1>{title}</h1><p>Treść, dane; polskie znaki.</p>{links}</body></html>"
    )


LAB_GRAPH = {
    "/lab/": page(
        "Laboratorium",
        "".join(f'<a href="/lab/s{s}">Dział {s}</a>' for s in range(3))
        + '<a href="/lab/s0#duplicate">Powtórzenie</a>'
        '<a href="http://other.example/lab/out">Zewnętrzna</a>'
        '<a href="/lab/missing">Błąd</a>'
        '<img src="/lab/image.png"><link rel="stylesheet" href="/lab/style.css">'
        '<script src="/lab/app.js"></script>',
    ),
    "/lab/out": page("Zewnętrzna", ""),
    "/lab/missing": (503, {}, "Kontrolowany błąd"),
}
for section in range(3):
    LAB_GRAPH[f"/lab/s{section}"] = page(
        f"Dział {section}",
        "".join(f'<a href="/lab/s{section}/t{t}">Temat {t}</a>' for t in range(2))
        + '<a href="/lab/">Cykl</a>',
    )
    for topic in range(2):
        path = f"/lab/s{section}/t{topic}"
        LAB_GRAPH[path] = page(
            f"Temat {section}/{topic}",
            "".join(f'<a href="{path}/a{a}">Artykuł {a}</a>' for a in range(2)),
            keywords=None,
        )
        for article in range(2):
            LAB_GRAPH[f"{path}/a{article}"] = page(
                f"Artykuł {section}/{topic}/{article}",
                '<a href="/lab/">Start</a>',
                keywords="=1+1" if article == 0 else "",
            )
