import { useState } from "react";
import { Link } from "react-router-dom";
import { api, fmtBytes, fmtDate, SyncRun, useEvents, usePoll } from "../api";
import { Badge, Empty, ErrorBox, ProgressBar, Stat } from "../components/ui";

function changeSummary(c: SyncRun["changes"]) {
  const parts: string[] = [];
  for (const [entity, kinds] of Object.entries(c)) {
    for (const [k, n] of Object.entries(kinds)) if (k !== "unchanged") parts.push(`${n} ${entity} ${k}`);
  }
  return parts.join(", ") || "no changes";
}

export default function Dashboard() {
  const { data: d, error } = usePoll(api.dashboard, 2000);
  const { data: runs } = usePoll(api.syncHistory, 5000);
  const { progress } = useEvents();
  const [conn, setConn] = useState<string | null>(null);
  const p = progress ?? d?.progress ?? null;

  const test = async () => {
    const r = await api.test();
    setConn(r.ok ? `Connected as ${r.user ?? "token user"} · ${r.brands?.length ?? 0} brand(s) accessible` : `Failed: ${r.error}`);
  };

  if (error) return <ErrorBox>Cannot reach the API: {error}</ErrorBox>;
  if (!d) return <Empty>Loading…</Empty>;
  return (
    <div className="space-y-6">
      <div className="card flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="label">Frontify connection</div>
          <div className="flex items-center gap-2">
            <span className={`h-2.5 w-2.5 rounded-full ${d.configured ? "bg-emerald-500" : "bg-amber-500"}`} />
            <span className="font-medium">{d.configured ? d.domain : "Not configured"}</span>
          </div>
          {conn && <div className="mt-1 text-sm text-slate-600">{conn}</div>}
          {!d.configured && <div className="mt-1 text-sm text-slate-600">Set <code>FRONTIFY_DOMAIN</code> and <code>FRONTIFY_TOKEN</code> in <code>.env</code>, then reopen — or go to <Link className="text-brand-600 underline" to="/settings">Settings</Link>.</div>}
        </div>
        <div className="flex gap-2">
          <button className="btn-secondary" onClick={test} disabled={!d.configured}>Test connection</button>
          <Link className="btn-primary" to="/export">Scan / Export</Link>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <Stat label="Brands" value={d.brands} />
        <Stat label="Assets found" value={d.assets} hint={`${d.downloaded} downloaded · ${d.pending} pending`} />
        <Stat label="Documents" value={d.documents} hint={`${d.guideline_pages} guideline pages`} />
        <Stat label="Total size" value={fmtBytes(d.total_bytes)} hint="as reported by Frontify" />
        <Stat label="Failed" value={d.failed} hint={`${d.unavailable} unavailable (protected)`} />
        <Stat label="Removed / inaccessible" value={d.deleted_assets} />
        <Stat label="AI chunks" value={d.chunks} hint="searchable knowledge fragments" />
        <Stat label="Last sync" value={d.last_sync ? <span className="text-base">{fmtDate(d.last_sync.finished_at)}</span> : "never"} hint={d.last_sync?.kind} />
      </div>

      <div className="card space-y-3">
        <div className="flex items-center justify-between">
          <div className="font-semibold">Export progress</div>
          {d.job.job && <Badge>{d.job.running ? "running" : d.job.job.status}</Badge>}
        </div>
        {p && d.job.running ? (
          <>
            <div className="text-sm text-slate-600">Phase: <b>{p.phase}</b>{p.path ? ` · ${p.path}` : ""}</div>
            {p.total ? <ProgressBar value={p.done ?? 0} max={p.total} label={p.phase} /> : null}
          </>
        ) : <div className="text-sm text-slate-500">No job running.</div>}
      </div>

      <div className="card">
        <div className="mb-3 font-semibold">Sync history</div>
        {!runs?.length ? <Empty>No synchronisations yet.</Empty> : (
          <table className="w-full text-left text-sm">
            <thead className="text-xs uppercase text-slate-500"><tr><th className="py-2">#</th><th>Type</th><th>Started</th><th>Status</th><th>Changes</th></tr></thead>
            <tbody>{runs.map((r) => (
              <tr key={r.id} className="border-t border-slate-100"><td className="py-2">{r.id}</td><td>{r.kind}</td><td>{fmtDate(r.started_at)}</td><td><Badge>{r.status}</Badge></td><td className="text-slate-600">{changeSummary(r.changes)}</td></tr>
            ))}</tbody>
          </table>
        )}
      </div>
    </div>
  );
}
