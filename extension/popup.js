import { getPages, clearPages } from "./lib/store.js";
import { buildZip, candidates, nameFor } from "./lib/build.js";

const $ = (id) => document.getElementById(id);
const log = (t) => { $("log").textContent = t; };
const qTab = new URLSearchParams(location.search).get("tab"); // test hook: operate on a given tab id
let tab;

async function refresh() {
  const pages = await getPages();
  $("count").textContent = `${pages.length} página${pages.length === 1 ? "" : "s"} capturada${pages.length === 1 ? "" : "s"}`;
  $("list").replaceChildren(...pages.slice(-8).reverse().map((p) => Object.assign(document.createElement("li"), { textContent: p.title })));
  $("exp").disabled = $("clr").disabled = !pages.length;
}

async function init() {
  tab = qTab ? await chrome.tabs.get(+qTab) : (await chrome.tabs.query({ active: true, currentWindow: true }))[0];
  const ok = /^https?:/.test(tab?.url || "");
  $("site").textContent = ok ? new URL(tab.url).host : "Abre una página web";
  $("cap").disabled = !ok;
  const { autoOrigins = [] } = await chrome.storage.local.get("autoOrigins");
  $("auto").checked = ok && autoOrigins.includes(new URL(tab.url).origin);
  $("auto").disabled = !ok;
  await refresh();
}

$("cap").onclick = async () => {
  $("cap").disabled = true; log("Capturando…");
  const r = await chrome.runtime.sendMessage({ type: "capture", tabId: tab.id });
  log(r.ok ? `✓ ${r.title}` : `✗ ${r.error}`); $("cap").disabled = false; await refresh();
};

$("auto").onchange = async (e) => {
  const origin = new URL(tab.url).origin;
  let { autoOrigins = [] } = await chrome.storage.local.get("autoOrigins");
  if (e.target.checked) {
    const granted = (await chrome.permissions.contains({ origins: [origin + "/*"] })) || (await chrome.permissions.request({ origins: [origin + "/*"] }));
    if (!granted) { e.target.checked = false; return log("Permiso denegado."); }
    autoOrigins = [...new Set([...autoOrigins, origin])];
  } else autoOrigins = autoOrigins.filter((o) => o !== origin);
  await chrome.storage.local.set({ autoOrigins });
  log(e.target.checked ? "Auto-captura activada para este sitio." : "Auto-captura desactivada.");
};

$("exp").onclick = async () => {
  $("exp").disabled = true;
  const pages = await getPages(), files = [];
  if ($("files").checked) {
    const list = candidates(pages), delay = Math.max(0, +$("delay").value || 0) * 1000;
    const origins = [...new Set(list.map((c) => new URL(c.url).origin + "/*"))];
    if (!(await chrome.permissions.contains({ origins })) && !(await chrome.permissions.request({ origins }))) log("Sin permiso para algunos orígenes: esos archivos se omitirán.");
    let i = 0;
    for (const c of list) {
      log(`Descargando ${++i}/${list.length}…`);
      try {
        const r = await fetch(c.url, { credentials: "include" });
        const ctype = (r.headers.get("content-type") || "").split(";")[0].trim().toLowerCase();
        if (!r.ok || (c.kind === "download" && ctype.startsWith("text/html"))) { files.push({ ...c, status: "skipped", reason: `HTTP ${r.status} ${ctype}` }); continue; }
        const bytes = new Uint8Array(await r.arrayBuffer());
        if (bytes.length > 200 * 1024 * 1024) { files.push({ ...c, status: "skipped", reason: "larger than 200 MB" }); continue; }
        files.push({ ...c, status: "ok", bytes, name: nameFor(c.url, r.headers.get("content-disposition"), ctype) });
      } catch (err) { files.push({ ...c, status: "failed", reason: String(err.message || err) }); }
      if (delay) await new Promise((res) => setTimeout(res, delay));
    }
  }
  const host = new URL(pages[0].url).host;
  const blob = buildZip(pages, files, { host, name: host.split(".")[0] });
  const a = Object.assign(document.createElement("a"), { href: URL.createObjectURL(blob), download: `${host.split(".")[0]}_frontify_capture.zip` });
  a.click(); log(`✓ ZIP generado (${pages.length} páginas, ${files.filter((f) => f.status === "ok").length} archivos)`); $("exp").disabled = false;
};

$("clr").onclick = async () => { await clearPages(); log("Captura borrada."); await refresh(); };
init();
