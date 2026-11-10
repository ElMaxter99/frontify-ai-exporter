import { useEffect, useState } from "react";
import { api, Settings } from "../api";
import { ErrorBox } from "../components/ui";

const Field = ({ label, children, hint }: { label: string; children: React.ReactNode; hint?: string }) => (
  <label className="block"><span className="label">{label}</span>{children}{hint && <span className="mt-1 block text-xs text-slate-500">{hint}</span>}</label>
);

export default function SettingsPage() {
  const [s, setS] = useState<Settings | null>(null);
  const [token, setToken] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => { api.settings().then(setS).catch((e: Error) => setErr(e.message)); }, []);
  if (err) return <ErrorBox>{err}</ErrorBox>;
  if (!s) return null;
  const set = <K extends keyof Settings>(k: K, v: Settings[K]) => setS({ ...s, [k]: v });

  const save = async () => {
    setErr(null);
    try {
      const { has_token, token_source, has_openai_key, ...values } = s; void has_token; void token_source; void has_openai_key;
      setS(await api.saveSettings(values, token || undefined));
      setToken("");
      setMsg("Saved.");
    } catch (e) { setErr((e as Error).message); }
  };
  const test = async () => {
    const r = await api.test();
    setMsg(r.ok ? `✔ Connected as ${r.user ?? "token user"} — brands: ${r.brands?.map((b) => b.name).join(", ") || "none"}` : `✘ ${r.error}`);
  };

  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <section className="card space-y-4">
        <h2 className="font-semibold">Frontify connection</h2>
        <Field label="Frontify domain" hint="e.g. acme.frontify.com"><input className="input" value={s.frontify_domain} onChange={(e) => set("frontify_domain", e.target.value)} /></Field>
        <Field label="Access token (session only)" hint={`Token source: ${s.token_source}. Recommended: set FRONTIFY_TOKEN in .env. A token typed here lives only in server memory, is never stored or sent back to the browser.`}>
          <input className="input" type="password" autoComplete="off" placeholder={s.has_token ? "•••••••• (configured)" : "paste token"} value={token} onChange={(e) => setToken(e.target.value)} />
        </Field>
        <Field label="Destination folder" hint="Inside the container (docker-compose mounts ./exports)."><input className="input" value={s.export_dir} onChange={(e) => set("export_dir", e.target.value)} /></Field>
      </section>

      <section className="card space-y-4">
        <h2 className="font-semibold">Export</h2>
        <div className="grid grid-cols-3 gap-3">
          <Field label="Download threads"><input className="input" type="number" min={1} max={32} value={s.download_concurrency} onChange={(e) => set("download_concurrency", +e.target.value)} /></Field>
          <Field label="API concurrency"><input className="input" type="number" min={1} max={16} value={s.api_concurrency} onChange={(e) => set("api_concurrency", +e.target.value)} /></Field>
          <Field label="Page size"><input className="input" type="number" min={1} max={100} value={s.page_size} onChange={(e) => set("page_size", +e.target.value)} /></Field>
        </div>
        <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={s.include_related_assets} onChange={(e) => set("include_related_assets", e.target.checked)} /> Fetch related-asset relationships (1 extra request per 25 assets)</label>
        <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={s.dedupe_hardlinks} onChange={(e) => set("dedupe_hardlinks", e.target.checked)} /> Replace duplicate files with hard links (saves disk; originals unchanged)</label>
      </section>

      <section className="card space-y-4 lg:col-span-2">
        <h2 className="font-semibold">AI preparation</h2>
        <div className="grid gap-3 md:grid-cols-4">
          <Field label="Embeddings">
            <select className="input" value={s.embeddings_provider} onChange={(e) => set("embeddings_provider", e.target.value)}>
              <option value="none">None (lexical search only)</option><option value="openai">OpenAI</option><option value="local">Local (sentence-transformers)</option>
            </select>
          </Field>
          <Field label="Embedding model" hint="blank = provider default"><input className="input" value={s.embeddings_model} onChange={(e) => set("embeddings_model", e.target.value)} /></Field>
          <Field label="Vector store">
            <select className="input" value={s.vector_store} onChange={(e) => set("vector_store", e.target.value)}>
              <option value="sqlite">SQLite (built-in)</option><option value="chroma">ChromaDB</option><option value="faiss">FAISS</option><option value="qdrant">Qdrant</option>
            </select>
          </Field>
          <Field label="Qdrant URL"><input className="input" value={s.qdrant_url} onChange={(e) => set("qdrant_url", e.target.value)} /></Field>
        </div>
        <div className="text-xs text-slate-500">OpenAI key: {s.has_openai_key ? "configured via OPENAI_API_KEY" : "not set (OPENAI_API_KEY in .env)"}. Chroma/FAISS/Qdrant/local embeddings need their optional packages (see docs).</div>
        <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={s.ocr_enabled} onChange={(e) => set("ocr_enabled", e.target.checked)} /> OCR for images with text (requires pytesseract + tesseract)</label>
      </section>

      <div className="flex items-center gap-3 lg:col-span-2">
        <button className="btn-primary" onClick={save}>Save settings</button>
        <button className="btn-secondary" onClick={test}>Test connection</button>
        {msg && <span className="text-sm text-slate-700">{msg}</span>}
      </div>
    </div>
  );
}
