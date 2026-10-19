import { request } from "./sessions-api";

export interface PageRow {
  id: string; normalized_url: string; final_url: string | null; depth: number;
  title: string | null; description: string | null; keywords: string | null;
  http_status: number | null; error: string | null;
}
export interface PageList { items: PageRow[]; total: number; offset: number; limit: number }
export interface PageFilters {
  q: string; depth: string; fetched: string; has_error: string; http_status: string;
}
export const emptyFilters: PageFilters = { q: "", depth: "", fetched: "", has_error: "", http_status: "" };
export const fieldLabels = {
  url: "URL", keywords: "Keyword", title: "Title", description: "Description", body: "Body",
  original_url: "Original URL", final_url: "Final URL", depth: "Depth", http_status: "HTTP Status",
  content_type: "Content-Type", encoding: "Encoding", error: "Error",
};
export type ExportField = keyof typeof fieldLabels;
export type Separator = "comma" | "semicolon" | "tab";
function params(filters: PageFilters) {
  const query = new URLSearchParams();
  Object.entries(filters).forEach(([key, value]) => { if (value !== "") query.set(key, value); });
  return query;
}
export const explorerApi = {
  pages: (id: string, filters: PageFilters, offset: number, signal?: AbortSignal) => {
    const query = params(filters); query.set("offset", String(offset)); query.set("limit", "10");
    return request<PageList>("/api/sessions/" + encodeURIComponent(id) + "/pages?" + query, { signal });
  },
  csv: (id: string, filters: PageFilters, fields: ExportField[], separator: Separator, bom: boolean, signal: AbortSignal) => {
    const query = params(filters); query.set("fields", fields.join(",")); query.set("separator", separator); query.set("bom", String(bom));
    return request<Blob>("/api/sessions/" + encodeURIComponent(id) + "/export?" + query, { signal }, true, 60000);
  },
};

export function saveCsv(blob: Blob, id: string) {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url; anchor.download = "crawl-" + id + ".csv";
  document.body.append(anchor); anchor.click(); anchor.remove();
  // Give the browser time to consume the object URL after initiating download.
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}
