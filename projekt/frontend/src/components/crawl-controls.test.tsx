import { useState } from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { CrawlControls } from "./crawl-controls";
import { sessionsApi } from "@/lib/sessions-api";
import { defaultConfig, type CrawlSession } from "@/types/sessions";

const queued: CrawlSession = {
  id: "8c72aaff-6592-4e99-aeb9-0497090846dc",
  start_url: "https://example.com/",
  config: defaultConfig,
  status: "queued",
  created_at: "2026-10-19T08:00:00Z",
  started_at: null,
  finished_at: null,
  error: null,
  stop_reason: null,
  discovered_count: 0,
  fetched_count: 0,
  error_count: 0,
  link_count: 0,
  crawler_version: null,
  user_agent: null,
};
class Source extends EventTarget {
  static instances: Source[] = [];
  closed = false;
  onerror: (() => void) | null = null;
  constructor(public url: string) {
    super();
    Source.instances.push(this);
  }
  close() {
    this.closed = true;
  }
}
function mount(initial = queued, disabled = false) {
  Source.instances = [];
  vi.stubGlobal("EventSource", Source);
  function Wrapper() {
    const [session, setSession] = useState(initial);
    return (
      <CrawlControls
        session={session}
        onChange={setSession}
        disabled={disabled}
      />
    );
  }
  return render(<Wrapper />);
}

describe("crawler controls", () => {
  it("starts and cancels using API state", async () => {
    const running = {
      ...queued,
      status: "running" as const,
      discovered_count: 1,
    };
    vi.spyOn(sessionsApi, "start").mockResolvedValue(running);
    vi.spyOn(sessionsApi, "read").mockResolvedValue(running);
    vi.spyOn(sessionsApi, "cancel").mockResolvedValue({
      ...running,
      status: "cancelled",
      stop_reason: "user_cancelled",
    });
    mount();
    await userEvent.click(
      screen.getByRole("button", { name: "Uruchom crawler" }),
    );
    await waitFor(() =>
      expect(sessionsApi.start).toHaveBeenCalledWith(queued.id),
    );
    expect(
      await screen.findByRole("button", { name: "Anuluj sesję" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Uruchom crawler" }),
    ).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Anuluj sesję" }));
    expect(await screen.findByRole("status")).toHaveTextContent(
      "Sesja anulowana",
    );
    expect(sessionsApi.cancel).toHaveBeenCalledWith(queued.id);
  });

  it("reads actual progress after SSE notification and closes on completion", async () => {
    const running = {
      ...queued,
      status: "running" as const,
      discovered_count: 3,
    };
    vi.spyOn(sessionsApi, "read")
      .mockResolvedValueOnce(running)
      .mockResolvedValue({
        ...running,
        status: "completed",
        fetched_count: 3,
        link_count: 5,
        stop_reason: "page_limit",
      });
    mount(running);
    await waitFor(() => expect(Source.instances).toHaveLength(1));
    Source.instances[0].dispatchEvent(new Event("progress"));
    expect(await screen.findByRole("status")).toHaveTextContent(
      "limit prób pobrania",
    );
    expect(
      screen.getByText("Pobrane HTML").nextElementSibling,
    ).toHaveTextContent("3");
    expect(
      screen.getByText("Odnalezione odnośniki").nextElementSibling,
    ).toHaveTextContent("5");
    expect(Source.instances[0].closed).toBe(true);
  });

  it("shows start failure without inventing running state", async () => {
    vi.spyOn(sessionsApi, "start").mockRejectedValue(
      new Error("Osiągnięto limit równoczesnych sesji"),
    );
    mount();
    await userEvent.click(
      screen.getByRole("button", { name: "Uruchom crawler" }),
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "limit równoczesnych sesji",
    );
    expect(
      screen.getByRole("button", { name: "Uruchom crawler" }),
    ).toBeEnabled();
    expect(Source.instances).toHaveLength(0);
  });

  it("disables actions during unsaved editing", () => {
    mount(queued, true);
    expect(
      screen.getByRole("button", { name: "Uruchom crawler" }),
    ).toBeDisabled();
    expect(screen.getByRole("button", { name: "Anuluj sesję" })).toBeDisabled();
  });

  it("closes stream and aborts pending reads when unmounted", async () => {
    let signal: AbortSignal | undefined;
    vi.spyOn(sessionsApi, "read").mockImplementation((_id, value) => {
      signal = value;
      return new Promise(() => {});
    });
    const view = mount({ ...queued, status: "running" });
    await waitFor(() => expect(signal).toBeDefined());
    view.unmount();
    expect(signal?.aborted).toBe(true);
    expect(Source.instances[0].closed).toBe(true);
  });
});
