import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { request } from "@/lib/sessions-api";

export function ReportDownload({ sessionId, sessionIds }: { sessionId?: string; sessionIds?: string[] }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const active = useRef<AbortController | null>(null);
  useEffect(() => () => active.current?.abort(), []);
  async function download() {
    const controller = new AbortController(); active.current = controller;
    setBusy(true); setError("");
    try {
      const blob = await request<Blob>(sessionId ? `/api/sessions/${encodeURIComponent(sessionId)}/report` : "/api/reports/compare", {
        signal: controller.signal, ...(sessionId ? {} : { method: "POST", body: JSON.stringify({ session_ids: sessionIds }) }),
      }, true, 35000);
      if (!blob.type.startsWith("text/html")) throw new Error("Nieprawidłowy format raportu.");
      if (controller.signal.aborted) return;
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a"); link.href = url;
      link.download = sessionId ? `report-${sessionId}.html` : "comparison-report.html";
      link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (err) {
      if (!controller.signal.aborted) setError(err instanceof Error ? err.message : "Nie udało się pobrać raportu.");
    } finally { if (!controller.signal.aborted) setBusy(false); }
  }
  return <div className="my-4"><Button variant="outline" disabled={busy} onClick={download}>
    {busy ? "Przygotowanie raportu…" : sessionId ? "Pobierz raport sesji HTML" : "Pobierz raport porównania HTML"}
  </Button>{busy && <Button variant="outline" className="ml-3" onClick={() => { active.current?.abort(); setBusy(false); }}>Anuluj raport</Button>}
    {error && <p role="alert" className="mt-2 text-red-800">{error}</p>}</div>;
}
