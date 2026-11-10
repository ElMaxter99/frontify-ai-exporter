from __future__ import annotations

from src.ai.chunking import chunk_markdown, chunk_plain, strip_front_matter
from src.assets.classify import category_for, mime_for
from src.config import RuntimeConfig, Settings, normalize_domain
from src.guidelines.markdown import render_block, render_page
from src.utils.files import safe_name, slugify


def test_category_for():
    assert category_for("svg", "Logos/Primary") == "logos"
    assert category_for("svg", "Icons/UI") == "icons"
    assert category_for("svg", "Logos/Primary", "Icon Set") == "icons"
    assert category_for("png", "Photos") == "images"
    assert category_for("mp4") == "videos"
    assert category_for("pdf") == "documents"
    assert category_for("mp3") == "audio"
    assert category_for("xyz") == "other"
    assert mime_for("a.webp", "webp") == "image/webp"


def test_names():
    assert slugify("Acme Corp, Inc.") == "acme-corp-inc"
    assert safe_name('a/b:c?.png') == "a_b_c_.png"
    assert safe_name("") == "unnamed"


def test_domain_and_runtime_config_hide_secrets():
    assert normalize_domain("https://Acme.Frontify.com/x") == "acme.frontify.com"
    cfg = RuntimeConfig(Settings(_env_file=None, frontify_token="tok123456"))
    pub = cfg.public()
    assert "tok123456" not in str(pub) and pub["has_token"] is True
    cfg.set_overrides({"download_concurrency": "9", "evil_key": "x", "frontify_domain": "https://x.frontify.com/"})
    assert cfg.get("download_concurrency") == 9 and cfg.domain == "x.frontify.com" and "evil_key" not in cfg.overrides


def test_chunking_keeps_heading_breadcrumb_and_provenance():
    md = "---\nx: 1\n---\n# Title\n\nintro\n\n## Logo\n\n" + "word " * 800 + "\n\n## Color\n\nRed"
    chunks = chunk_markdown(md, {"frontify_id": "p1"}, size=1000, overlap=100)
    assert len(chunks) >= 3 and all(c.metadata["frontify_id"] == "p1" for c in chunks)
    assert chunks[0].text.startswith("Title") and any("Title > Logo" == c.metadata["heading_path"] for c in chunks)
    assert chunks[-1].text.endswith("Red") and chunks[-1].metadata["chunk_count"] == len(chunks)
    assert strip_front_matter(md).startswith("# Title")
    assert chunk_plain("", {}) == []


def test_markdown_render_has_text_headings_and_raw_settings_fallback():
    page = {"id": "p", "title": "T", "url": "u", "modifiedAt": "m"}
    secs = [[{"__typename": "GuidelinePageHeading", "id": "h", "title": "Sub"},
             {"__typename": "GuidelinePageBlock", "id": "b", "content": "Hello", "type": {"name": "Text"}},
             {"__typename": "X", "id": "c", "content": None, "settings": {"k": "v"}, "type": {"name": "Color"}}]]
    md = render_page(page, secs, brand="Acme", brand_id="b1", path="G/T", extracted_at="now")
    assert "# T" in md and "## Sub" in md and "Hello" in md and '"k": "v"' in md and 'frontify_id: "p"' in md
    assert "block id=b" in render_block({"id": "b", "content": "x", "type": {"name": "Text"}})
