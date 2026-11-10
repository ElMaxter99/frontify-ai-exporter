import { useEffect, useRef, useState } from "react";
import { api, Brand, fmtBytes, useEvents, usePoll } from "../api";
import { Badge, ErrorBox, ProgressBar } from "../components/ui";

const CATS = ["images", "logos", "icons", "videos", "audio", "documents", "fonts", "other"];

export default function ExportPage() {
  const { data: brands } = usePoll<Brand[]>(api.brands, 0);
  const { data: jobs, reload } = usePoll(api.jobs, 1500);
  const { logs, progress } = useEvents();
  const [sel, setSel] = useState<Set<string>>(new Set());
  const [cats, setCats] = useState<Set<string>>(new Set());
  const [opts, setOpts] = useState({ force: false, guidelines: true, download: true, index: true });
  const [err, setErr] = useState<string | null>(null);
  const [report, setReport] = useState<Record<string, any> | null>(null); // eslint-disable-line @typescript-eslint/no-explicit-any
  const [failures, setFailures] = useState<Awaited<ReturnType<typeof api.failures>> | null>(null);
  const logRef = useRef<HTMLDivElement>(null);
  const running = !!jobs?.running;

  useEffect(() => { logRef.current?.scrollTo({ top: logRef.current.scrollHeight }); }, [logs]);
  useEffect(() => { if (!running) { api.report().then(setReport).catch(() => undefined); api.failures().then(setFailures).catch(() => undefined); } }, [running]);

  const body = () => ({ brand_ids: sel.size ? [...sel] : null, categories: cats.size ? [...cats] : null, ...opts });
  const run = async (fn: () => Promise<unknown>) => { setErr(null); try { await fn(); reload(); } catch (e) { setErr((e as Error).message); } };
  const toggle = (s: Set<string>, v: string, set: (x: Set<string>) => void) => { const n = new Set(s); n.has(v) ? n.delete(v) : n.add(v); set(n); };

  return (
    <div className="grid gap-4 lg:grid-cols-[22rem_1fr]">
      <div className="space-y-4">
        <section className="card space-y-3">
          <h2 className="font-semibold">1 · Scan</h2>
          <p className="text-sm text-slate-600">Discovers brands, libraries, folders, assets and guideline structure. Nothing is downloaded.</p>
          <button className="btn-secondary w-full" disabled={running} onClick={() => run(() => api.scan({ brand_ids: sel.size ? [...sel] : null }))}>Scan Frontify</button>
        </section>
        <section className="card space-y-3">
          <h2 className="font-semibold">2 · Export</h2>
          <div><div className="label">Brands {sel.size ? `(${sel.size})` : "(all)"}</div>
            <div className="max-h-40 space-y-1 overflow-auto">{brands?.map((b) => (
              <label key={b.id} className="flex items-center gap-2 text-sm"><input type="checkbox" checked={sel.has(b.id)} onChange={() => toggle(sel, b.id, setSel)} />{b.name} <span className="text-xs text-slate-400">{b.assets} assets</span></label>
            ))}{!brands?.length && <div className="text-sm text-slate-500">Scan first to list brands (export also scans).</div>}</div></div>
          <div><div className="label">Asset types {cats.size ? "" : "(all)"}</div>
            <div className="flex flex-wrap gap-1.5">{CATS.map((c) => (
              <button key={c} onClick={() => toggle(cats, c, setCats)} className={`rounded-full border px-2.5 py-1 text-xs ${cats.has(c) ? "border-brand-500 bg-brand-50 text-brand-700" : "border-slate-300 text-slate-600"}`}>{c}</button>
            ))}</div></div>
          <div className="space-y-1 text-sm">
            <label className="flex items-center gap-2"><input type="checkbox" checked={opts.download} onChange={(e) => setOpts({ ...opts, download: e.target.checked })} /> Download original files</label>
            <label className="flex items-center gap-2"><input type="checkbox" checked={opts.guidelines} onChange={(e) => setOpts({ ...opts, guidelines: e.target.checked })} /> Export guidelines (Markdown)</label>
            <label className="flex items-center gap-2"><input type="checkbox" checked={opts.index} onChange={(e) => setOpts({ ...opts, index: e.target.checked })} /> Build AI index (chunks / embeddings)</label>
            <label className="flex items-center gap-2"><input type="checkbox" checked={opts.force} onChange={(e) => setOpts({ ...opts, force: e.target.checked })} /> Re-download everything (otherwise incremental)</label>
          </div>
          <div className="flex gap-2">
            <button className="btn-primary flex-1" disabled={running} onClick={() => run(() => api.exportAll(body()))}>{opts.force ? "Export all (full)" : "Export (incremental)"}</button>
            {running && <button className="btn-danger" onClick={() => run(api.cancel)}>Cancel</button>}
          </div>
          {err && <ErrorBox>{err}</ErrorBox>}
        </section>
      </div>

      <div className="space-y-4">
        <section className="card space-y-3">
          <div className="flex items-center justify-between"><h2 className="font-semibold">Progress</h2>{jobs?.job && <Badge>{running ? "running" : jobs.job.status}</Badge>}</div>
          {progress?.total ? <ProgressBar value={progress.done ?? 0} max={progress.total} label={progress.phase} /> : <div className="text-sm text-slate-500">{running ? `Phase: ${progress?.phase ?? "starting"}…` : "Idle."}</div>}
          {progress?.counts && <div className="text-xs text-slate-500">{Object.entries(progress.counts).filter(([, v]) => v).map(([k, v]) => `${k}: ${v}`).join(" · ")}</div>}
          {progress?.bytes != null && <div className="text-xs text-slate-500">Downloaded {fmtBytes(progress.bytes)} · failed {progress.failed ?? 0}</div>}
        </section>

        <section className="card">
          <h2 className="mb-2 font-semibold">Live logs</h2>
          <div ref={logRef} className="h-72 overflow-auto rounded-lg bg-slate-900 p-3 font-mono text-xs leading-relaxed text-slate-200">
            {logs.length ? logs.map((l) => (
              <div key={l.id} className={l.level === "ERROR" ? "text-rose-300" : l.level === "WARNING" ? "text-amber-300" : ""}>{new Date(l.ts * 1000).toLocaleTimeString()} {l.level.padEnd(7)} {l.message}</div>
            )) : <div className="text-slate-500">Waiting for events…</div>}
          </div>
        </section>

        {report?.totals && (
          <section className="card space-y-3">
            <h2 className="font-semibold">Final report <span className="text-xs font-normal text-slate-500">run #{report.run_id} · {report.duration_seconds}s · {report.status}</span></h2>
            <div className="grid grid-cols-2 gap-3 text-sm md:grid-cols-4">
              {Object.entries(report.totals as Record<string, number>).map(([k, v]) => <div key={k}><div className="label">{k.replace(/_/g, " ")}</div><div className="font-semibold">{k.includes("bytes") ? fmtBytes(v) : v}</div></div>)}
            </div>
            {report.scan?.errors?.length > 0 && <ErrorBox>{report.scan.errors.length} scan error(s): {report.scan.errors.slice(0, 3).map((e: { where: string; error: string }) => `${e.where}: ${e.error}`).join(" | ")}</ErrorBox>}
            {report.knowledge?.embeddings_error && <ErrorBox>Embeddings disabled: {report.knowledge.embeddings_error}</ErrorBox>}
            {failures && (failures.assets.length > 0 || failures.pages.length > 0) && (
              <div>
                <div className="label">Failed / unavailable resources ({failures.assets.length + failures.pages.length})</div>
                <ul className="max-h-48 space-y-1 overflow-auto text-sm">
                  {failures.assets.map((a) => <li key={a.id}><Badge>{a.download_status}</Badge> {a.title} <span className="text-slate-400">— {a.error}</span></li>)}
                  {failures.pages.map((p) => <li key={p.id}><Badge>failed</Badge> page {p.title} <span className="text-slate-400">— {p.error}</span></li>)}
                </ul>
              </div>
            )}
          </section>
        )}
      </div>
    </div>
  );
}
