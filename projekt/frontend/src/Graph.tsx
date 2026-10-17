import { useMemo, useRef, useState } from 'react';
import { Crosshair, Minus, Plus, MousePointer2 } from 'lucide-react';
import type { GraphData, Page } from './types';

export function Graph({ data, onSelect }: { data: GraphData; onSelect: (page: Page) => void }) {
  const [filter, setFilter] = useState('all');
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const drag = useRef<{ x: number; y: number; px: number; py: number } | null>(null);
  const moved = useRef(false);
  const nodes = useMemo(
    () =>
      data.nodes.filter(
        (n) =>
          filter === 'all' ||
          (filter === 'page' && n.kind === 'page') ||
          (filter === 'resource' && n.kind === 'resource') ||
          (filter === 'external' && n.external) ||
          (filter === 'error' && n.status === 'error'),
      ),
    [data, filter],
  );
  const { positions, height, width } = useMemo(() => {
    const groups = new Map<number, Page[]>();
    nodes.forEach((n) => {
      const d = n.distance ?? n.depth ?? 0;
      groups.set(d, [...(groups.get(d) || []), n]);
    });
    const height = Math.max(
      520,
      Math.min(1100, Math.max(0, ...Array.from(groups.values()).map((g) => g.length * 18 + 80))),
    );
    const width = Math.max(920, (Math.max(0, ...groups.keys()) + 1) * 200 + 120);
    const positions = new Map<string, { x: number; y: number }>();
    groups.forEach((items, depth) =>
      items.forEach((n, i) =>
        positions.set(n.url, { x: 80 + depth * 200, y: ((i + 1) * height) / (items.length + 1) }),
      ),
    );
    return { positions, height, width };
  }, [nodes]);
  const color = (n: Page) =>
    n.status === 'error'
      ? '#d56d60'
      : n.status !== 'ok'
        ? '#bac3ca'
        : n.external
          ? '#d2a362'
          : n.kind === 'resource'
            ? '#7892b4'
            : '#438b70';
  return (
    <div className="graph-wrap">
      <div className="graph-toolbar">
        <div className="segmented">
          {[
            ['all', 'Wszystkie'],
            ['page', 'Strony'],
            ['resource', 'Zasoby'],
            ['external', 'Zewnętrzne'],
            ['error', 'Błędy'],
          ].map(([v, l]) => (
            <button key={v} className={filter === v ? 'chosen' : ''} onClick={() => setFilter(v)}>
              {l}
            </button>
          ))}
        </div>
        <span>{nodes.length} węzłów</span>
      </div>
      <svg
        className="graph-canvas"
        viewBox={`0 0 ${width} ${height}`}
        role="img"
        aria-label="Interaktywny graf odkrytych adresów"
        onWheel={(e) => {
          setZoom((z) => Math.min(5, Math.max(0.25, z * (e.deltaY < 0 ? 1.1 : 0.9))));
        }}
        onPointerDown={(e) => {
          moved.current = false;
          if ((e.target as Element).closest('.graph-node')) return;
          drag.current = { x: e.clientX, y: e.clientY, px: pan.x, py: pan.y };
          moved.current = false;
          e.currentTarget.setPointerCapture(e.pointerId);
        }}
        onPointerMove={(e) => {
          if (drag.current) {
            const dx = ((e.clientX - drag.current.x) * width) / e.currentTarget.clientWidth,
              dy = ((e.clientY - drag.current.y) * height) / e.currentTarget.clientHeight;
            if (Math.abs(dx) + Math.abs(dy) > 4) moved.current = true;
            setPan({ x: drag.current.px + dx, y: drag.current.py + dy });
          }
        }}
        onPointerUp={() => {
          drag.current = null;
        }}
      >
        <defs>
          <pattern id="dots" width="22" height="22" patternUnits="userSpaceOnUse">
            <circle cx="1" cy="1" r="1" fill="#d8dfdf" />
          </pattern>
          <marker
            id="arrow"
            viewBox="0 0 10 10"
            refX="12"
            refY="5"
            markerWidth="4"
            markerHeight="4"
            orient="auto-start-reverse"
          >
            <path d="M 0 0 L 10 5 L 0 10 z" fill="#a1b7ac" />
          </marker>
        </defs>
        <rect width="100%" height="100%" fill="url(#dots)" />
        <g transform={`translate(${pan.x} ${pan.y}) scale(${zoom})`}>
          {data.edges.map((e) => {
            const a = positions.get(e.source),
              b = positions.get(e.target);
            return a && b ? (
              <path
                key={e.id}
                d={`M${a.x},${a.y} C${(a.x + b.x) / 2},${a.y} ${(a.x + b.x) / 2},${b.y} ${b.x},${b.y}`}
                fill="none"
                stroke="#b6c9c0"
                strokeWidth="1.2"
                opacity=".55"
                markerEnd="url(#arrow)"
              />
            ) : null;
          })}
          {nodes.map((n) => {
            const p = positions.get(n.url)!;
            let label = n.url;
            try {
              const u = new URL(n.url);
              label = u.pathname === '/' ? u.hostname : u.pathname;
            } catch {
              /* Unsupported URL is still displayed. */
            }
            return (
              <g
                key={n.url}
                className="graph-node"
                tabIndex={0}
                role="button"
                aria-label={`Adres ${n.url}`}
                transform={`translate(${p.x} ${p.y})`}
                onClick={() => {
                  if (!moved.current) onSelect(n);
                }}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') onSelect(n);
                }}
              >
                <title>
                  {n.url} · {n.status}
                </title>
                <circle r={n.depth === 0 ? 13 : 8} fill={color(n)} stroke="white" strokeWidth="3" />
                <text x="16" y="4" fontSize="10" fill="#51645b">
                  {label.length > 24 ? label.slice(0, 23) + '…' : label}
                </text>
              </g>
            );
          })}
        </g>
        {!nodes.length && (
          <text x="50%" y="50%" textAnchor="middle" fill="#7d8d85" fontSize="15">
            Graf pojawi się po rozpoczęciu badania
          </text>
        )}
      </svg>
      <div className="graph-bottom">
        <span>
          <MousePointer2 size={13} /> Przeciągnij, aby przesunąć · kliknij węzeł
        </span>
        <div className="zoom">
          <button aria-label="Oddal" onClick={() => setZoom((z) => Math.max(0.25, z - 0.2))}>
            <Minus size={15} />
          </button>
          <span>{Math.round(zoom * 100)}%</span>
          <button aria-label="Przybliż" onClick={() => setZoom((z) => Math.min(5, z + 0.2))}>
            <Plus size={15} />
          </button>
          <button
            aria-label="Wycentruj graf"
            onClick={() => {
              setZoom(1);
              setPan({ x: 0, y: 0 });
            }}
          >
            <Crosshair size={15} />
          </button>
        </div>
      </div>
      <div className="graph-legend">
        {[
          ['#438b70', 'Strona HTML'],
          ['#7892b4', 'Zasób'],
          ['#d2a362', 'Adres zewnętrzny'],
          ['#d56d60', 'Błąd'],
          ['#bac3ca', 'Niepobrany / pominięty'],
        ].map(([c, l]) => (
          <span key={l}>
            <i style={{ background: c }} />
            {l}
          </span>
        ))}
      </div>
    </div>
  );
}
