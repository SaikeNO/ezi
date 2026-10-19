import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { ComparisonResults } from "./comparison-results";
import type { Comparison, Results } from "@/lib/comparison-api";
import { defaultConfig } from "@/types/sessions";

vi.mock("recharts", () => {
  const Wrapper = ({ children }: { children?: React.ReactNode }) => <div>{children}</div>;
  return { ResponsiveContainer: Wrapper, BarChart: Wrapper, Bar: () => null,
    XAxis: () => null, YAxis: () => null, Tooltip: () => null, Legend: () => null, CartesianGrid: () => null };
});
function results<T>(items: T[], total = items.length): Results<T> { return { items, total, offset: 0, limit: 25 }; }
const sets = { common: results(["https://example.com/"]), left_only: results<string>([]), right_only: results<string>([]) };
const value = { value: "<script>alert(1)</script>", length: 25, sha256: "hash", truncated: false };
const data = { start_url: "https://example.com/", notes: ["BFS/DFS nie gwarantuje różnych zbiorów."],
  runs: ["a", "b"].map(id => ({ session: { id, config: defaultConfig, status: "completed", stop_reason: "frontier_exhausted", crawler_version: "0.3", user_agent: "UA" },
    discovered_pages: 7, fetched_pages: 6, attempted_pages: 7, errored_pages: 1, link_count: 9,
    unique_typed_edges: 8, reached_depth: 3, elapsed_seconds: 1.234, metadata_present: { title: 6 },
    retrieval_order: results(["https://example.com/"], 30) })),
  pairs: [{ left_id: "a", right_id: "b", config_changes: { strategy: ["bfs", "dfs"] },
    discovered: sets, fetched: sets, edges: { common: results([]), left_only: results([]), right_only: results([]), multiplicity_changes: results([]) },
    metadata_changes: results([{ url: "https://example.com/", fields: { title: [{ ...value, value: null, sha256: null, length: null }, value] } }]),
    depth_changes: results([]), retrieval_order_equal: false, observations: ["Wspólne HTML: 1."] }],
} as unknown as Comparison;
const response = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status });
function mount() { return render(<MemoryRouter><ComparisonResults ids={["a", "b"]} /></MemoryRouter>); }

describe("saved comparison", () => {
  it("shows measured metrics, safe metadata, config and whole-result counts", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response(data))); mount();
    expect(await screen.findByText("BFS/DFS nie gwarantuje różnych zbiorów.")).toBeInTheDocument();
    expect(screen.getAllByText("1.234")).toHaveLength(2);
    await userEvent.click(screen.getByText("Zmiany metadanych wspólnie pobranych HTML: 1"));
    expect(screen.getByText("<script>alert(1)</script>")).toBeVisible();
    expect(document.querySelector("script")).toBeNull();
    expect(screen.getByText("Brak (null)")).toBeVisible();
    expect(screen.getByText("strategy: bfs → dfs")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Następna partia" })).toBeEnabled();
  });
  it("requests next result batch, preserving chosen session order", async () => {
    const fetcher = vi.fn().mockImplementation(() => Promise.resolve(response(data)));
    vi.stubGlobal("fetch", fetcher); mount(); await screen.findByText("A względem B");
    await userEvent.click(screen.getByRole("button", { name: "Następna partia" }));
    await waitFor(() => expect(fetcher).toHaveBeenLastCalledWith(expect.stringContaining("offset=25"), expect.objectContaining({ body: JSON.stringify({ session_ids: ["a", "b"] }) })));
  });
  it("readiness errors support retry", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(response({ message: "Poczekaj na zakończenie" }, 409)).mockResolvedValue(response(data)));
    mount(); expect(await screen.findByRole("alert")).toHaveTextContent("Poczekaj");
    await userEvent.click(screen.getByRole("button", { name: "Ponów porównanie" }));
    expect(await screen.findByText("A względem B")).toBeInTheDocument();
  });
  it("aborts when leaving comparison", async () => {
    let signal: AbortSignal | undefined;
    vi.stubGlobal("fetch", vi.fn((_url, options) => { signal = options.signal; return new Promise(() => {}); }));
    const view = mount(); await waitFor(() => expect(signal).toBeDefined());
    view.unmount(); expect(signal?.aborted).toBe(true);
  });
});
