import { useState } from "react";
import { api, Brand, SearchHit, usePoll } from "../api";
import { Empty } from "../components/ui";

export default function SearchPage() {
  const { data: brands } = usePoll<Brand[]>(api.brands, 0);
  const [q, setQ] = useState(""); const [brand, setBrand] = useState("");
  const [hits, setHits] = useState<SearchHit[] | null>(null);
  const go = async (e: React.FormEvent) => { e.preventDefault(); if (q.trim()) setHits((await api.search(q, brand || undefined)).results); };
  return (
    <div className="space-y-4">
      <form onSubmit={go} className="card flex flex-wrap gap-3">
        <input className="input flex-1" placeholder="Ask your brand knowledge base (e.g. “logo clear space”)" value={q} onChange={(e) => setQ(e.target.value)} />
        <select className="input w-52" value={brand} onChange={(e) => setBrand(e.target.value)}><option value="">All brands</option>{brands?.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}</select>
        <button className="btn-primary">Search</button>
      </form>
      {hits && !hits.length && <Empty>No results. Run an export with “Build AI index” enabled first.</Empty>}
      {hits?.map((h) => (
        <div key={h.id} className="card space-y-2">
          <div className="flex flex-wrap items-center gap-2 text-xs text-slate-500">
            <b className="text-slate-800">{String(h.metadata.title ?? "")}</b><span>{String(h.metadata.brand)}</span><span>· {String(h.metadata.kind)}</span><span>· {String(h.metadata.folder ?? "")}</span><span className="ml-auto">{h.mode} · {h.score}</span>
          </div>
          <p className="whitespace-pre-wrap text-sm">{h.text.slice(0, 700)}</p>
          <div className="text-xs text-slate-400">Frontify id {String(h.metadata.frontify_id)} · file {String(h.metadata.source_file ?? "—")} · extracted {String(h.metadata.extracted_at)}</div>
        </div>
      ))}
    </div>
  );
}
