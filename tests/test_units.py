# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from src.assets.classify import category_for, mime_for
from src.config import normalize_domain
from src.guidelines.markdown import render_block, render_page, strip_front_matter
from src.utils.files import safe_name, slugify


def test_category_for():
    assert category_for("svg", "Logos/Primary") == "logos"
    assert category_for("svg", "Icons/UI") == "icons"
    assert category_for("svg", "Logos/Primary", "Icon Set") == "icons"
    assert category_for("jpg", "Brand/Photography") == "photography"
    assert category_for("png", "x", "Hero illustration") == "illustrations"
    assert category_for("png", "Misc") == "images"
    assert category_for("mp4") == "videos" and category_for("pdf") == "documents" and category_for("ttf") == "fonts"
    assert category_for("xyz") == "other" and mime_for("a.webp", "webp") == "image/webp"


def test_names_and_domain():
    assert slugify("Acme Corp, Inc.") == "acme-corp-inc"
    assert safe_name("a/b:c?.png") == "a_b_c_.png" and safe_name("") == "unnamed"
    assert normalize_domain("https://Acme.Frontify.com/x") == "acme.frontify.com"


def test_markdown_render_keeps_text_headings_and_raw_settings_fallback():
    page = {"id": "p", "title": "T", "url": "u", "modifiedAt": "m"}
    secs = [[{"__typename": "GuidelinePageHeading", "id": "h", "title": "Sub"},
             {"__typename": "GuidelinePageBlock", "id": "b", "content": "Hello", "type": {"name": "Text"}},
             {"__typename": "X", "id": "c", "content": None, "settings": {"k": "v"}, "type": {"name": "Color"}}]]
    md = render_page(page, secs, brand="Acme", brand_id="b1", path="G/T", extracted_at="now")
    assert "# T" in md and "## Sub" in md and "Hello" in md and '"k": "v"' in md and 'frontify_id: "p"' in md
    assert strip_front_matter(md).startswith("# T") and "block id=b" in render_block({"id": "b", "content": "x", "type": {"name": "Text"}})
