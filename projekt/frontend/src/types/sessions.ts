export type SessionStatus =
  | "queued"
  | "running"
  | "completed"
  | "failed"
  | "cancelled";

export interface CrawlConfig {
  strategy: "bfs" | "dfs";
  scope: "server" | "web";
  link_types: "hyperlinks" | "images_and_hyperlinks" | "all_links";
  max_depth: number;
  max_pages: number;
  timeout_seconds: number;
  request_delay_ms: number;
  max_duration_seconds: number;
  max_response_bytes: number;
  max_redirects: number;
  concurrency: number;
  respect_robots: boolean;
  follow_external_urls: boolean;
  process_one_page: boolean;
}

export interface SessionInput {
  start_url: string;
  config: CrawlConfig;
}
export interface CrawlSession extends SessionInput {
  id: string;
  status: SessionStatus;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  discovered_count: number;
  fetched_count: number;
  error_count: number;
  error: string | null;
  link_count: number;
  stop_reason: string | null;
  crawler_version: string | null;
  user_agent: string | null;
}
export interface SessionList {
  items: CrawlSession[];
  total: number;
  offset: number;
  limit: number;
}

export const statusLabels: Record<SessionStatus, string> = {
  queued: "Oczekująca",
  running: "W trakcie",
  completed: "Zakończona",
  failed: "Błąd",
  cancelled: "Anulowana",
};

export const defaultConfig: CrawlConfig = {
  strategy: "bfs",
  scope: "server",
  link_types: "hyperlinks",
  max_depth: 3,
  max_pages: 100,
  timeout_seconds: 10,
  request_delay_ms: 500,
  max_duration_seconds: 300,
  max_response_bytes: 2097152,
  max_redirects: 5,
  concurrency: 2,
  respect_robots: true,
  follow_external_urls: false,
  process_one_page: false,
};
