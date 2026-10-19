import { useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { sessionsApi, graphApi } from "@/lib/sessions-api";
import { emptyFilters, explorerApi, fieldLabels, saveCsv, type ExportField, type PageFilters, type PageList, type Separator } from "@/lib/explorer-api";
import type { SessionList } from "@/types/sessions";
import type { PageDetail } from "@/types/graph";

const message = (error: unknown) => error instanceof Error ? error.message : "Nie udało się pobrać danych.";
const cell = (text: string | null) => text === null ? "Brak" : text || "(puste)";

function Detail({ id, pageId }: { id: string; pageId: string }) {
  const [detail, setDetail] = useState<PageDetail | null>(null);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    const controller = new AbortController(); setDetail(null); setError("");
    graphApi.page(id, pageId, controller.signal).then(data => {
      if (!controller.signal.aborted) setDetail(data);
    }, error => { if (!controller.signal.aborted) setError(message(error)); });
    return () => controller.abort();
  }, [id, pageId, attempt]);
  return <section aria-label="Zapisana treść strony" className="mt-6 rounded-2xl border bg-card p-5">
    <h2 className="text-xl font-semibold">Zapisana treść strony</h2>
    {error && <><p role="alert">{error}</p><Button onClick={() => setAttempt(value => value + 1)}>Ponów odczyt treści</Button></>}
    {!detail && !error && <p role="status">Wczytywanie treści…</p>}
    {detail && <dl className="mt-4 space-y-4 text-sm">{Object.entries({ "Tytuł": detail.title, "Opis": detail.description,
      "Słowa kluczowe": detail.keywords, "Końcowy URL": detail.final_url, "Kodowanie": detail.encoding,
      "Content-Type": detail.content_type, "Body": detail.body }).map(([label, value]) =>
      <div key={label}><dt className="text-muted-foreground">{label}</dt><dd className="max-h-72 overflow-y-auto whitespace-pre-wrap break-all">{cell(value)}</dd></div>)}</dl>}
  </section>;
}

function ExplorerSession({ id }: { id: string }) {
  const [draft, setDraft] = useState<PageFilters>(emptyFilters);
  const [filters, setFilters] = useState<PageFilters>(emptyFilters);
  const [offset, setOffset] = useState(0);
  const [attempt, setAttempt] = useState(0);
  const [data, setData] = useState<PageList | null>(null);
  const [error, setError] = useState("");
  const [pageId, setPageId] = useState<string | null>(null);
  const [fields, setFields] = useState<ExportField[]>(["url", "keywords"]);
  const [separator, setSeparator] = useState<Separator>("comma");
  const [bom, setBom] = useState(true);
  const [exportState, setExportState] = useState("");
  const [exportError, setExportError] = useState("");
  const download = useRef<AbortController | null>(null);
  useEffect(() => () => download.current?.abort(), []);
  useEffect(() => {
    const controller = new AbortController(); setData(null); setError(""); setPageId(null);
    explorerApi.pages(id, filters, offset, controller.signal).then(data => {
      if (!controller.signal.aborted) setData(data);
    }, error => { if (!controller.signal.aborted) setError(message(error)); });
    return () => controller.abort();
  }, [id, filters, offset, attempt]);
  const apply = (next: PageFilters) => {
    download.current?.abort(); download.current = null; setExportState(""); setExportError("");
    setFilters(next); setOffset(0);
  };
  return <>
    <div className="mt-5 flex flex-wrap gap-4 text-sm text-teal-800 underline"><Link to={"/sessions/" + id}>Szczegóły sesji</Link><Link to={"/graph/" + id}>Graf sesji</Link></div>
    <form className="mt-6 rounded-2xl border bg-card p-5" aria-label="Filtry stron" onSubmit={event => { event.preventDefault(); apply({ ...draft }); }}>
      <h2 className="text-xl font-semibold">Filtry stron</h2>
      <label className="mt-4 block text-sm">Szukaj w URL i metadanych<input maxLength={200} value={draft.q} onChange={event => setDraft({ ...draft, q: event.target.value })} className="mt-2 block w-full rounded-lg border p-2" /></label>
      <p className="mt-2 text-xs text-muted-foreground">Dosłowny fragment URL, tytułu, opisu lub keywords, bez rozróżniania wielkości liter. Wyszukiwanie nie obejmuje body.</p>
      <div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <label className="text-sm">Głębokość<input type="number" min={0} max={21} value={draft.depth} onChange={event => setDraft({ ...draft, depth: event.target.value })} className="mt-2 block w-full rounded-lg border p-2" /></label>
        <label className="text-sm">Pobrany HTML<select value={draft.fetched} onChange={event => setDraft({ ...draft, fetched: event.target.value })} className="mt-2 block w-full rounded-lg border p-2"><option value="">Wszystkie</option><option value="true">Tak</option><option value="false">Nie</option></select></label>
        <label className="text-sm">Błąd strony<select value={draft.has_error} onChange={event => setDraft({ ...draft, has_error: event.target.value })} className="mt-2 block w-full rounded-lg border p-2"><option value="">Wszystkie</option><option value="true">Z błędem</option><option value="false">Bez błędu</option></select></label>
        <label className="text-sm">Status HTTP<input type="number" min={100} max={599} value={draft.http_status} onChange={event => setDraft({ ...draft, http_status: event.target.value })} className="mt-2 block w-full rounded-lg border p-2" /></label>
      </div>
      <div className="mt-5 flex flex-wrap gap-3"><Button type="submit">Zastosuj filtry</Button><Button type="button" variant="outline" onClick={() => { setDraft(emptyFilters); apply({ ...emptyFilters }); }}>Wyczyść filtry</Button><Button type="button" variant="outline" onClick={() => setAttempt(value => value + 1)}>Odśwież dane</Button></div>
    </form>
    {error && <p role="alert" className="mt-5">{error}</p>}
    {!data && !error && <p role="status" className="mt-5">Wczytywanie stron…</p>}
    {data && <section aria-label="Wyniki stron" className="mt-6 min-w-0 rounded-2xl border bg-white p-5">
      <h2 className="text-xl font-semibold">Zapisane strony</h2><p className="my-3 text-sm">Pasujące strony: {data.total}. Widok obejmuje także odkryte, niepobrane cele hiperłączy.</p>
      {data.items.length === 0 ? <p>Brak stron dla wybranych filtrów.</p> : <div className="overflow-x-auto" tabIndex={0} aria-label="Tabela stron — przewiń poziomo">
        <table className="w-full min-w-[850px] table-fixed text-left text-sm"><caption className="sr-only">Strony zapisane w wybranej sesji</caption>
          <thead><tr>{["URL", "Title", "Keyword", "Description", "Poziom / HTTP", "Treść"].map(label => <th className="px-2 py-3" key={label}>{label}</th>)}</tr></thead>
          <tbody>{data.items.map(row => <tr key={row.id} className="border-t align-top">
            {[row.normalized_url, row.title, row.keywords, row.description].map((value, index) => <td key={index} className="break-all px-2 py-3"><span className="line-clamp-4">{cell(value)}</span></td>)}
            <td className="px-2 py-3">{row.depth} / {row.http_status ?? "—"}<br />{row.final_url ? "Pobrany HTML" : "Niepobrany HTML"}{row.error && <p className="mt-1 break-all text-red-800">{row.error}</p>}</td>
            <td className="px-2 py-3"><Button variant="outline" aria-label={"Treść strony " + row.normalized_url} onClick={() => setPageId(row.id)}>Szczegóły</Button></td>
          </tr>)}</tbody>
        </table>
      </div>}
      <div className="mt-5 flex flex-wrap items-center gap-3"><Button variant="outline" disabled={offset === 0} onClick={() => setOffset(value => Math.max(0, value - 10))}>Poprzednie strony</Button><span className="text-sm">Od {data.total ? offset + 1 : 0} do {Math.min(offset + 10, data.total)} z {data.total}</span><Button variant="outline" disabled={offset + 10 >= data.total} onClick={() => setOffset(value => value + 10)}>Następne strony</Button></div>
    </section>}
    {pageId && <Detail key={pageId} id={id} pageId={pageId} />}
    <section aria-label="Eksport CSV" className="mt-6 rounded-2xl border bg-card p-5">
      <h2 className="text-xl font-semibold">Eksport CSV</h2>
      <p className="mt-3 text-sm text-muted-foreground">Eksport wszystkich stron pasujących do zastosowanych filtrów, ze wszystkich stron tabeli. Zmiany w formularzu najpierw zastosuj. Puste pola CSV oznaczają brak lub pustą treść. Wartości przypominające formuły otrzymują prefiks apostrofu.</p>
      <fieldset className="mt-5"><legend className="text-sm font-medium">Pola — kolejność według wyboru</legend><div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-3">{Object.entries(fieldLabels).map(([key, label]) => <label key={key} className="text-sm"><input type="checkbox" checked={fields.includes(key as ExportField)} onChange={event => setFields(current => event.target.checked ? [...current, key as ExportField] : current.filter(field => field !== key))} className="mr-2" />{label}</label>)}</div></fieldset>
      <p className="mt-3 break-words text-sm">Kolejność kolumn: {fields.map(field => fieldLabels[field]).join(" → ") || "Brak wybranych pól"}</p>
      <div className="mt-5 flex flex-wrap items-center gap-5"><label className="text-sm">Separator<select value={separator} onChange={event => setSeparator(event.target.value as Separator)} className="ml-3 rounded-lg border p-2"><option value="comma">Przecinek (,)</option><option value="semicolon">Średnik (;)</option><option value="tab">Tabulator</option></select></label><label className="text-sm"><input type="checkbox" checked={bom} onChange={event => setBom(event.target.checked)} className="mr-2" />UTF-8 z BOM</label></div>
      <Button className="mt-5" disabled={fields.length === 0 || exportState === "busy" || !data} onClick={async () => {
        const controller = new AbortController(); download.current = controller; setExportError(""); setExportState("busy");
        try {
          const blob = await explorerApi.csv(id, filters, fields, separator, bom, controller.signal);
          if (!controller.signal.aborted) { saveCsv(blob, id); setExportState("done"); }
        } catch (error) { if (!controller.signal.aborted) { setExportError(message(error)); setExportState(""); } }
        finally { if (download.current === controller) download.current = null; }
      }}>{exportState === "busy" ? "Przygotowywanie CSV…" : "Pobierz CSV"}</Button>
      {exportState === "busy" && <Button variant="outline" className="mt-5 ml-3" onClick={() => { download.current?.abort(); download.current = null; setExportState(""); }}>Anuluj pobieranie</Button>}
      {exportError && <p role="alert" className="mt-3">{exportError}</p>}{exportState === "done" && <p role="status" className="mt-3">Plik CSV przekazany do pobrania.</p>}
    </section>
  </>;
}

function SessionChooser() {
  const [data, setData] = useState<SessionList | null>(null);
  const [offset, setOffset] = useState(0);
  const [attempt, setAttempt] = useState(0);
  const [error, setError] = useState("");
  useEffect(() => {
    const controller = new AbortController(); setData(null); setError("");
    sessionsApi.list(offset, "", controller.signal).then(data => { if (!controller.signal.aborted) setData(data); }, error => { if (!controller.signal.aborted) setError(message(error)); });
    return () => controller.abort();
  }, [offset, attempt]);
  return <section className="mt-6 rounded-2xl border bg-white p-5"><h2 className="text-xl font-semibold">Wybierz sesję do eksploracji</h2>
    {error && <><p role="alert">{error}</p><Button onClick={() => setAttempt(value => value + 1)}>Spróbuj ponownie</Button></>}
    {!data && !error && <p role="status">Wczytywanie sesji…</p>}
    {data && <>{data.items.length === 0 && <p className="mt-4">Brak zapisanych sesji. <Link to="/sessions" className="underline">Utwórz sesję</Link>.</p>}
      <ul className="my-5 space-y-3">{data.items.map(session => <li key={session.id}><Link className="block break-all rounded-lg border p-3 text-teal-800" to={"/data/" + session.id}>{session.start_url} · {session.created_at}</Link></li>)}</ul>
      <div className="flex flex-wrap gap-3"><Button variant="outline" disabled={!offset} onClick={() => setOffset(value => Math.max(0, value - 10))}>Poprzednie sesje</Button><span>Łącznie: {data.total}</span><Button variant="outline" disabled={offset + 10 >= data.total} onClick={() => setOffset(value => value + 10)}>Następne sesje</Button></div></>}
  </section>;
}

export function ExplorerPage() {
  const { id } = useParams();
  return <><p className="eyebrow">ZAPISANE DANE I EKSPORT</p><h1 className="mt-3 text-3xl font-semibold">Eksplorator danych</h1>
    <p className="mt-4 text-muted-foreground">Przeszukuj zapisane strony i pobierz wybrane pola jako CSV. Wyniki pochodzą z wybranej sesji.</p>
    {id ? <ExplorerSession key={id} id={id} /> : <SessionChooser />}</>;
}
