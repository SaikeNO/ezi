import { NavLink, Route, Routes } from "react-router-dom"
import { lazy, Suspense } from "react"
import { ArrowUpRight, Database, GitCompareArrows, LayoutDashboard, Network, Table } from "lucide-react"
import { SessionDetail, SessionsPage } from "@/pages/sessions"
import { HealthPanel } from "@/components/health-panel"
const GraphPage = lazy(() => import("@/pages/graph").then(module => ({ default: module.GraphPage })))
const graphView = <Suspense fallback={<p role="status">Wczytywanie widoku grafu…</p>}><GraphPage /></Suspense>
const ExplorerPage = lazy(() => import("@/pages/explorer").then(module => ({ default: module.ExplorerPage })))
const explorerView = <Suspense fallback={<p role="status">Wczytywanie eksploratora…</p>}><ExplorerPage /></Suspense>

const sections = [
  { path: "/", title: "Przegląd", icon: LayoutDashboard },
  { path: "/sessions", title: "Sesje", icon: Database },
  { path: "/graph", title: "Graf witryny", icon: Network },
  { path: "/data", title: "Dane i CSV", icon: Table },
  { path: "/experiments", title: "Porównania", icon: GitCompareArrows },
]

function Overview() {
  return <>
    <p className="eyebrow">ŚRODOWISKO GOTOWE DO PRACY</p>
    <h1 className="mt-3 text-3xl font-semibold tracking-tight sm:text-4xl">Przegląd projektu</h1>
    <p className="mt-4 max-w-2xl leading-relaxed text-muted-foreground">Twoje miejsce do badania struktury stron WWW. Sprawdź połączenie z serwerem przed rozpoczęciem pracy.</p>
    <div className="mt-9 grid gap-6 lg:grid-cols-2">
      <HealthPanel />
      <section className="rounded-2xl bg-slate-900 p-6 text-white sm:p-8">
        <p className="text-xs font-semibold tracking-widest text-teal-300">ETAP 06 / DANE I CSV</p>
        <h2 className="mt-4 text-xl font-semibold">Od adresu do wiedzy o witrynie</h2>
        <p className="mt-4 leading-relaxed text-slate-300">Zapisuj sesje i uruchamiaj pobieranie stron z kontrolą limitów, robots.txt i bezpieczeństwa adresów. Odkrywaj graf witryny, metadane stron i statystyki zapisanych relacji.</p>
        <div className="mt-8 flex items-center gap-2 text-sm text-teal-200"><ArrowUpRight aria-hidden="true" size={18} /> Analizy będą oparte na rzeczywistych danych.</div>
      </section>
    </div>
  </>
}

function Planned({ title, description }: { title: string; description: string }) {
  return <section className="rounded-2xl border bg-card p-8"><p className="eyebrow">W PRZYGOTOWANIU</p><h1 className="mt-3 text-3xl font-semibold">{title}</h1><p className="mt-4 max-w-xl leading-relaxed text-muted-foreground">{description}</p></section>
}

export default function App() {
  return <div className="min-h-screen lg:grid lg:grid-cols-[260px_1fr]">
    <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:z-10 focus:bg-white focus:p-4">Przejdź do treści</a>
    <aside className="border-b bg-white p-6 lg:min-h-screen lg:border-r lg:border-b-0">
      <div className="flex items-center gap-3"><div className="rounded-xl bg-teal-700 p-2 text-white"><Network aria-hidden="true" /></div><span className="font-semibold leading-tight">WebCrawler<br /><span className="text-sm font-normal text-muted-foreground">Studio</span></span></div>
      <nav aria-label="Nawigacja główna" className="mt-8 flex flex-wrap gap-2 lg:flex-col">
        {sections.map(({ path, title, icon: Icon }) => <NavLink key={path} to={path} end={path === "/"} className={({ isActive }) => `flex items-center gap-3 rounded-lg px-4 py-3 text-sm font-medium transition-colors ${isActive ? "bg-teal-50 text-teal-800" : "text-slate-600 hover:bg-slate-100"}`}><Icon aria-hidden="true" size={18} />{title}</NavLink>)}
      </nav>
      <p className="mt-10 text-xs leading-relaxed text-muted-foreground">Laboratorium eksploracji<br />zasobów internetowych</p>
    </aside>
    <div className="min-w-0"><header className="flex items-center justify-between border-b px-6 py-5 sm:px-10"><span className="text-sm text-muted-foreground">Przestrzeń robocza</span><span className="rounded-full border bg-white px-3 py-1 text-xs">Etap 06</span></header>
      <main id="main" className="mx-auto max-w-6xl px-6 py-10 sm:px-10 sm:py-14">
        <Routes>
          <Route path="/" element={<Overview />} />
          <Route path="/sessions" element={<SessionsPage />} />
          <Route path="/sessions/:id" element={<SessionDetail />} />
          <Route path="/graph" element={graphView} />
          <Route path="/graph/:id" element={graphView} />
          <Route path="/data" element={explorerView} />
          <Route path="/data/:id" element={explorerView} />
          <Route path="/experiments" element={<Planned title="Porównania" description="Porównywanie rzeczywistych wyników sesji będzie dostępne w etapie 07." />} />
          <Route path="*" element={<Planned title="Nie znaleziono strony" description="Wybierz sekcję z menu nawigacji." />} />
        </Routes>
      </main>
    </div>
  </div>
}
