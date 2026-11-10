# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from src.frontify.client import FrontifyAuthError
from tests.fake_frontify import TOKEN, FakeFrontify, asset


def jl(p: Path):
    return json.loads(p.read_text("utf-8"))


async def test_analyze_reads_structure_without_writing_files(make_exporter, tmp_path):
    ex = make_exporter()
    s = await ex.analyze()
    assert s["brands"] == ["Acme Corp"] and s["assets"] == 6 and s["folders"] == 2 and s["libraries_workspaces"] == 2
    assert s["guideline_pages"] == 4 and s["by_type"]["documents"] == 3
    assert s["api_capabilities"]["introspection"] and ex.progress.result["kind"] == "analysis" and ex.progress.found == 6
    assert not (tmp_path / "EXPORTS").exists()


async def test_full_export_layout_originals_docs_and_report(make_exporter, fake: FakeFrontify):
    ex = make_exporter()
    report = await ex.export()
    c = ex.client_dir
    assert c.name == "CLIENTE_01"

    # originals: byte-exact, hash verified, spec folder layout
    logo = c / "02_ASSETS/LOGOS/Acme Corp/Logos/Acme Logo.png"
    assert logo.read_bytes() == fake.files["a1"]
    assert (c / "02_ASSETS/ICONS/Acme Corp/Logos/Primary/Icon Set.svg").exists()
    assert (c / "03_DOCUMENTATION/Acme Corp/Logos/Primary/Dark/Voice Guide.txt").read_bytes() == fake.files["a3"]
    for d in ("01_BRAND_GUIDELINES", "02_ASSETS", "03_DOCUMENTATION", "04_DESIGN_SYSTEM", "05_METADATA", "06_AI_KNOWLEDGE"):
        assert (c / d).is_dir(), d
    assert not list(c.rglob("*.part"))

    # failure isolation + honest accounting
    s = report["summary"]
    assert (s["assets_found"], s["assets_downloaded"], s["assets_failed"], s["assets_unavailable"]) == (6, 4, 1, 1)
    assert s["guideline_pages_found"] == 4 and s["guideline_pages_exported"] == 4 and s["document_texts_extracted"] >= 2
    ne = {n["id"]: n for n in report["not_exported"]}
    assert "404" in ne["a6"]["reason"] and "preview was NOT substituted" in ne["a5"]["reason"]
    assert jl(c / "EXPORT_REPORT.json")["summary"] == s and report["limitations"]
    assert ex.progress.snapshot()["errors"] >= 2 and ex.progress.phase == "done"

    # guidelines: hierarchy, text, headings, embedded preview, raw json
    md = next((c / "01_BRAND_GUIDELINES").rglob("*logo-usage.md")).read_text()
    assert "## Clear space" in md and "clear space equal" in md and "frontify_id" in md
    assert list((c / "01_BRAND_GUIDELINES/Acme Corp/_media").glob("*.png"))
    tone = next((c / "01_BRAND_GUIDELINES").rglob("*tone-of-voice.md")).read_text()
    assert '"palette": "main"' in tone  # no text content -> raw settings kept, nothing lost

    # metadata keeps the link to the original Frontify location
    m = c / "05_METADATA/Acme Corp"
    a1 = next(a for a in jl(m / "assets.json") if a["frontify_id"] == "a1")
    assert a1["frontify_location"]["folder_path"] == "Logos" and a1["export"]["local_path"].endswith("Acme Logo.png")
    assert a1["export"]["sha256"] == hashlib.sha256(fake.files["a1"]).hexdigest() and a1["file_metadata"]["width"] == 8
    assert "downloadUrl" not in a1["frontify_raw"]
    rel = jl(m / "relationships.json")
    assert any(r["rel"] == "contains" and r["src_id"] == "col1" and r["dst_id"] == "a2" for r in rel)
    assert any(r["rel"] == "related_to" and r["src_id"] == "a1" for r in rel) and any(r["rel"] == "shows" and r["src_id"] == "lp1" for r in rel)
    assert jl(c / "05_METADATA/api_capabilities.json")["introspection"]

    # AI docs: real data only, explicit gaps
    ai = c / "06_AI_KNOWLEDGE"
    for f in ("BRAND_OVERVIEW", "VISUAL_IDENTITY", "BRAND_GUIDELINES", "ASSET_INDEX", "DESIGN_SYSTEM", "CONTENT_INDEX"):
        assert (ai / f"{f}.md").exists(), f
    vis = (ai / "VISUAL_IDENTITY.md").read_text()
    assert "#E4002B" in vis and "Acme Sans" in vis and "Acme Red" in vis and "Acme Logo" in vis
    assert "friendly, direct and optimistic" in (ai / "BRAND_GUIDELINES.md").read_text()
    idx = (ai / "ASSET_INDEX.md").read_text()
    assert "02_ASSETS/LOGOS/Acme Corp/Logos/Acme Logo.png" in idx and "NOT EXPORTED (failed" in idx and "Icons for UI" in idx
    design = (ai / "DESIGN_SYSTEM.md").read_text()
    assert "no design-token or component queries" in design and "Not available" in design
    assert "Not available" not in (ai / "BRAND_OVERVIEW.md").read_text()
    readme = (c / "README_AI.md").read_text()
    assert "untouched originals" in readme and "BRAND_OVERVIEW.md" in readme
    content = (ai / "CONTENT_INDEX.md").read_text()
    assert "Voice Guide" in content and "_extracted_text" in content

    # manifest covers files with checksums
    man = jl(c / "manifest.json")
    assert man["files"]["02_ASSETS/LOGOS/Acme Corp/Logos/Acme Logo.png"]["sha256"] == hashlib.sha256(fake.files["a1"]).hexdigest()
    assert "06_AI_KNOWLEDGE/DESIGN_SYSTEM.md" in man["files"]
    assert (c / "export.log").exists() and TOKEN not in (c / "export.log").read_text()


async def test_rerun_skips_unchanged_and_keeps_previous_version_of_changed(make_exporter, fake: FakeFrontify):
    ex = make_exporter()
    await ex.export()
    fake.downloads.clear()
    r2 = await make_exporter().export()
    assert [d for d in fake.downloads if d != "a6"] == [] and r2["summary"]["assets_unchanged"] == 4

    old = fake.files["a1"]
    new = b"NEW" + old
    fake.files["a1"] = new
    fake.state["assets"]["l1"][0].update(modifiedAt="2025-06-01T00:00:00Z", size=len(new))
    fake.state["assets"]["l1"].append(asset("a7", "Fresh", "txt", 5))
    fake.files["a7"] = b"fresh"
    fake.downloads.clear()
    r3 = await make_exporter().export()
    assert sorted(d for d in fake.downloads if d != "a6") == ["a1", "a7"]
    c = ex.client_dir
    assert (c / "02_ASSETS/LOGOS/Acme Corp/Logos/Acme Logo.png").read_bytes() == new
    prev = list((c / "_previous_versions").rglob("Acme Logo.png.*"))
    assert len(prev) == 1 and prev[0].read_bytes() == old  # original never silently overwritten
    assert r3["summary"]["assets_downloaded"] == 2


async def test_resume_partial_download(make_exporter, fake: FakeFrontify):
    ex = make_exporter()
    dest = ex.client_dir / "03_DOCUMENTATION/Acme Corp/Logos/Primary/Dark/Voice Guide.txt"
    dest.parent.mkdir(parents=True)
    part = dest.with_name(dest.name + ".part")
    part.write_bytes(fake.files["a3"][:10])
    await ex.export()
    assert dest.read_bytes() == fake.files["a3"] and not part.exists()


async def test_duplicates_detected_not_dropped(make_exporter, fake: FakeFrontify):
    fake.files["a4"] = fake.files["a3"]
    fake.state["assets"]["l2"][0]["size"] = len(fake.files["a3"])
    ex = make_exporter()
    r = await ex.export()
    assert r["summary"]["duplicates_detected"] == 1 and len(r["duplicates"]) == 1
    assert (ex.client_dir / "03_DOCUMENTATION/Acme Corp/Docs/Notes.md").exists()  # both files kept


async def test_transient_api_errors_are_retried(make_exporter, fake: FakeFrontify):
    fake.fail_once["Brands"] = 1
    fake.fail_once["RootAssets"] = 1
    s = await make_exporter().analyze()
    assert s["assets"] == 6 and not s["errors"]


async def test_incomplete_crawl_is_reported(make_exporter, fake: FakeFrontify):
    fake.fail_once["FolderAssets"] = 99
    s = await make_exporter().analyze()
    assert s["assets"] < 6 and any("assets of" in e["where"] or "only" in e["reason"] for e in s["errors"])


async def test_missing_credentials_and_bad_token(tmp_path, fake):
    from src.exporter.run import Exporter
    with pytest.raises(FrontifyAuthError):
        await Exporter("acme.frontify.com", "", tmp_path).analyze()
    import httpx
    ex = Exporter("acme.frontify.com", "badtoken", tmp_path, api_transport=httpx.MockTransport(lambda r: httpx.Response(401)))
    report = await ex.export()  # export never raises: it reports
    assert report["status"] == "failed" and "rejected" in report["error"] and ex.progress.phase == "failed"
    assert json.loads((ex.client_dir / "EXPORT_REPORT.json").read_text())["status"] == "failed"
