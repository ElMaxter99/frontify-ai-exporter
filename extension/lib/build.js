// Turns captured pages (+ optionally fetched files) into the same folder layout the Python exporter writes.
import { makeZip } from "./zip.js";

const slug = (s, d = "item") => (s || "").normalize("NFKD").replace(/[^\x00-\x7f]/g, "").replace(/[^a-zA-Z0-9]+/g, "-").replace(/^-+|-+$/g, "").toLowerCase() || d;
const safe = (s, d = "file") => ((s || "").replace(/[<>:"/\\|?*\x00-\x1f]/g, "_").trim().replace(/^\.+/, "").slice(0, 120)) || d;
const enc = (s) => new TextEncoder().encode(s);
const toHex = (css) => { const m = /rgba?\((\d+),\s*(\d+),\s*(\d+)/.exec(css); return m ? "#" + [1, 2, 3].map((i) => (+m[i]).toString(16).padStart(2, "0")).join("").toUpperCase() : null; };
const IMG = /^(png|jpe?g|gif|webp|svg|avif|tiff?|bmp)$/, DOC = /^(pdf|docx?|xlsx?|pptx?|txt|csv|zip|key|indd|idml|json)$/, FONT = /^(ttf|otf|woff2?|eot)$/;
const category = (ext, hint) => FONT.test(ext) ? "fonts" : DOC.test(ext) ? "documents" : /^(mp4|mov|webm)$/.test(ext) ? "videos" : /^(mp3|wav)$/.test(ext) ? "audio"
  : IMG.test(ext || "") ? (/logo|logotype|wordmark|brandmark|emblem/i.test(hint) ? "logos" : /icon|pictogram|glyph/i.test(hint) ? "icons" : /illustrat/i.test(hint) ? "illustrations" : /photo|imagery/i.test(hint) ? "photography" : "images") : "other";
const DIR = { documents: "03_DOCUMENTATION", fonts: "04_DESIGN_SYSTEM/fonts", logos: "02_ASSETS/LOGOS", images: "02_ASSETS/IMAGES", icons: "02_ASSETS/ICONS",
  illustrations: "02_ASSETS/ILLUSTRATIONS", photography: "02_ASSETS/PHOTOGRAPHY", videos: "02_ASSETS/VIDEOS", audio: "02_ASSETS/AUDIO", other: "02_ASSETS/OTHER" };

export function candidates(pages) {
  const out = new Map();
  for (const p of pages) {
    for (const im of p.images) if (!out.has(im.src)) out.set(im.src, { url: im.src, kind: "image", text: im.alt, from: p.url });
    for (const d of p.downloads) if (!out.has(d.href)) out.set(d.href, { url: d.href, kind: "download", text: d.text, from: p.url });
  }
  return [...out.values()];
}

// files: [{url, kind, text, from, status, name, bytes?: Uint8Array, reason?}]
export function buildZip(pages, files, meta) {
  const now = new Date().toISOString(), entries = [];
  const add = (name, data) => entries.push({ name, data: typeof data === "string" ? enc(data) : data });
  const host = meta.host || "portal";
  pages.forEach((p, i) => add(`01_BRAND_GUIDELINES/${String(i + 1).padStart(3, "0")}-${slug(p.title, "page").slice(0, 60)}.md`,
    `---\nsource_url: "${p.url}"\ntitle: "${(p.title || "").replace(/"/g, "'")}"\ncaptured_at: ${p.captured_at}\nmode: extension\n---\n\n${p.markdown || "_Not available (no text found on this page)_"}\n`));

  const done = []; const seen = new Set();
  for (const f of files.filter((x) => x.status === "ok" && x.bytes)) {
    const ext = (f.name.split(".").pop() || "").toLowerCase();
    const cat = category(ext, `${f.text || ""} ${f.name}`);
    let path = `${DIR[cat]}/${f.name}`;
    if (seen.has(path)) path = path.replace(/(\.[^.]*)?$/, (m) => `-${done.length}${m}`);
    seen.add(path); add(path, f.bytes);
    done.push({ path, url: f.url, category: cat, size: f.bytes.length, from_page: f.from });
  }
  const colors = new Map(), hexText = new Set();
  for (const p of pages) {
    for (const s of p.swatches) { const c = colors.get(s.css) || { css: s.css, hex: toHex(s.css), labels: new Set(), pages: new Set() }; if (s.label) c.labels.add(s.label.slice(0, 160)); c.pages.add(p.url); colors.set(s.css, c); }
    for (const m of (p.text_sample + " " + p.markdown).match(/#[0-9a-fA-F]{6}\b/g) || []) hexText.add(m.toUpperCase());
  }
  const colorList = [...colors.values()].map((c) => ({ css: c.css, hex: c.hex, labels: [...c.labels].slice(0, 3), pages: c.pages.size }));
  const fams = {};
  for (const p of pages) { for (const k of ["heading", "body"]) if (p.fonts?.[k]) fams[p.fonts[k]] = (fams[p.fonts[k]] || 0) + 1; for (const f of p.fonts?.loaded || []) fams[f.family] = fams[f.family] || 0; }

  add("05_METADATA/pages.json", JSON.stringify(pages.map((p) => ({ url: p.url, title: p.title, images: p.images.map((i) => i.src), downloads: p.downloads, fonts: p.fonts, captured_at: p.captured_at })), null, 2));
  add("05_METADATA/assets.json", JSON.stringify(files.map(({ bytes, ...r }) => ({ ...r, size: bytes?.length })), null, 2));
  add("05_METADATA/colors.json", JSON.stringify({ swatches_heuristic: colorList, hex_values_in_text: [...hexText].sort() }, null, 2));
  add("05_METADATA/fonts.json", JSON.stringify({ css_font_stacks: fams }, null, 2));
  add("06_AI_KNOWLEDGE/BRAND_GUIDELINES.md", "# Guidelines (extension capture)\n\n" + pages.filter((p) => p.markdown).map((p) => `<!-- source: ${p.url} -->\n${p.markdown}`).join("\n\n---\n\n") + "\n");
  add("06_AI_KNOWLEDGE/VISUAL_IDENTITY.md", [
    "# Visual identity (extension capture)\n",
    "> Read from the pages you opened, not from the API. Colours/fonts are heuristics — verify against the guideline text. Missing data is 'Not available'.\n",
    "## Colours written in the guidelines (HEX)\n", [...hexText].sort().map((h) => `- \`${h}\``).join("\n") || "_Not available_", "",
    "## Colour swatches detected on pages (heuristic)\n", colorList.slice(0, 60).map((c) => `- \`${c.hex || c.css}\` — ${c.labels.join("; ") || "no label"}`).join("\n") || "_Not available_", "",
    "## Fonts\n", Object.keys(fams).map((f) => `- ${f}`).join("\n") || "_Not available_", "",
    "## Downloaded brand files\n", done.map((f) => `- \`${f.path}\` (${f.category}) — from ${f.from_page}`).join("\n") || "_None_", ""].join("\n"));
  add("README_AI.md", `# ${meta.name || host} — capture from ${host} (extension mode)\n\nCaptured ${now} from pages opened by the user in their own browser session.\n\n- \`06_AI_KNOWLEDGE/VISUAL_IDENTITY.md\` and \`BRAND_GUIDELINES.md\`: start here.\n- \`01_BRAND_GUIDELINES/\`: one Markdown per captured page with its source URL.\n- \`05_METADATA/\`: pages, assets, colours, fonts (JSON).\n- \`EXPORT_REPORT.json\`: what was captured, skipped or failed.\n\nRules: use only values found here; if something is "Not available", say so and ask; never invent colours, fonts or rules.\n`);
  add("EXPORT_REPORT.json", JSON.stringify({ mode: "extension", host, generated_at: now,
    summary: { pages_captured: pages.length, files_downloaded: done.length, files_failed_or_skipped: files.filter((f) => f.status !== "ok").length },
    files: files.filter((f) => f.status !== "ok").map(({ bytes, ...r }) => r),
    limitations: ["Only pages the user opened/captured are included; pages never visited are not.", "Colours/fonts come from rendered elements (heuristic).", "Font files and structured Frontify metadata (tags, custom fields) are not captured.", "Original files only exist where the portal exposes a downloadable link for this user."] }, null, 2));
  return makeZip(entries);
}

export const nameFor = (url, disposition, ctype) => {
  const m = /filename\*?=(?:UTF-8'')?"?([^";]+)/i.exec(disposition || "");
  let n = safe(decodeURIComponent(m ? m[1] : new URL(url).pathname.split("/").pop() || "file"));
  if (!n.includes(".")) n += { "image/png": ".png", "image/jpeg": ".jpg", "image/svg+xml": ".svg", "image/webp": ".webp", "application/pdf": ".pdf" }[ctype] || "";
  return n;
};
