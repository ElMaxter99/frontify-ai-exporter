"""Generate the human/AI readable knowledge files per brand from REAL exported data only.
Nothing is invented: when Frontify has no data for a topic the file says so."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from src.ai.chunking import strip_front_matter
from src.database.db import Database
from src.exporter.layout import Layout
from src.utils.files import human_size, utcnow_iso, write_text

TOPICS: dict[str, list[str]] = {
    "visual_identity": ["logo", "identity", "identidad", "visual", "imagery", "image", "photo", "fotograf", "icon", "iconograf",
                        "illustration", "ilustra", "layout", "grid", "symbol", "mark", "marca", "design", "diseño", "editorial", "digital"],
    "typography": ["typograph", "tipograf", "font", "fuente", "typeface", "type "],
    "colors": ["color", "colour", "palette", "paleta"],
    "tone_of_voice": ["tone", "voice", "tono", "voz", "messag", "mensaje", "writing", "copy", "communicat", "comunicaci", "language", "lenguaje", "naming", "slogan", "claim"],
}


def _load(raw: str | None) -> Any:
    try:
        return json.loads(raw) if raw else None
    except ValueError:
        return None


def page_matches(page: dict[str, Any], topic: str) -> bool:
    hay = f"{page.get('path') or ''}".lower()
    return any(k in hay for k in TOPICS[topic])


def read_page_md(page: dict[str, Any]) -> str | None:
    p = page.get("markdown_path")
    if p and Path(p).exists():
        return strip_front_matter(Path(p).read_text("utf-8"))
    return None


def render_colors(ess: dict[str, Any] | None) -> str | None:
    palettes = ((ess or {}).get("colorPalettes") or {}).get("items") or []
    if not palettes:
        return None
    out = []
    for pal in palettes:
        out.append(f"### {pal.get('name')}")
        if pal.get("description"):
            out.append(pal["description"])
        out.append("\n| Color | HEX | Pantone | Pantone Coated | Pantone Uncoated | Description |\n|---|---|---|---|---|---|")
        for c in ((pal.get("colors") or {}).get("items")) or []:
            rep = c.get("representations") or {}
            vals = [((rep.get(k) or {}).get("value")) or "" for k in ("hex", "pantone", "pantoneCoated", "pantoneUncoated")]
            desc = (c.get("description") or "").replace("\n", " ")
            out.append(f"| {c.get('name')} | " + " | ".join(vals) + f" | {desc} |")
        out.append("")
    return "\n".join(out)


def render_fonts(ess: dict[str, Any] | None) -> str | None:
    fams = ((ess or {}).get("fontFamilies") or {}).get("items") or []
    if not fams:
        return None
    out = []
    for f in fams:
        styles = ", ".join(f"{s['name']} ({s['weight']}{', italic' if s.get('isItalic') else ''})" for s in f.get("fontStyles") or [])
        out.append(f"- **{f.get('name')}** — CSS name `{f.get('cssName')}`, provider: {f.get('provider')}" + (f"; styles: {styles}" if styles else ""))
    return "\n".join(out)


def _header(title: str, brand: dict[str, Any], note: str = "") -> str:
    return (f"---\ntitle: {json.dumps(title)}\nbrand: {json.dumps(brand['name'])}\nbrand_id: {json.dumps(brand['id'])}\n"
            f"generated_at: {utcnow_iso()}\nsource: frontify-export\n---\n\n# {title} — {brand['name']}\n\n{note}")


def build_knowledge(db: Database, layout: Layout, brand_id: str, domain: str = "") -> dict[str, str]:
    brand = db.one("SELECT * FROM brands WHERE id=?", (brand_id,))
    if not brand:
        return {}
    kdir = layout.brand_dir(brand_id) / "knowledge"
    pages = db.query("SELECT * FROM guideline_pages WHERE brand_id=? AND status='active' ORDER BY guideline_id, path", (brand_id,))
    content_pages = [p for p in pages if p["markdown_path"]]
    ess_row = db.one("SELECT raw FROM essentials WHERE brand_id=?", (brand_id,))
    ess = _load(ess_row["raw"]) if ess_row else None
    stats = db.one("""SELECT count(*) n, coalesce(sum(size),0) bytes, sum(download_status='done') done FROM assets
                      WHERE brand_id=? AND status='active'""", (brand_id,)) or {}
    cats = db.query("SELECT category, count(*) n FROM assets WHERE brand_id=? AND status='active' GROUP BY category ORDER BY n DESC", (brand_id,))
    containers = db.query("SELECT kind,name,expected_assets FROM containers WHERE brand_id=? AND status='active' ORDER BY kind,name", (brand_id,))
    guidelines = [p for p in pages if p["kind"] == "Guideline"]
    files: dict[str, str] = {}

    # brand_context.md --------------------------------------------------------
    ctx = [_header("Brand context", brand, "Overview of what exists in this Frontify brand. Facts only; see the other files for detail.\n")]
    ctx.append(f"- Frontify brand ID: `{brand['id']}`" + (f"\n- Frontify domain: `{domain}`" if domain else ""))
    ctx.append(f"- Assets: {stats.get('n', 0)} ({human_size(stats.get('bytes'))}), downloaded originals: {stats.get('done') or 0}")
    ctx.append("- Asset categories: " + (", ".join(f"{c['category']} ({c['n']})" for c in cats) or "none"))
    ctx.append("\n## Libraries and workspaces\n")
    ctx += [f"- {c['kind']}: **{c['name']}**" + (f" ({c['expected_assets']} assets)" if c["expected_assets"] is not None else "") for c in containers] or ["- none found"]
    ctx.append("\n## Brand guidelines\n")
    ctx += [f"- **{g['title']}** — {g['url'] or 'no url'} ({sum(1 for p in content_pages if p['guideline_id'] == g['id'])} exported pages)" for g in guidelines] or ["- No guidelines are accessible with this token."]
    files["brand_context.md"] = "\n".join(ctx) + "\n"

    # brand_guidelines.md -----------------------------------------------------
    bg = [_header("Brand guidelines (complete)", brand, "All exported guideline pages in Frontify navigation order.\n")]
    if not content_pages:
        bg.append("_No guideline page content was exported (none accessible, or not yet exported)._")
    for p in content_pages:
        depth = p["path"].count("/")
        body = read_page_md(p) or ""
        body = re.sub(r"^# .*\n", "", body, count=1)
        bg.append(f"\n{'#' * min(2 + max(depth - 1, 0), 5)} {p['title']}\n\n*Source: {p['url'] or p['id']} — path: {p['path']}*\n\n{body.strip()}")
    files["brand_guidelines.md"] = "\n".join(bg) + "\n"

    # topic files -------------------------------------------------------------
    colors_md = render_colors(ess)
    fonts_md = render_fonts(ess)
    extra = {"colors": colors_md and "## Color palettes (Brand Essentials)\n\n" + colors_md,
             "typography": fonts_md and "## Font families (Brand Essentials)\n\n" + fonts_md}
    labels = {"visual_identity": "Visual identity", "typography": "Typography", "colors": "Colors", "tone_of_voice": "Tone of voice"}
    for topic, label in labels.items():
        sec = [_header(label, brand, f"Guideline pages whose navigation path matches: {', '.join(k.strip() for k in TOPICS[topic])}.\n")]
        if extra.get(topic):
            sec.append(str(extra[topic]))
        matched = [p for p in content_pages if page_matches(p, topic)]
        for p in matched:
            body = re.sub(r"^# .*\n", "", read_page_md(p) or "", count=1).strip()
            sec.append(f"\n## {p['title']}\n\n*Source: {p['url'] or p['id']}*\n\n{body}")
        if not extra.get(topic) and not matched:
            sec.append(f"_Frontify returned no {label.lower()} data for this brand (no matching Brand Essentials or guideline pages)._")
        files[f"{topic}.md"] = "\n".join(sec) + "\n"

    # complete_index.md ---------------------------------------------------------
    idx = [_header("Complete index", brand, "Every guideline page and asset known for this brand, with local paths.\n")]
    idx.append("## Guideline pages\n")
    for p in pages:
        indent = "  " * p["path"].count("/")
        link = f"[{p['title']}](../guidelines/markdown/{Path(p['markdown_path']).relative_to(layout.brand_dir(brand_id) / 'guidelines' / 'markdown').as_posix()})" if p["markdown_path"] and Path(p["markdown_path"]).exists() else (p["title"] or "")
        idx.append(f"{indent}- {link} · `{p['kind']}` · `{p['id']}`")
    if not pages:
        idx.append("- none")
    idx.append("\n## Assets\n")
    cur = None
    for a in db.query("SELECT * FROM assets WHERE brand_id=? AND status='active' ORDER BY folder_path, title", (brand_id,)):
        if a["folder_path"] != cur:
            cur = a["folder_path"]
            idx.append(f"\n### {cur}\n")
        loc = ""
        if a["local_path"]:
            loc = f" → `{layout.rel(Path(a['local_path']))}`"
        elif a["download_status"] != "done":
            loc = f" _({a['download_status']})_"
        idx.append(f"- {a['title']} · `{a['extension'] or ''}` · {human_size(a['size'])} · id `{a['id']}`{loc}")
    files["complete_index.md"] = "\n".join(idx) + "\n"

    for name, text in files.items():
        write_text(kdir / name, text)
    return files
