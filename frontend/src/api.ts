import { useEffect, useRef, useState } from "react";

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(path, { headers: { "Content-Type": "application/json" }, ...init });
  if (!r.ok) {
    let detail = r.statusText;
    try { detail = (await r.json()).detail ?? detail; } catch { /* ignore */ }
    throw new Error(detail);
  }
  return r.json() as Promise<T>;
}
const post = <T,>(p: string, body?: unknown) => req<T>(p, { method: "POST", body: body ? JSON.stringify(body) : undefined });

export interface Progress { phase: string; done?: number; total?: number; counts?: Record<string, number>; downloaded?: number; failed?: number; bytes?: number; path?: string; brand?: string; chunks?: number; pages?: number }
export interface Job { id: string; kind: string; status: string; started_at: string; finished_at?: string; error?: string }
export interface Dashboard {
  configured: boolean; domain: string; brands: number; assets: number; total_bytes: number; downloaded: number; failed: number;
  pending: number; unavailable: number; documents: number; guideline_pages: number; deleted_assets: number; chunks: number;
  last_sync: { id: number; kind: string; started_at: string; finished_at: string; status: string } | null;
  job: { running: boolean; job: Job | null }; progress: Progress | null;
}
export interface Settings {
  frontify_domain: string; export_dir: string; download_concurrency: number; api_concurrency: number; page_size: number;
  embeddings_provider: string; embeddings_model: string; vector_store: string; qdrant_url: string; ocr_enabled: boolean;
  include_related_assets: boolean; dedupe_hardlinks: boolean; has_token: boolean; token_source: string; has_openai_key: boolean;
}
export interface Brand { id: string; name: string; slug: string; assets: number; folders: number; guideline_pages: number }
export interface Asset {
  id: string; brand_id: string; title: string; filename: string | null; extension: string | null; mime: string | null; size: number | null;
  category: string; folder_path: string; created_at: string | null; modified_at: string | null; download_status: string;
  local_path: string | null; sha256: string | null; error: string | null; duplicate_of: string | null;
}
export interface Tree {
  containers: { id: string; kind: string; name: string; expected_assets: number | null; scan_complete: number }[];
  folders: { id: string; container_id: string; parent_id: string | null; name: string; path: string }[];
  guidelines: { id: string; parent_id: string | null; guideline_id: string; title: string; url: string | null; kind: string; path: string; position: number; export_status: string }[];
}
export interface SyncRun { id: number; kind: string; started_at: string; finished_at: string | null; status: string; changes: Record<string, Record<string, number>>; duration_seconds?: number }
export interface SearchHit { id: string; score: number; mode: string; text: string; metadata: Record<string, string | number | null> }

export const api = {
  dashboard: () => req<Dashboard>("/api/dashboard"),
  settings: () => req<Settings>("/api/settings"),
  saveSettings: (values: Partial<Settings>, token?: string) => req<Settings>("/api/settings", { method: "PUT", body: JSON.stringify({ values, token }) }),
  test: () => post<{ ok: boolean; error?: string; user?: string; brands?: { id: string; name: string }[] }>("/api/connection/test"),
  scan: (body: object) => post<Job>("/api/scan", body),
  exportAll: (body: object) => post<Job>("/api/export", body),
  cancel: () => post<{ cancelling: boolean }>("/api/jobs/cancel"),
  jobs: () => req<{ running: boolean; job: Job | null; history: Job[] }>("/api/jobs"),
  brands: () => req<Brand[]>("/api/brands"),
  tree: (id: string) => req<Tree>(`/api/brands/${id}/tree`),
  assets: (p: Record<string, string>) => req<{ total: number; items: Asset[] }>(`/api/assets?${new URLSearchParams(p)}`),
  asset: (id: string) => req<Record<string, unknown>>(`/api/assets/${id}`),
  guideline: (id: string) => req<{ title: string; path: string; url: string | null; markdown: string | null; export_status: string }>(`/api/guidelines/${id}`),
  syncHistory: () => req<SyncRun[]>("/api/sync/history"),
  syncChanges: (id: number) => req<{ entity: string; entity_id: string; change: string; name: string }[]>(`/api/sync/${id}/changes`),
  report: () => req<Record<string, any>>("/api/report"), // eslint-disable-line @typescript-eslint/no-explicit-any
  failures: () => req<{ assets: { id: string; title: string; folder_path: string; download_status: string; error: string | null }[]; pages: { id: string; title: string; error: string | null }[] }>("/api/failures"),
  search: (q: string, brand_id?: string) => req<{ results: SearchHit[] }>(`/api/search?${new URLSearchParams({ q, ...(brand_id ? { brand_id } : {}) })}`),
};

export function usePoll<T>(fn: () => Promise<T>, ms = 2000, deps: unknown[] = []): { data: T | null; error: string | null; reload: () => void } {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);
  useEffect(() => {
    let alive = true;
    const run = () => fn().then((d) => { if (alive) { setData(d); setError(null); } }).catch((e: Error) => alive && setError(e.message));
    run();
    const t = ms > 0 ? setInterval(run, ms) : undefined;
    return () => { alive = false; if (t) clearInterval(t); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tick, ms, ...deps]);
  return { data, error, reload: () => setTick((x) => x + 1) };
}

export interface LogLine { id: number; ts: number; level: string; message: string }
/** Realtime logs + progress through Server-Sent Events. */
export function useEvents(): { logs: LogLine[]; progress: Progress | null; jobEvent: Job | null } {
  const [logs, setLogs] = useState<LogLine[]>([]);
  const [progress, setProgress] = useState<Progress | null>(null);
  const [jobEvent, setJob] = useState<Job | null>(null);
  const seen = useRef(new Set<number>());
  useEffect(() => {
    const es = new EventSource("/api/events");
    const handle = (kind: string) => (m: MessageEvent) => {
      const e = JSON.parse(m.data) as { id: number; ts: number; data: Record<string, unknown> };
      if (seen.current.has(e.id)) return;
      seen.current.add(e.id);
      if (kind === "log") setLogs((l) => [...l.slice(-499), { id: e.id, ts: e.ts, level: String(e.data.level), message: String(e.data.message) }]);
      if (kind === "progress") setProgress(e.data as unknown as Progress);
      if (kind === "job") setJob(e.data as unknown as Job);
    };
    (["log", "progress", "job"] as const).forEach((k) => es.addEventListener(k, handle(k)));
    return () => es.close();
  }, []);
  return { logs, progress, jobEvent };
}

export const fmtBytes = (n: number | null | undefined) => {
  let v = n ?? 0; const u = ["B", "KB", "MB", "GB", "TB"]; let i = 0;
  while (v >= 1024 && i < u.length - 1) { v /= 1024; i++; }
  return `${v.toFixed(i ? 1 : 0)} ${u[i]}`;
};
export const fmtDate = (s?: string | null) => (s ? new Date(s).toLocaleString() : "—");
