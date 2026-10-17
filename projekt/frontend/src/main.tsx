import React, { useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import {
  Activity,
  ArrowDownToLine,
  ArrowRight,
  Check,
  ChevronDown,
  ChevronRight,
  CircleHelp,
  Database,
  ExternalLink,
  FileText,
  FlaskConical,
  Globe2,
  History,
  Layers3,
  Link2,
  LoaderCircle,
  Network,
  Play,
  Plus,
  Search,
  Settings2,
  ShieldCheck,
  Square,
  X,
} from 'lucide-react';
import { Graph } from './Graph';
import type { Config, Session, Run, Page, GraphData, Study, Datasets } from './types';
import './style.css';

const defaults: Config = {
  url: '',
  strategy: 'dfs',
  scope: 'server',
  links: 'hyperlinks',
  depth: 3,
  page_limit: 200,
  resource_limit: 500,
  delay: 1,
  timeout: 15,
};
const emptyGraph: GraphData = { nodes: [], edges: [] };
const statusNames: Record<string, string> = {
  queued: 'W kolejce',
  running: 'W trakcie',
  completed: 'Zakończono',
  cancelled: 'Zatrzymano',
  interrupted: 'Przerwano',
  failed: 'Niepowodzenie',
  ok: 'Pobrano',
  error: 'Błąd',
  robots: 'robots.txt',
  scope: 'Poza zakresem',
  depth: 'Limit głębokości',
  page_limit: 'Limit stron',
  resource_limit: 'Limit zasobów',
  unsupported: 'Nieobsługiwany adres',
  duplicate: 'Duplikat',
  eligible: 'Odkryto',
  pending: 'Pobieranie',
  redirect: 'Przekierowanie',
};
const linkNames: Record<string, string> = {
  hyperlinks: 'Hiperłącza',
  images: 'Obrazy + hiperłącza',
  all: 'Wszystkie łącza',
};
const purposeNames: Record<string, string> = {
  manual: 'Badanie',
  experiment: 'Eksperyment',
  dataset_A: 'Zbiór A',
  dataset_B: 'Zbiór B',
};
const tabs = [
  { id: 'overview', label: 'Przegląd', icon: Activity },
  { id: 'graph', label: 'Graf WWW', icon: Network },
  { id: 'data', label: 'Dane stron', icon: Database },
  { id: 'experiments', label: 'Eksperymenty', icon: FlaskConical },
  { id: 'report', label: 'Raport', icon: FileText },
];
async function api<T>(path: string, method = 'GET', body?: unknown): Promise<T> {
  const res = await fetch('/api' + path, {
    method,
    headers: body ? { 'Content-Type': 'application/json' } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    let detail;
    try {
      detail = (await res.json()).detail;
    } catch {
      detail = res.statusText;
    }
    throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail));
  }
  return res.json();
}
const fmt = (n: number) => new Intl.NumberFormat('pl-PL', { maximumFractionDigits: 1 }).format(n);
const date = (v: string) => new Date(v).toLocaleString('pl-PL');
function Badge({ status }: { status: string }) {
  return (
    <span className={`badge status-${status}`}>
      {status === 'running' && <LoaderCircle size={12} className="spin" />}
      {statusNames[status] || status}
    </span>
  );
}

function App() {
  const [sessions, setSessions] = useState<Session[]>([]),
    [sessionId, setSessionId] = useState('');
  const [runs, setRuns] = useState<Run[]>([]),
    [runId, setRunId] = useState('');
  const [config, setConfig] = useState<Config>(defaults),
    [tab, setTab] = useState('overview');
  const [graph, setGraph] = useState<GraphData>(emptyGraph),
    [records, setRecords] = useState<Page[]>([]);
  const [study, setStudy] = useState<Study | null>(null),
    [datasets, setDatasets] = useState<Datasets | null>(null);
  const [busy, setBusy] = useState(false),
    [working, setWorking] = useState(false),
    [error, setError] = useState('');
  const [modal, setModal] = useState(false),
    [name, setName] = useState('Badanie struktury WWW'),
    [draftUrl, setDraftUrl] = useState(''),
    [search, setSearch] = useState('');
  const [selected, setSelected] = useState<Page | null>(null),
    [csvFields, setCsvFields] = useState(['URL', 'Keyword']);
  useEffect(() => {
    const close = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setModal(false);
        setSelected(null);
      }
    };
    window.addEventListener('keydown', close);
    return () => window.removeEventListener('keydown', close);
  }, []);
  const session = sessions.find((s) => s.id === sessionId),
    run = runs.find((r) => r.id === runId),
    m = run?.metrics;
  const update = <K extends keyof Config>(key: K, value: Config[K]) =>
    setConfig((c) => ({ ...c, [key]: value }));
  const refresh = async (sid = sessionId) => {
    const [ss, state] = await Promise.all([
      api<Session[]>('/sessions'),
      api<{ busy: boolean }>('/status'),
    ]);
    setSessions(ss);
    setBusy(state.busy);
    if (sid) {
      const [st, ds] = await Promise.all([
        api<Study>(`/sessions/${sid}/comparison`),
        api<Datasets>(`/sessions/${sid}/datasets`),
      ]);
      setStudy(st);
      setRuns(st.runs);
      setDatasets(ds);
      setRunId((prev) => (st.runs.some((r) => r.id === prev) ? prev : st.runs.at(-1)?.id || ''));
    }
  };
  useEffect(() => {
    let live = true;
    api<Session[]>('/sessions')
      .then((ss) => {
        if (live) {
          setSessions(ss);
          if (ss[0]) {
            setSessionId(ss[0].id);
            setConfig({ ...defaults, url: ss[0].url });
          }
        }
      })
      .catch((e) => setError(e.message));
    return () => {
      live = false;
    };
  }, []);
  useEffect(() => {
    let disposed = false;
    const tick = async () => {
      if (!disposed)
        try {
          await refresh(sessionId);
        } catch (e) {
          if (!disposed) setError(String(e));
        }
    };
    void tick();
    const timer = setInterval(() => void tick(), 2000);
    return () => {
      disposed = true;
      clearInterval(timer);
    };
  }, [sessionId]);
  useEffect(() => {
    let disposed = false;
    const load = async () => {
      if (!runId) {
        setGraph(emptyGraph);
        setRecords([]);
        return;
      }
      try {
        const [g, r] = await Promise.all([
          api<GraphData>(`/runs/${runId}/graph`),
          api<Page[]>(`/runs/${runId}/records`),
        ]);
        if (!disposed) {
          setGraph(g);
          setRecords(r.map((p) => ({ ...p, ...g.nodes.find((n) => n.url === p.url) })));
        }
      } catch (e) {
        if (!disposed) setError(String(e));
      }
    };
    void load();
    const timer = setInterval(() => {
      if (busy) void load();
    }, 1800);
    return () => {
      disposed = true;
      clearInterval(timer);
    };
  }, [runId, busy]);
  function chooseSession(s: Session) {
    setSessionId(s.id);
    setConfig({ ...defaults, url: s.url });
    setRuns([]);
    setRunId('');
    setStudy(null);
    setDatasets(null);
    setSelected(null);
  }
  async function createSession(e: React.FormEvent) {
    e.preventDefault();
    setWorking(true);
    setError('');
    try {
      const s = await api<Session>('/sessions', 'POST', {
        name,
        config: { ...defaults, url: draftUrl },
      });
      setSessions((old) => [s, ...old]);
      chooseSession(s);
      setModal(false);
      setDraftUrl('');
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setWorking(false);
    }
  }
  async function launch(kind: 'runs' | 'experiments' | 'datasets') {
    setWorking(true);
    setError('');
    try {
      let sid = sessionId;
      if (!sid) {
        const s = await api<Session>('/sessions', 'POST', { name, config });
        sid = s.id;
        setSessionId(sid);
        setSessions((old) => [s, ...old]);
      }
      const result = await api<{ run_ids: string[] }>(`/sessions/${sid}/${kind}`, 'POST', config);
      setRunId(result.run_ids[0]);
      setBusy(true);
      setSelected(null);
      await refresh(sid);
      if (kind === 'experiments') setTab('experiments');
      if (kind === 'datasets') setTab('data');
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setWorking(false);
    }
  }
  const cancel = async () => {
    try {
      await api('/cancel', 'POST');
    } catch (e) {
      setError(String(e));
    }
  };
  const download = (suffix: string) => `/api/runs/${runId}/${suffix}`;
  const visible = records.filter((p) =>
    [p.url, p.title, p.keywords, p.body, p.error].some((v) =>
      v?.toLowerCase().includes(search.toLowerCase()),
    ),
  );
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <a
          href="#"
          className="brand"
          onClick={(e) => {
            e.preventDefault();
            setTab('overview');
          }}
        >
          <span className="brand-mark">
            <Network size={22} />
          </span>
          <div>
            EZI<span>LABORATORIUM WWW</span>
          </div>
        </a>
        <div className="workspace-label">PRZESTRZEŃ BADAWCZA</div>
        <nav>
          {tabs.map((t) => (
            <button
              key={t.id}
              className={tab === t.id ? 'nav-item active' : 'nav-item'}
              onClick={() => setTab(t.id)}
            >
              <t.icon size={18} />
              {t.label}
              {t.id === 'graph' && m && <small>{m.pages}</small>}
            </button>
          ))}
        </nav>
        <div className="side-section">
          <span>SESJE BADAWCZE</span>
          <button
            title="Nowa sesja"
            aria-label="Nowa sesja"
            onClick={() => {
              setModal(true);
            }}
          >
            <Plus size={16} />
          </button>
        </div>
        <div className="session-list">
          {sessions.length ? (
            sessions.map((s) => (
              <button
                key={s.id}
                className={`session-item ${s.id === sessionId ? 'current' : ''}`}
                onClick={() => chooseSession(s)}
              >
                <Globe2 size={15} />
                <span>
                  {s.name}
                  <small>{new URL(s.url).hostname}</small>
                </span>
                {s.id === sessionId && <span className="current-dot" />}
              </button>
            ))
          ) : (
            <p className="side-empty">Twoje badania pojawią się tutaj.</p>
          )}
        </div>
        <div className="side-bottom">
          <div className="local-state">
            <i /> Tryb lokalny <span>SQLite</span>
          </div>
          <div className="course">
            <Layers3 size={17} />
            <div>
              Eksploracja zasobów Internetu<small>Ćwiczenia 1–2 · struktura WWW</small>
            </div>
          </div>
        </div>
      </aside>
      <main>
        <header className="topbar">
          <div>
            Laboratorium{' '}
            {sessions.length > 0 && (
              <select
                className="global-session-select"
                aria-label="Wybierz sesję"
                value={sessionId}
                onChange={(e) => {
                  const s = sessions.find((s) => s.id === e.target.value);
                  if (s) chooseSession(s);
                }}
              >
                {sessions.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.name}
                  </option>
                ))}
              </select>
            )}
            <ChevronRight size={14} />
            <strong>{tabs.find((t) => t.id === tab)?.label}</strong>
          </div>
          <span className="top-status">
            <i className={busy ? 'pulsing' : ''} />
            {busy ? 'Badanie w toku' : 'Gotowe do badania'}
          </span>
        </header>
        <div className="page-content">
          <div className="page-heading">
            <div>
              <div className="eyebrow">EKSPLORACJA ZASOBÓW INTERNETU</div>
              <h1>
                {tab === 'overview'
                  ? 'Zrozum strukturę sieci.'
                  : tab === 'graph'
                    ? 'Mapa połączeń WWW.'
                    : tab === 'data'
                      ? 'Od stron do wiedzy.'
                      : tab === 'experiments'
                        ? 'Porównaj. Zmierz. Zrozum.'
                        : 'Wnioski z Twoich badań.'}
              </h1>
              <p>
                {tab === 'overview'
                  ? 'Odkrywaj połączenia, analizuj zawartość i porównuj strategie przeszukiwania.'
                  : tab === 'graph'
                    ? 'Zobacz, jak strony łączą się w sieć. Wybierz węzeł, aby poznać szczegóły.'
                    : tab === 'data'
                      ? 'Przeglądaj treść stron, eksportuj dane i porównuj struktury ich przechowywania.'
                      : tab === 'experiments'
                        ? 'Dwanaście konfiguracji. Jeden adres. Wyniki oparte na pomiarach.'
                        : 'Raport obejmuje wszystkie osiem punktów ćwiczenia i zapisane wyniki.'}
              </p>
            </div>
            <button
              className="button secondary"
              onClick={() => {
                setModal(true);
              }}
            >
              <Plus size={16} /> Nowa sesja
            </button>
          </div>
          {error && (
            <div className="error-banner" role="alert">
              {error}
              <button aria-label="Zamknij błąd" onClick={() => setError('')}>
                <X size={16} />
              </button>
            </div>
          )}
          <section className="study-bar">
            <div className="study-icon">
              <Globe2 size={21} />
            </div>
            <div className="study-current">
              <span>{session ? 'AKTYWNA SESJA' : 'NOWE BADANIE'}</span>
              <strong>{session?.name || 'Rozpocznij od adresu strony'}</strong>
              <small>{session?.url || 'Wprowadź URL w konfiguracji poniżej'}</small>
            </div>
            {run && <Badge status={run.status} />}
            <div className="study-actions">
              {busy && (
                <button
                  className="stop-button"
                  aria-label="Zatrzymaj aktywne badanie"
                  onClick={() => void cancel()}
                >
                  <Square size={12} />
                  <span>Zatrzymaj</span>
                </button>
              )}
              {runs.length > 0 && (
                <label className="run-select">
                  <History size={15} />
                  <select
                    aria-label="Wybierz przebieg"
                    value={runId}
                    onChange={(e) => {
                      setRunId(e.target.value);
                      setSelected(null);
                    }}
                  >
                    {[...runs].reverse().map((r, i) => (
                      <option key={r.id} value={r.id}>
                        {purposeNames[r.purpose]} · {r.config.strategy.toUpperCase()} /{' '}
                        {r.config.scope} / {linkNames[r.config.links]} · {statusNames[r.status]} ·{' '}
                        {i + 1}
                      </option>
                    ))}
                  </select>
                  <ChevronDown size={13} />
                </label>
              )}
              {session && (
                <a
                  className="icon-button"
                  title="Otwórz raport"
                  href={`/api/sessions/${sessionId}/report`}
                  target="_blank"
                  rel="noreferrer"
                >
                  <FileText size={18} />
                </a>
              )}
            </div>
          </section>
          {(tab === 'overview' || tab === 'graph') && (
            <div className="stats-grid">
              {[
                {
                  label: 'Strony HTML',
                  value: m?.pages ?? 0,
                  icon: Globe2,
                  sub: `${m?.subpages ?? 0} podstron · cel: min. 20`,
                },
                {
                  label: 'Odkryte łącza',
                  value: m?.links ?? 0,
                  icon: Link2,
                  sub: `${m?.unique_edges ?? 0} unikalnych połączeń`,
                },
                {
                  label: 'Głębokość grafu',
                  value: m?.depth ?? 0,
                  icon: Layers3,
                  sub: 'Najkrótszy dystans hiperłączy',
                },
                {
                  label: 'Czas badania',
                  value: `${fmt(m?.elapsed ?? 0)} s`,
                  icon: Activity,
                  sub: `${m?.requests ?? 0} żądań HTTP`,
                },
              ].map((item) => (
                <div className="stat-card" key={item.label}>
                  <div>
                    <span>{item.label}</span>
                    <item.icon size={17} />
                  </div>
                  <strong>{typeof item.value === 'number' ? fmt(item.value) : item.value}</strong>
                  <small>{item.sub}</small>
                </div>
              ))}
            </div>
          )}
          {tab === 'overview' && (
            <>
              <div className="overview-grid">
                <section className="card config-card">
                  <div className="card-header">
                    <h2>
                      <Settings2 size={17} /> Konfiguracja badania
                    </h2>
                    <span className="muted-label">CRAWLER</span>
                  </div>
                  <form
                    onSubmit={(e) => {
                      e.preventDefault();
                      void launch('runs');
                    }}
                  >
                    <label className="field">
                      Adres początkowy
                      <div className="input-icon">
                        <Globe2 size={16} />
                        <input
                          type="url"
                          required
                          placeholder="https://twoja-strona.pl"
                          value={config.url}
                          disabled={!!session || busy}
                          onChange={(e) => update('url', e.target.value)}
                        />
                      </div>
                    </label>
                    <div className="field-row">
                      <label className="field">
                        Strategia
                        <select
                          value={config.strategy}
                          disabled={busy}
                          onChange={(e) => update('strategy', e.target.value as Config['strategy'])}
                        >
                          <option value="dfs">Depth first (DFS)</option>
                          <option value="bfs">Breadth first (BFS)</option>
                        </select>
                      </label>
                      <label className="field">
                        Zakres
                        <select
                          value={config.scope}
                          disabled={busy}
                          onChange={(e) => update('scope', e.target.value as Config['scope'])}
                        >
                          <option value="server">Server — ten sam serwer</option>
                          <option value="web">Web — także zewnętrzne</option>
                        </select>
                      </label>
                    </div>
                    <label className="field">
                      Uwzględniane łącza
                      <select
                        value={config.links}
                        disabled={busy}
                        onChange={(e) => update('links', e.target.value as Config['links'])}
                      >
                        {Object.entries(linkNames).map(([v, l]) => (
                          <option key={v} value={v}>
                            {l}
                          </option>
                        ))}
                      </select>
                    </label>
                    <div className="field-row">
                      <label className="field">
                        Głębokość
                        <input
                          type="number"
                          min="0"
                          max="15"
                          value={config.depth}
                          disabled={busy}
                          onChange={(e) => update('depth', Number(e.target.value))}
                        />
                      </label>
                      <label className="field">
                        Limit stron
                        <input
                          type="number"
                          min="1"
                          max="5000"
                          value={config.page_limit}
                          disabled={busy}
                          onChange={(e) => update('page_limit', Number(e.target.value))}
                        />
                      </label>
                    </div>
                    <details className="advanced">
                      <summary>
                        Ustawienia zaawansowane <ChevronDown size={14} />
                      </summary>
                      <div className="field-row">
                        <label className="field">
                          Limit zasobów
                          <input
                            type="number"
                            min="0"
                            max="10000"
                            value={config.resource_limit}
                            disabled={busy}
                            onChange={(e) => update('resource_limit', Number(e.target.value))}
                          />
                        </label>
                        <label className="field">
                          Opóźnienie [s]
                          <input
                            type="number"
                            min="0"
                            max="30"
                            step="0.1"
                            value={config.delay}
                            disabled={busy}
                            onChange={(e) => update('delay', Number(e.target.value))}
                          />
                        </label>
                        <label className="field">
                          Timeout [s]
                          <input
                            type="number"
                            min="0.1"
                            max="120"
                            step="0.1"
                            value={config.timeout}
                            disabled={busy}
                            onChange={(e) => update('timeout', Number(e.target.value))}
                          />
                        </label>
                      </div>
                    </details>
                    <div className="respect-note">
                      <ShieldCheck size={14} /> Respektujemy robots.txt · analizujemy statyczny HTML
                    </div>
                    {busy ? (
                      <button
                        type="button"
                        className="button danger full"
                        onClick={() => void cancel()}
                      >
                        <Square size={14} /> Zatrzymaj badanie i kolejkę
                      </button>
                    ) : (
                      <button
                        className="button primary full"
                        type="submit"
                        disabled={working || !config.url}
                      >
                        <Play size={15} />
                        {working ? 'Uruchamianie…' : 'Rozpocznij badanie'}
                        <ArrowRight size={15} />
                      </button>
                    )}
                  </form>
                </section>
                <section className="card graph-preview">
                  <div className="card-header">
                    <h2>
                      <Network size={17} /> Mapa połączeń
                    </h2>
                    <button className="text-button" onClick={() => setTab('graph')}>
                      Pełny widok <ArrowRight size={14} />
                    </button>
                  </div>
                  <Graph data={graph} onSelect={setSelected} />
                </section>
              </div>
              <div className="lower-grid">
                <section className="card">
                  <div className="card-header">
                    <h2>
                      <Check size={17} /> Wymagania ćwiczenia
                    </h2>
                    <span className={`badge ${m?.qualifies ? 'status-completed' : ''}`}>
                      {m?.qualifies ? 'Spełnione' : 'Do zweryfikowania'}
                    </span>
                  </div>
                  <div className="requirements">
                    <div>
                      <span className={`require-dot ${(m?.subpages ?? 0) >= 20 ? 'done' : ''}`}>
                        <Check size={12} />
                      </span>
                      <p>
                        Co najmniej 20 podstron HTML
                        <small>Strona startowa i zasoby nie są wliczane.</small>
                      </p>
                      <strong>
                        {m?.subpages ?? 0}
                        <span> / 20</span>
                      </strong>
                    </div>
                    <div>
                      <span className={`require-dot ${(m?.depth ?? 0) >= 3 ? 'done' : ''}`}>
                        <Check size={12} />
                      </span>
                      <p>
                        Co najmniej 3 poziomy głębokości
                        <small>Korzeń = 0; najkrótsza ścieżka hiperłączy.</small>
                      </p>
                      <strong>
                        {m?.depth ?? 0}
                        <span> / 3</span>
                      </strong>
                    </div>
                  </div>
                  {run?.message && <p className="note">{run.message}</p>}
                </section>
                <section className="next-card">
                  <span className="step-label">KOLEJNY KROK</span>
                  <h2>Jedna strona, różne perspektywy.</h2>
                  <p>Sprawdź wpływ strategii, zakresu i typów łączy na wynik przeszukiwania.</p>
                  <button className="text-button" onClick={() => setTab('experiments')}>
                    Przejdź do eksperymentów <ArrowRight size={15} />
                  </button>
                  <FlaskConical className="decor-icon" size={100} />
                </section>
              </div>
            </>
          )}
          {tab === 'graph' && (
            <section className="card">
              <div className="card-header">
                <h2>
                  <Network size={17} /> Graf odkrytych adresów
                </h2>
                <span className="muted-label">
                  {m?.traversal_depth ?? 0} · maks. głębokość przejścia
                </span>
              </div>
              <Graph data={graph} onSelect={setSelected} />
              <div className="distribution">
                <strong>Rozkład głębokości HTML</strong>
                {Object.entries(m?.distribution || {}).map(([d, n]) => (
                  <span key={d}>
                    Poziom {d}: <b>{n}</b>
                  </span>
                ))}
                {!m?.pages && <span>Brak pobranych stron.</span>}
              </div>
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr>
                      <th>Adres</th>
                      <th>Status</th>
                      <th>Łącza / cele</th>
                      <th>Przejście / dystans</th>
                    </tr>
                  </thead>
                  <tbody>
                    {graph.nodes.map((n) => (
                      <tr key={n.url} onClick={() => setSelected(n)} className="clickable">
                        <td className="url-cell">{n.url}</td>
                        <td>
                          <Badge status={n.status} />
                        </td>
                        <td>
                          {n.outgoing} / {n.unique_targets}
                        </td>
                        <td>
                          {n.depth ?? '—'} / {n.distance ?? '—'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          )}
          {tab === 'data' && (
            <>
              <section className="callout">
                <div className="callout-icon">
                  <Database size={22} />
                </div>
                <div>
                  <h2>Dwa zbiory. Dwie struktury danych.</h2>
                  <p>
                    A: CSV URL/Keyword · web, głębokość 2. B: relacyjna baza SQLite · server,
                    głębokość 3.
                  </p>
                </div>
                <button
                  className="button primary"
                  disabled={!session || busy || working}
                  onClick={() => void launch('datasets')}
                >
                  <Play size={14} /> Przygotuj zbiory A/B
                </button>
              </section>
              <div className="dataset-grid">
                {(['A', 'B'] as const).map((role) => {
                  const d = datasets?.[role];
                  return (
                    <section className="card dataset-card" key={role}>
                      <div className="card-header">
                        <h2>
                          <span className="dataset-letter">{role}</span>
                          {role === 'A' ? 'Płaski indeks CSV' : 'Relacyjna baza SQLite'}
                        </h2>
                        {d && <Badge status={d.status} />}
                      </div>
                      <div className="dataset-body">
                        <div className="dataset-numbers">
                          <div>
                            <strong>{d?.records ?? '—'}</strong>
                            <small>rekordów HTML</small>
                          </div>
                          <div>
                            <strong>
                              {d ? fmt(d.size / 1024) : '—'} <em>KB</em>
                            </strong>
                            <small>rozmiar eksportu</small>
                          </div>
                        </div>
                        <p>
                          {role === 'A'
                            ? 'URL, Keyword — prosty indeks adresów i meta keywords.'
                            : 'Tabele pages, metadata, links, run — zawartość i relacje.'}
                        </p>
                        {d && (
                          <>
                            <div className="completeness">
                              {Object.entries(d.completeness).map(([k, v]) => (
                                <div key={k}>
                                  <span>{k}</span>
                                  <meter min="0" max="1" value={v} />
                                  <small>{Math.round(v * 100)}%</small>
                                </div>
                              ))}
                            </div>
                            <a
                              className="button secondary full"
                              href={`/api/runs/${d.run_id}/export.${role === 'A' ? 'csv' : 'sqlite'}`}
                            >
                              <ArrowDownToLine size={15} /> Pobierz zbiór {role}
                            </a>
                            <details>
                              <summary>Konfiguracja zbioru</summary>
                              <pre>{JSON.stringify(d.config, null, 2)}</pre>
                            </details>
                          </>
                        )}
                      </div>
                    </section>
                  );
                })}
              </div>
              {datasets?.comparison && (
                <section className="card comparison-note">
                  <h2>Różnice i zastosowania</h2>
                  <div className="comparison-counts">
                    <span>
                      Wspólne URL <b>{datasets.comparison.common}</b>
                    </span>
                    <span>
                      Tylko A <b>{datasets.comparison.only_a}</b>
                    </span>
                    <span>
                      Tylko B <b>{datasets.comparison.only_b}</b>
                    </span>
                  </div>
                  <p>{datasets.comparison.usefulness_a}</p>
                  <p>{datasets.comparison.usefulness_b}</p>
                  <p className="note">{datasets.comparison.caveat}</p>
                </section>
              )}
              <section className="card">
                <div className="card-header">
                  <h2>
                    <Database size={17} /> Dane wybranego przebiegu{' '}
                    <span className="count">{records.length}</span>
                  </h2>
                  {runId && (
                    <a className="button secondary small" href={download('export.sqlite')}>
                      <ArrowDownToLine size={14} /> SQLite
                    </a>
                  )}
                </div>
                <div className="data-toolbar">
                  <div className="search-input">
                    <Search size={16} />
                    <input
                      placeholder="Szukaj URL, tytułu, treści…"
                      aria-label="Szukaj danych"
                      value={search}
                      onChange={(e) => setSearch(e.target.value)}
                    />
                  </div>
                  <details className="csv-options">
                    <summary>
                      Pola CSV <ChevronDown size={14} />
                    </summary>
                    <div>
                      {[
                        'URL',
                        'Keyword',
                        'Title',
                        'Description',
                        'Body',
                        'Depth',
                        'Status',
                        'ContentType',
                      ].map((f) => (
                        <label key={f}>
                          <input
                            type="checkbox"
                            checked={csvFields.includes(f)}
                            onChange={(e) =>
                              setCsvFields((old) =>
                                e.target.checked ? [...old, f] : old.filter((v) => v !== f),
                              )
                            }
                          />
                          {f}
                        </label>
                      ))}
                    </div>
                  </details>
                  <a
                    className={`button secondary small ${!runId || !csvFields.length ? 'disabled' : ''}`}
                    href={
                      runId && csvFields.length
                        ? download(`export.csv?fields=${csvFields.join(',')}`)
                        : undefined
                    }
                  >
                    <ArrowDownToLine size={14} /> Eksport CSV
                  </a>
                </div>
                <div className="table-scroll">
                  <table>
                    <thead>
                      <tr>
                        <th>URL / tytuł</th>
                        <th>Słowa kluczowe</th>
                        <th>Status</th>
                        <th>Rozmiar</th>
                        <th />
                      </tr>
                    </thead>
                    <tbody>
                      {visible.map((p) => (
                        <tr key={p.url} className="clickable" onClick={() => setSelected(p)}>
                          <td className="url-cell">
                            <strong>{p.title || 'Bez tytułu'}</strong>
                            <small>{p.url}</small>
                          </td>
                          <td>{p.keywords || '—'}</td>
                          <td>
                            <Badge status={p.status} />
                          </td>
                          <td>{fmt((p.bytes ?? 0) / 1024)} KB</td>
                          <td>
                            <ChevronRight size={15} />
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  {!visible.length && (
                    <div className="empty-state">
                      <Database size={30} />
                      <h3>Jeszcze bez danych</h3>
                      <p>Uruchom badanie lub przygotuj zbiory A/B.</p>
                    </div>
                  )}
                </div>
              </section>
            </>
          )}
          {tab === 'experiments' && (
            <>
              <section className="callout">
                <div className="callout-icon">
                  <FlaskConical size={23} />
                </div>
                <div>
                  <h2>Pełna macierz eksperymentów</h2>
                  <p>
                    2 strategie × 2 zakresy × 3 typy łączy. Wspólny URL i limity z konfiguracji
                    badania.
                  </p>
                </div>
                <button
                  className="button primary"
                  disabled={!session || busy || working}
                  onClick={() => void launch('experiments')}
                >
                  <Play size={14} /> Uruchom 12 wariantów
                </button>
              </section>
              {busy && (
                <div className="running-note">
                  <LoaderCircle size={16} className="spin" /> Przebiegi wykonywane kolejno. Wyniki
                  zapisują się na bieżąco.
                  <button className="text-button" onClick={() => void cancel()}>
                    Zatrzymaj kolejkę
                  </button>
                </div>
              )}
              <section className="card">
                <div className="card-header">
                  <h2>
                    <FlaskConical size={17} /> Wyniki eksperymentów
                  </h2>
                  <span className="muted-label">
                    {
                      runs.filter((r) => r.purpose === 'experiment' && r.status === 'completed')
                        .length
                    }{' '}
                    zakończonych
                  </span>
                </div>
                <div className="table-scroll">
                  <table>
                    <thead>
                      <tr>
                        <th>Strategia / zakres</th>
                        <th>Łącza</th>
                        <th>Status</th>
                        <th>Strony</th>
                        <th>Głęb.</th>
                        <th>Łącza</th>
                        <th>Zasoby</th>
                        <th>Błędy</th>
                        <th>Żądania</th>
                        <th>Czas</th>
                        <th>Limit</th>
                      </tr>
                    </thead>
                    <tbody>
                      {runs
                        .filter((r) => r.purpose === 'experiment')
                        .map((r) => (
                          <tr
                            key={r.id}
                            className={`clickable ${r.id === runId ? 'selected-row' : ''}`}
                            onClick={() => setRunId(r.id)}
                          >
                            <td>
                              <strong>{r.config.strategy.toUpperCase()}</strong>
                              <small>{r.config.scope}</small>
                            </td>
                            <td>{linkNames[r.config.links]}</td>
                            <td>
                              <Badge status={r.status} />
                            </td>
                            {['pages', 'depth', 'links', 'resources', 'failures', 'requests'].map(
                              (k) => (
                                <td key={k}>{r.metrics[k as keyof typeof r.metrics] as number}</td>
                              ),
                            )}
                            <td>{fmt(r.metrics.elapsed)} s</td>
                            <td>{r.metrics.truncated ? 'Tak' : 'Nie'}</td>
                          </tr>
                        ))}
                    </tbody>
                  </table>
                  {!runs.some((r) => r.purpose === 'experiment') && (
                    <div className="empty-state">
                      <FlaskConical size={32} />
                      <h3>Nie ma jeszcze eksperymentów</h3>
                      <p>Utwórz sesję, następnie uruchom serię 12 konfiguracji.</p>
                    </div>
                  )}
                </div>
              </section>
              <section className="recommendation">
                <ShieldCheck size={23} />
                <div>
                  <h2>Rekomendacja na podstawie wyników</h2>
                  <p>{study?.recommendation || 'Brak zakończonych eksperymentów.'}</p>
                </div>
              </section>
              <div className="findings-grid">
                {study?.findings.map((f) => (
                  <section className="card finding" key={f.parameter}>
                    <h2>{f.label}</h2>
                    <p>{f.note}</p>
                    <details>
                      <summary>Pokaż porównania ({f.comparisons.length})</summary>
                      <ul>
                        {f.comparisons.map((s, i) => (
                          <li key={i}>{s}</li>
                        ))}
                      </ul>
                    </details>
                  </section>
                ))}
              </div>
            </>
          )}
          {tab === 'report' && (
            <>
              <section className="report-hero">
                <div className="report-illustration">
                  <FileText size={62} strokeWidth={1} />
                  <span>
                    <Check size={20} />
                  </span>
                </div>
                <div>
                  <span className="eyebrow">OD DANYCH DO WNIOSKÓW</span>
                  <h2>Twoje badanie, w jednym raporcie.</h2>
                  <p>
                    Graf, pomiary, wpływ parametrów i porównanie struktur danych.
                    <br />
                    Gotowy do zapisania i wydruku; brakujące wyniki oznaczone wprost.
                  </p>
                  <div className="button-row">
                    <a
                      className={`button primary ${!session ? 'disabled' : ''}`}
                      href={session ? `/api/sessions/${sessionId}/report` : undefined}
                      target="_blank"
                      rel="noreferrer"
                    >
                      <ExternalLink size={16} /> Otwórz i drukuj raport
                    </a>
                    <a
                      className={`button secondary ${!session ? 'disabled' : ''}`}
                      href={session ? `/api/sessions/${sessionId}/report?download=true` : undefined}
                    >
                      <ArrowDownToLine size={16} /> Pobierz HTML
                    </a>
                  </div>
                </div>
              </section>
              <section className="card report-checklist">
                <div className="card-header">
                  <h2>
                    <FileText size={17} /> Zawartość raportu
                  </h2>
                  <span className="muted-label">ĆWICZENIA 1–8</span>
                </div>
                {[
                  'Graf i charakterystyka strony',
                  'Zmiany parametrów przeszukiwania',
                  'Wpływ poszczególnych parametrów',
                  'Najlepszy wariant praktyczny',
                  'Pozyskanie danych i CSV URL/Keyword',
                  'Przydatność struktury CSV',
                  'Alternatywna struktura SQLite',
                  'Różnice baz i zastosowania',
                ].map((s, i) => {
                  const done =
                    i < 1
                      ? runs.some((r) => r.status === 'completed' && r.purpose === 'manual')
                      : i < 4
                        ? runs.some((r) => r.purpose === 'experiment' && r.status === 'completed')
                        : i < 6
                          ? datasets?.A?.status === 'completed'
                          : i === 6
                            ? datasets?.B?.status === 'completed'
                            : datasets?.A?.status === 'completed' &&
                              datasets?.B?.status === 'completed';
                  return (
                    <div className="checklist-row" key={s}>
                      <span>{String(i + 1).padStart(2, '0')}</span>
                      <strong>{s}</strong>
                      <span className={`badge ${done ? 'status-completed' : ''}`}>
                        {done ? 'Dane dostępne' : 'Brak kompletu danych'}
                      </span>
                    </div>
                  );
                })}
              </section>
              <p className="footnote">
                <CircleHelp size={14} /> Raport opisuje zmierzone dane. Spełnienie warunków zadania
                zależy od struktury wybranej witryny.
              </p>
            </>
          )}
          <footer>
            <span>EZI / Laboratorium WWW</span>
            <span>Statyczny HTML · Dane lokalne · Bez usług chmurowych</span>
          </footer>
        </div>
      </main>
      {modal && (
        <div className="modal-backdrop" onClick={() => setModal(false)}>
          <section
            className="modal card"
            role="dialog"
            aria-modal="true"
            aria-labelledby="modal-title"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="card-header">
              <h2 id="modal-title">Nowa sesja badawcza</h2>
              <button className="icon-button" aria-label="Zamknij" onClick={() => setModal(false)}>
                <X size={19} />
              </button>
            </div>
            <form onSubmit={(e) => void createSession(e)}>
              <label className="field">
                Nazwa sesji
                <input
                  required
                  maxLength={150}
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  autoFocus
                />
              </label>
              <label className="field">
                Adres początkowy
                <input
                  type="url"
                  required
                  placeholder="https://twoja-strona.pl"
                  value={draftUrl}
                  onChange={(e) => setDraftUrl(e.target.value)}
                />
              </label>
              <p className="note">
                Sesja zachowuje adres startowy oraz historię wszystkich przebiegów.
              </p>
              {error && (
                <p role="alert" className="modal-error">
                  {error}
                </p>
              )}
              <button className="button primary full" disabled={working}>
                Utwórz sesję <ArrowRight size={15} />
              </button>
            </form>
          </section>
        </div>
      )}
      {selected && (
        <div className="detail-backdrop" onClick={() => setSelected(null)}>
          <aside
            className="detail-panel"
            role="dialog"
            aria-modal="true"
            aria-labelledby="detail-title"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="card-header">
              <h2 id="detail-title">Szczegóły adresu</h2>
              <button
                className="icon-button"
                aria-label="Zamknij szczegóły"
                onClick={() => setSelected(null)}
              >
                <X size={19} />
              </button>
            </div>
            <div className="detail-content">
              <Badge status={selected.status} />
              <h2>{selected.title || 'Odkryty adres'}</h2>
              <p className="detail-url">{selected.url}</p>
              {selected.final_url && selected.final_url !== selected.url && (
                <p>Po przekierowaniu: {selected.final_url}</p>
              )}
              <dl>
                {[
                  ['Typ', selected.kind],
                  ['Głębokość przejścia', selected.depth ?? '—'],
                  ['Dystans hiperłączy', selected.distance ?? '—'],
                  ['Łącza wychodzące', selected.outgoing ?? '—'],
                  ['Unikalne cele', selected.unique_targets ?? '—'],
                  ['HTTP', selected.http_status ?? '—'],
                ].map(([k, v]) => (
                  <div key={k}>
                    <dt>{k}</dt>
                    <dd>{v}</dd>
                  </div>
                ))}
              </dl>
              {selected.error && <p className="modal-error">{selected.error}</p>}
              <h3>Meta description</h3>
              <p>{selected.description || 'Brak'}</p>
              <h3>Meta keywords</h3>
              <p>{selected.keywords || 'Brak'}</p>
              <h3>Treść strony</h3>
              <p className="body-preview">{selected.body || 'Brak treści HTML'}</p>
            </div>
          </aside>
        </div>
      )}
    </div>
  );
}
createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
