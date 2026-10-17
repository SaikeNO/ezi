export type Config = {
  url: string;
  strategy: 'dfs' | 'bfs';
  scope: 'server' | 'web';
  links: 'hyperlinks' | 'images' | 'all';
  depth: number;
  page_limit: number;
  resource_limit: number;
  delay: number;
  timeout: number;
};
export type Session = { id: string; name: string; url: string; created: string };
export type Metrics = {
  pages: number;
  subpages: number;
  depth: number;
  traversal_depth: number;
  links: number;
  unique_edges: number;
  resources: number;
  failures: number;
  excluded: number;
  requests: number;
  elapsed: number;
  qualifies: boolean;
  truncated: boolean;
  distribution: Record<string, number>;
};
export type Run = {
  id: string;
  session_id: string;
  purpose: string;
  batch_id: string | null;
  config: Config;
  status: string;
  created: string;
  ended: string | null;
  message: string;
  metrics: Metrics;
};
export type Page = {
  url: string;
  final_url?: string;
  kind: string;
  status: string;
  depth: number | null;
  distance?: number | null;
  external?: boolean;
  outgoing?: number;
  unique_targets?: number;
  title?: string;
  description?: string;
  keywords?: string;
  body?: string;
  error?: string;
  http_status?: number;
  bytes?: number;
};
export type Edge = {
  id: number;
  source: string;
  target: string;
  kind: string;
  disposition: string;
};
export type GraphData = { nodes: Page[]; edges: Edge[] };
export type Study = {
  runs: Run[];
  recommendation: string;
  findings: { parameter: string; label: string; note: string; comparisons: string[] }[];
};
export type Dataset = {
  run_id: string;
  config: Config;
  status: string;
  records: number;
  size: number;
  fields: string[];
  completeness: Record<string, number>;
};
export type Datasets = {
  A: Dataset | null;
  B: Dataset | null;
  comparison: null | {
    common: number;
    only_a: number;
    only_b: number;
    usefulness_a: string;
    usefulness_b: string;
    caveat: string;
  };
};
