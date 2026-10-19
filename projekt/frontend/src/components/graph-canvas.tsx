import { useEffect, useRef, useState } from "react";
import cytoscape, { type Core } from "cytoscape";
import { Button } from "@/components/ui/button";
import type { GraphRead } from "@/types/graph";

export const depthColor = (depth: number) => `hsl(${(175 + depth * 37) % 360}, 65%, 38%)`;
const MIN_ZOOM = 0.0001; // Fit even a permitted 5000-node level before zooming into it.

export function GraphCanvas({ graph, selected, onSelect }: {
  graph: GraphRead; selected: string | null; onSelect: (id: string) => void;
}) {
  const container = useRef<HTMLDivElement>(null);
  const core = useRef<Core | null>(null);
  const select = useRef(onSelect);
  select.current = onSelect;
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    if (!container.current) return;
    let cy: Core;
    try {
      const levels = new Map<number, number>();
      cy = cytoscape({
        container: container.current, minZoom: MIN_ZOOM, maxZoom: 4, wheelSensitivity: 0.2,
        layout: { name: "preset", padding: 35 },
        elements: [
          ...graph.nodes.map(node => {
            const row = levels.get(node.depth) ?? 0;
            levels.set(node.depth, row + 1);
            return { data: { ...node, label: node.url.replace(/^https?:\/\//, "").slice(0, 38),
              color: depthColor(node.depth), resource: node.page_id === null,
              external: node.is_external, pending: !node.fetched, failed: !!node.error },
              position: { x: node.depth * 200, y: row * 95 } };
          }),
          ...graph.edges.map(edge => ({ data: { ...edge, external: edge.is_external } })),
        ],
        style: [
          { selector: "node", style: { label: "data(label)", "background-color": "data(color)",
            width: 32, height: 32, "font-size": 10, "text-valign": "bottom", "text-margin-y": 8,
            "border-width": 2, "border-color": "#fff", color: "#334155" } },
          { selector: "node[?resource]", style: { shape: "diamond" } },
          { selector: "node[?pending]", style: { "background-opacity": 0.4 } },
          { selector: "node[?external]", style: { "border-style": "dashed", "border-color": "#b45309" } },
          { selector: "node[?failed]", style: { "border-color": "#b91c1c", "border-width": 4 } },
          { selector: "edge", style: { width: 1.5, "line-color": "#94a3b8", "target-arrow-color": "#94a3b8",
            "target-arrow-shape": "triangle", "curve-style": "bezier" } },
          { selector: "edge[?external]", style: { "line-color": "#d97706", "line-style": "dashed" } },
          { selector: "node:selected", style: { "border-width": 5, "border-color": "#0f172a" } },
        ],
      });
      core.current = cy;
      cy.on("tap", "node", event => select.current(event.target.id()));
      setFailed(false);
    } catch {
      setFailed(true);
      return;
    }
    const observer = new ResizeObserver(() => cy.resize());
    observer.observe(container.current);
    return () => { observer.disconnect(); cy.destroy(); core.current = null; };
  }, [graph]);
  useEffect(() => {
    const cy = core.current;
    if (!cy) return;
    cy.nodes().unselect();
    if (selected) {
      const node = cy.getElementById(selected);
      node.select();
      cy.center(node);
    }
  }, [selected, graph]);
  return <section className="min-w-0 rounded-2xl border bg-white p-3" aria-label="Wizualizacja grafu">
    <div className="flex flex-wrap gap-2 p-2">
      <Button variant="outline" onClick={() => core.current?.zoom(Math.min(4, (core.current?.zoom() ?? 1) * 1.3))}>Powiększ</Button>
      <Button variant="outline" onClick={() => core.current?.zoom(Math.max(MIN_ZOOM, (core.current?.zoom() ?? 1) / 1.3))}>Pomniejsz</Button>
      <Button variant="outline" onClick={() => core.current?.fit(undefined, 35)}>Dopasuj graf</Button>
    </div>
    <p className="px-2 text-xs text-muted-foreground">Przeciągnij tło, aby przesunąć. Kółko lub gest szczypania zmienia skalę. Kliknij węzeł.</p>
    {failed && <p role="alert">Nie można wyświetlić grafu. Wybierz węzeł z listy poniżej.</p>}
    <div ref={container} data-testid="graph-canvas" className="h-[440px] w-full touch-none" />
    <p className="px-2 text-xs text-muted-foreground">Koło: strona · romb: cel zasobu · jasny: niepobrany · czerwona obwódka: błąd · przerywany: zewnętrzny.</p>
    <div className="mt-3 flex flex-wrap gap-3 px-2 text-xs" aria-label="Kolory głębokości">
      {[...new Set(graph.nodes.map(node => node.depth))].sort((a,b) => a-b).map(depth =>
        <span key={depth}><span className="mr-1 inline-block size-3 rounded-full" style={{ background: depthColor(depth) }} />Poziom {depth}</span>)}
    </div>
  </section>;
}
