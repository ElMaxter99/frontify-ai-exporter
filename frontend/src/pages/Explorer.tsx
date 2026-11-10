import { useEffect, useMemo, useState } from "react";
import { api, Asset, Brand, fmtBytes, fmtDate, Tree, usePoll } from "../api";
import { Badge, Empty } from "../components/ui";

const CATS = ["", "images", "logos", "icons", "videos", "audio", "documents", "fonts", "other"];

function guidelineTree(g: Tree["guidelines"]) {
  const kids = new Map<string | null, Tree["guidelines"]>();
  g.forEach((p) => kids.set(p.parent_id, [...(kids.get(p.parent_id) ?? []), p]));
  kids.forEach((v) => v.sort((a, b) => a.position - b.position));
  return kids;
}

export default function Explorer() {
  const { data: brands } = usePoll(api.brands, 0);
  const [brand, setBrand] = useState<Brand | null>(null);
  const [tree, setTree] = useState<Tree | null>(null);
  const [folder, setFolder] = useState<string>("");
  const [container, setContainer] = useState<string>("");
  const [cat, setCat] = useState(""); const [status, setStatus] = useState(""); const [q, setQ] = useState("");
  const [assets, setAssets] = useState<{ total: number; items: Asset[] } | null>(null);
  const [detail, setDetail] = useState<Record<string, unknown> | null>(null);
  const [page, setPage] = useState<{ title: string; markdown: string | null; url: string | null } | null>(null);

  useEffect(() => { if (!brand && brands?.length) setBrand(brands[0]); }, [brands, brand]);
  useEffect(() => { if (brand) api.tree(brand.id).then(setTree); setFolder(""); setContainer(""); }, [brand]);
  useEffect(() => {
    if (!brand) return;
    const p: Record<string, string> = { brand_id: brand.id, limit: "200" };
    if (folder) p.folder_id = folder; else if (container) p.container_id = container;
    if (cat) p.category = cat; if (status) p.status = status; if (q) p.q = q;
    api.assets(p).then(setAssets);
  }, [brand, folder, container, cat, status, q]);

  const gKids = useMemo(() => guidelineTree(tree?.guidelines ?? []), [tree]);
  const folderKids = useMemo(() => {
    const m = new Map<string, Tree["folders"]>();
    tree?.folders.forEach((f) => m.set(f.parent_id ?? `c:${f.container_id}`, [...(m.get(f.parent_id ?? `c:${f.container_id}`) ?? []), f]));
    return m;
  }, [tree]);

  const renderFolders = (key: string, depth: number): React.ReactNode =>
    (folderKids.get(key) ?? []).map((f) => (
      <div key={f.id}>
        <button className={`block w-full truncate rounded px-2 py-1 text-left text-sm hover:bg-slate-100 ${folder === f.id ? "bg-brand-50 font-medium" : ""}`} style={{ paddingLeft: 8 + depth * 14 }} onClick={() => { setFolder(f.id); setContainer(""); }}>📁 {f.name}</button>
        {renderFolders(f.id, depth + 1)}
      </div>
    ));
  const renderG = (parent: string | null, depth: number): React.ReactNode =>
    (gKids.get(parent) ?? []).map((p) => (
      <div key={p.id}>
        <button className="block w-full truncate rounded px-2 py-1 text-left text-sm hover:bg-slate-100" style={{ paddingLeft: 8 + depth * 14 }}
          onClick={() => ["DocumentPage", "CoverPage", "DocumentLibrary"].includes(p.kind) && api.guideline(p.id).then(setPage)}>
          📄 {p.title} <span className="text-xs text-slate-400">{p.kind === "Guideline" ? "" : p.kind}</span>
        </button>
        {renderG(p.id, depth + 1)}
      </div>
    ));

  if (!brands) return null;
  if (!brands.length) return <Empty>No brands yet. Run a scan from the Export page.</Empty>;

  return (
    <div className="grid gap-4 lg:grid-cols-[18rem_1fr]">
      <aside className="card max-h-[75vh] space-y-3 overflow-auto">
        <select className="input" value={brand?.id} onChange={(e) => setBrand(brands.find((b) => b.id === e.target.value) ?? null)}>
          {brands.map((b) => <option key={b.id} value={b.id}>{b.name} ({b.assets})</option>)}
        </select>
        <div className="label">Libraries & folders</div>
        <button className="block w-full rounded px-2 py-1 text-left text-sm hover:bg-slate-100" onClick={() => { setFolder(""); setContainer(""); }}>All assets</button>
        {tree?.containers.map((c) => (
          <div key={c.id}>
            <button className={`block w-full truncate rounded px-2 py-1 text-left text-sm font-medium hover:bg-slate-100 ${container === c.id && !folder ? "bg-brand-50" : ""}`} onClick={() => { setContainer(c.id); setFolder(""); }}>
              🗂 {c.name} <span className="text-xs text-slate-400">{c.kind}{c.scan_complete ? "" : " · incomplete scan"}</span>
            </button>
            {renderFolders(`c:${c.id}`, 1)}
          </div>
        ))}
        <div className="label pt-2">Guidelines</div>
        {tree?.guidelines.length ? renderG(null, 0) : <div className="text-sm text-slate-500">None accessible.</div>}
      </aside>

      <section className="space-y-3">
        {page ? (
          <div className="card">
            <div className="mb-2 flex items-center justify-between"><h2 className="font-semibold">{page.title}</h2><button className="btn-secondary" onClick={() => setPage(null)}>Close</button></div>
            <pre className="max-h-[65vh] overflow-auto whitespace-pre-wrap rounded-lg bg-slate-50 p-3 text-sm">{page.markdown ?? "Not exported yet."}</pre>
          </div>
        ) : (
          <>
            <div className="card flex flex-wrap gap-3">
              <input className="input max-w-xs" placeholder="Search by name…" value={q} onChange={(e) => setQ(e.target.value)} />
              <select className="input w-40" value={cat} onChange={(e) => setCat(e.target.value)}>{CATS.map((c) => <option key={c} value={c}>{c || "All categories"}</option>)}</select>
              <select className="input w-40" value={status} onChange={(e) => setStatus(e.target.value)}>{["", "done", "pending", "failed", "unavailable"].map((c) => <option key={c} value={c}>{c || "Any status"}</option>)}</select>
              <div className="ml-auto self-center text-sm text-slate-500">{assets?.total ?? 0} assets</div>
            </div>
            <div className="card overflow-auto p-0">
              <table className="w-full text-left text-sm">
                <thead className="bg-slate-50 text-xs uppercase text-slate-500"><tr><th className="p-3">Name</th><th>Folder</th><th>Type</th><th>Size</th><th>Modified</th><th>Status</th></tr></thead>
                <tbody>{assets?.items.map((a) => (
                  <tr key={a.id} className="cursor-pointer border-t border-slate-100 hover:bg-slate-50" onClick={() => api.asset(a.id).then(setDetail)}>
                    <td className="p-3 font-medium">{a.title}</td><td className="max-w-[16rem] truncate text-slate-500">{a.folder_path}</td>
                    <td>{a.category}{a.extension ? ` · ${a.extension}` : ""}</td><td>{fmtBytes(a.size)}</td><td>{fmtDate(a.modified_at)}</td>
                    <td><Badge>{a.download_status}</Badge></td>
                  </tr>
                ))}</tbody>
              </table>
              {assets && !assets.items.length && <div className="p-6"><Empty>No assets match.</Empty></div>}
            </div>
          </>
        )}
        {detail && (
          <div className="card">
            <div className="mb-2 flex items-center justify-between"><h2 className="font-semibold">Asset metadata</h2><button className="btn-secondary" onClick={() => setDetail(null)}>Close</button></div>
            <pre className="max-h-96 overflow-auto rounded-lg bg-slate-50 p-3 text-xs">{JSON.stringify(detail, null, 2)}</pre>
          </div>
        )}
      </section>
    </div>
  );
}
