import type { SessionStatus } from "./sessions";

export interface GraphNode {
  id: string; page_id: string | null; url: string; title: string | null;
  depth: number; fetched: boolean; is_external: boolean;
  http_status: number | null; error: string | null;
  in_degree: number; out_degree: number;
  unique_in_degree: number; unique_out_degree: number;
}
export interface GraphEdge {
  id: string; source: string; target: string; target_url: string;
  kind: string; is_external: boolean; is_followed: boolean;
}
export interface GraphSummary {
  node_count: number; page_count: number; resource_target_count: number;
  fetched_pages: number; errored_pages: number;
  reached_depth: number | null; discovered_depth: number | null;
  link_count: number; unique_relations: number;
  internal_links: number; external_links: number;
  root_links: number; root_unique_targets: number;
  subpage_links: number; subpage_unique_targets: number;
}
export interface DepthStats {
  depth: number; pages: number; fetched_pages: number; outgoing_links: number;
}
export interface GraphRead {
  session_id: string; status: SessionStatus; nodes: GraphNode[]; edges: GraphEdge[];
  summary: GraphSummary; per_depth: DepthStats[];
}
export interface GraphStats extends Omit<GraphRead, "nodes" | "edges"> {
  per_page: Array<Pick<GraphNode, "page_id" | "url" | "depth" | "fetched" |
    "in_degree" | "out_degree" | "unique_in_degree" | "unique_out_degree">>;
}
export interface PageDetail {
  title: string | null; description: string | null; keywords: string | null;
  body: string | null; final_url: string | null;
  content_type: string | null; encoding: string | null;
}
