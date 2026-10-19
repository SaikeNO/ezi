import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { GraphPage } from "./graph";
import type { GraphRead } from "@/types/graph";

vi.mock("@/components/graph-canvas", () => ({ GraphCanvas: () => <div>Canvas</div> }));
const node = { id: "page:a", page_id: "a", url: "https://example.com/", title: "Home",
  depth: 0, fetched: true, is_external: false, http_status: 200, error: null,
  in_degree: 1, out_degree: 2, unique_in_degree: 1, unique_out_degree: 1 };
const graph: GraphRead = { session_id: "s", status: "completed", nodes: [node,
  { ...node, id: "target:b", page_id: null, url: "https://example.com/a.png", title: null, fetched: false, depth: 1 }],
  edges: [], per_depth: [], summary: {
    node_count: 2, page_count: 1, resource_target_count: 1, fetched_pages: 1, errored_pages: 0,
    reached_depth: 0, discovered_depth: 0, link_count: 2, unique_relations: 1,
    internal_links: 2, external_links: 0, root_links: 2, root_unique_targets: 1,
    subpage_links: 0, subpage_unique_targets: 0 } };
const response = (data: unknown, status = 200) => new Response(JSON.stringify(data), { status });
function mount(path = "/graph/s") {
  return render(<MemoryRouter initialEntries={[path]}><Routes>
    <Route path="/graph/:id?" element={<GraphPage />} />
  </Routes></MemoryRouter>);
}

describe("stored graph view", () => {
  it("uses server stats, searches and renders untrusted metadata as text", async () => {
    const fetcher = vi.fn((url: string) => Promise.resolve(response(url.endsWith("/graph") ? graph : {
      title: "<script>alert(1)</script>", description: "Desc", keywords: null, body: "<b>body</b>",
      final_url: node.url, content_type: "text/html", encoding: "utf-8" })));
    vi.stubGlobal("fetch", fetcher); mount();
    const stats = await screen.findByRole("region", { name: "Statystyki grafu" });
    expect(within(stats).getByText("Wystąpienia linków").nextElementSibling).toHaveTextContent("2");
    await userEvent.type(screen.getByRole("textbox"), "HOME");
    expect(screen.queryByRole("button", { name: "https://example.com/a.png" })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: node.url }));
    expect(await screen.findByText("<script>alert(1)</script>")).toBeInTheDocument();
    expect(screen.getByText("<b>body</b>")).toBeInTheDocument();
    expect(document.querySelector("script")).toBeNull();
    await userEvent.clear(screen.getByRole("textbox"));
    await userEvent.type(screen.getByRole("textbox"), ".png");
    await userEvent.click(screen.getByRole("button", { name: "https://example.com/a.png" }));
    expect(await screen.findByText(/Cel odnośnika bez rekordu/)).toBeInTheDocument();
    expect(fetcher).toHaveBeenCalledTimes(2);
  });

  it("empty graph keeps honest null depth and no canvas", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response({ ...graph, nodes: [],
      summary: { ...graph.summary, reached_depth: null } })));
    mount();
    expect(await screen.findByText(/Brak zapisanych węzłów/)).toBeInTheDocument();
    expect(screen.queryByText("Canvas")).not.toBeInTheDocument();
    expect(screen.getByText("Osiągnięta głębokość HTML").nextElementSibling).toHaveTextContent("—");
  });

  it("failure retries and reloads graph", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValueOnce(new Error("offline")).mockResolvedValue(response(graph)));
    mount(); await screen.findByRole("alert");
    await userEvent.click(screen.getByRole("button", { name: "Odśwież graf" }));
    expect(await screen.findByText("Canvas")).toBeInTheDocument();
  });

  it("oversized graph shows full stats without partial visualization", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(response({ message: "large" }, 413))
      .mockResolvedValueOnce(response({ ...graph, per_page: [] })));
    mount();
    expect(await screen.findByRole("alert")).toHaveTextContent("Pokazano pełne statystyki");
    expect(screen.queryByText("Canvas")).not.toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Statystyki grafu" })).toBeInTheDocument();
  });

  it("aborts graph read on unmount", async () => {
    let signal: AbortSignal | undefined;
    vi.stubGlobal("fetch", vi.fn((_url, init: RequestInit) => {
      signal = init.signal as AbortSignal; return new Promise(() => {});
    }));
    const view = mount(); await waitFor(() => expect(signal).toBeDefined());
    view.unmount(); expect(signal?.aborted).toBe(true);
  });

  it("chooser supports empty sessions and pagination", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response({ items: [], total: 0, offset: 0, limit: 10 })));
    mount("/graph");
    expect(await screen.findByText(/Brak zapisanych sesji/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Następne" })).toBeDisabled();
  });
});
