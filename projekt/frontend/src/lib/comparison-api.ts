import { request } from "./sessions-api";
import type { CrawlConfig, CrawlSession } from "@/types/sessions";

export interface Experiment { id: string; name: string; start_url: string; created_at: string;
  state: "queued" | "running" | "finished" | "incomplete"; sessions: CrawlSession[] }
export interface Results<T> { items: T[]; total: number; offset: number; limit: number }
export interface TextValue { value: string | null; length: number | null; sha256: string | null; truncated: boolean }
export interface Edge { source: string; target: string; kind: string }
export interface Pair {
  left_id: string; right_id: string; config_changes: Record<string, Array<string | number | boolean>>;
  discovered: UrlSets; fetched: UrlSets;
  edges: { common: Results<Edge>; left_only: Results<Edge>; right_only: Results<Edge>;
    multiplicity_changes: Results<Edge & { left_count: number; right_count: number }> };
  metadata_changes: Results<{ url: string; fields: Record<string, TextValue[]> }>;
  depth_changes: Results<{ url: string; left: number; right: number }>;
  retrieval_order_equal: boolean; observations: string[];
}
export interface UrlSets { common: Results<string>; left_only: Results<string>; right_only: Results<string> }
export interface RunMetrics {
  session: CrawlSession; discovered_pages: number; fetched_pages: number; attempted_pages: number;
  errored_pages: number; link_count: number; unique_typed_edges: number; reached_depth: number | null;
  elapsed_seconds: number | null; metadata_present: Record<string, number>; retrieval_order: Results<string>;
}
export interface Comparison { start_url: string; runs: RunMetrics[]; pairs: Pair[]; notes: string[] }
export const comparisonApi = {
  create: (name: string, start_url: string, variants: CrawlConfig[]) => request<Experiment>("/api/experiments", { method: "POST", body: JSON.stringify({ name, start_url, variants }) }),
  list: (offset = 0, signal?: AbortSignal) => request<Results<Experiment>>("/api/experiments?limit=10&offset=" + offset, { signal }),
  read: (id: string, signal?: AbortSignal) => request<Experiment>("/api/experiments/" + encodeURIComponent(id), { signal }),
  start: (id: string) => request<{ experiment: Experiment; errors: Array<{ session_id: string; code: string; message: string }> }>("/api/experiments/" + encodeURIComponent(id) + "/start", { method: "POST" }),
  remove: (id: string) => request<void>("/api/experiments/" + encodeURIComponent(id), { method: "DELETE" }),
  compare: (session_ids: string[], offset: number, signal?: AbortSignal) => request<Comparison>("/api/compare?limit=25&offset=" + offset, { method: "POST", body: JSON.stringify({ session_ids }), signal }, false, 45000),
};
