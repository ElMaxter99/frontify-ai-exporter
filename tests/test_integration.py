from __future__ import annotations

import hashlib
import json
from pathlib import Path

from src.ai.indexer import Searcher
from src.exporter.pipeline import ExportOptions
from tests.fake_frontify import FakeFrontify


def jload(p: Path):
    return json.loads(p.read_text("utf-8"))


async def test_full_export_structure_integrity_and_isolation(env, fake: FakeFrontify):
    cfg, db, bus, pipe = env
    report = await pipe.run(ExportOptions())
    root = cfg.export_path
    brand = root / "brands" / "acme"

    # --- originals downloaded, hash-verified, organised by category/library/folder
    logo = brand / "assets/logos/Logos/Acme Logo.png"
    assert logo.read_bytes() == fake.files["a1"]
    assert (brand / "assets/icons/Logos/Primary/Icon Set.svg").exists()  # name says "Icon" -> icons
    assert (brand / "assets/documents/Logos/Primary/Dark/Voice Guide.txt").read_bytes() == fake.files["a3"]
    row = db.one("SELECT * FROM assets WHERE id='a1'")
    assert row["sha256"] == hashlib.sha256(fake.files["a1"]).hexdigest() and row["download_status"] == "done"

    # --- one broken + one protected asset must not stop the export, and are reported
    assert db.one("SELECT download_status FROM assets WHERE id='a6'")["download_status"] == "failed"
    assert db.one("SELECT download_status FROM assets WHERE id='a5'")["download_status"] == "unavailable"
    assert {a["id"] for a in report["failed_assets"]} == {"a6"}
    assert {a["id"] for a in report["unavailable_assets"]} == {"a5"}
    assert db.one("SELECT download_status FROM assets WHERE id='a4'")["download_status"] == "done"

    # --- guideline pages: markdown with hierarchy + original json + embedded media preview
    md_files = sorted((brand / "guidelines/markdown").rglob("*.md"))
    names = [p.relative_to(brand / "guidelines/markdown").as_posix() for p in md_files]
    assert any(n.endswith("Foundations/00-logo-usage.md") or "logo-usage" in n for n in names)
    logo_md = next(p for p in md_files if "logo-usage" in p.name).read_text("utf-8")
    assert "# Logo usage" in logo_md and "## Clear space" in logo_md and "clear space equal" in logo_md and "frontify_id" in logo_md
    assert list((brand / "guidelines/original/media").glob("*.png"))
    assert any("tone-of-voice" in p.name for p in md_files)
    assert (brand / "guidelines/original/navigation.json").exists() and (brand / "guidelines/pdf/README.txt").exists()
    # block without text content keeps its raw settings so nothing is lost
    tone = next(p for p in md_files if "tone-of-voice" in p.name).read_text("utf-8")
    assert '"palette": "main"' in tone

    # --- metadata json
    meta = brand / "metadata"
    assets = jload(meta / "assets.json")
    a1 = next(a for a in assets if a["frontify_id"] == "a1")
    assert a1["export"]["sha256"] and a1["mime_type"] == "image/png" and a1["author"] == "Jane" and a1["tags"][0]["value"] == "brand"
    assert a1["file_metadata"]["width"] == 8  # image metadata extracted from the original
    assert "downloadUrl" not in a1["raw_frontify"]  # signed URLs are credentials: never persisted in exports
    assert {f["name"] for f in jload(meta / "folders.json")} == {"Primary", "Dark"}
    rels = jload(meta / "relationships.json")
    assert {"src_type": "collection", "src_id": "col1", "rel": "contains", "dst_type": "asset", "dst_id": "a1"} in rels
    assert any(r["rel"] == "related" and r["src_id"] == "a1" and r["dst_id"] == "a2" for r in rels)
    assert any(r["rel"] == "shows" and r["src_id"] == "lp1" for r in rels)
    assert jload(meta / "essentials.json")["fontFamilies"]["items"][0]["name"] == "Acme Sans"

    # --- knowledge base from real data only
    k = brand / "knowledge"
    for f in ("brand_context.md", "brand_guidelines.md", "visual_identity.md", "typography.md", "colors.md", "tone_of_voice.md", "complete_index.md", "chunks.jsonl"):
        assert (k / f).exists(), f
    assert "#E4002B" in (k / "colors.md").read_text() and "Acme Sans" in (k / "typography.md").read_text()
    assert "friendly, direct and optimistic" in (k / "tone_of_voice.md").read_text()
    assert "Acme Logo.png" in (k / "complete_index.md").read_text() or "Acme Logo" in (k / "complete_index.md").read_text()
    # extracted text from a downloaded document
    assert any("friendly and direct" in p.read_text() for p in (k / "extracted_text").glob("*.md"))

    # --- chunks carry provenance
    chunks = [json.loads(l) for l in (k / "chunks.jsonl").read_text().splitlines()]
    assert chunks
    for c in chunks:
        for key in ("brand", "frontify_id", "source_file", "category", "folder", "extracted_at", "kind"):
            assert key in c["metadata"], (key, c["metadata"])
    guideline_chunk = next(c for c in chunks if c["metadata"]["kind"] == "guideline_page" and "clear space" in c["text"])
    assert guideline_chunk["metadata"]["source_url"] == "/p1" and guideline_chunk["metadata"]["brand"] == "Acme Corp"

    # --- search (lexical, no embeddings configured)
    hits = Searcher(db).search("clear space logo", k=3)
    assert hits and hits[0]["metadata"]["frontify_id"] in ("p1",) and hits[0]["mode"] == "lexical"

    # --- global files
    manifest = jload(root / "manifest.json")
    assert manifest["brands"][0]["knowledge_files"]["colors.md"]["sha256"]
    inv = jload(root / "global/inventory.json")
    assert inv["brands"][0]["assets"]["done"] == 4
    assert jload(root / "global/export_report.json")["totals"]["assets"] == 6


async def test_incremental_sync_downloads_only_changes_and_detects_deletions(env, fake: FakeFrontify):
    cfg, db, bus, pipe = env
    await pipe.run(ExportOptions())
    first = list(fake.downloads)
    assert sorted(set(first)) == ["a1", "a2", "a3", "a4", "a6"]

    # run again with nothing changed -> no re-downloads of healthy files
    fake.downloads.clear()
    r2 = await pipe.run(ExportOptions())
    assert [d for d in fake.downloads if d != "a6"] == []
    assert not any(c["change"] in ("new", "modified") and c["entity"] == "asset" for c in r2["changes_this_run"])

    # modify a1 (new bytes + modifiedAt), delete a2, add a new asset and a new guideline text
    new = b"NEWPNG" + fake.files["a1"]
    fake.files["a1"] = new
    a1 = fake.state["assets"]["l1"][0]
    a1.update(modifiedAt="2025-06-01T00:00:00Z", size=len(new))
    fake.state["assets"]["f1"] = []
    fake.state["assets"]["l1"].append(__import__("tests.fake_frontify", fromlist=["asset"]).asset("a7", "Fresh", "txt", 5))
    fake.files["a7"] = b"fresh"
    fake.state["pages"]["p2"]["sections"][0][0]["content"] = "We are bold now."
    fake.downloads.clear()
    r3 = await pipe.run(ExportOptions())

    assert sorted(d for d in fake.downloads if d != "a6") == ["a1", "a7"]
    assert (cfg.export_path / "brands/acme/assets/logos/Logos/Acme Logo.png").read_bytes() == new
    ch = {(c["entity"], c["change"]): c["n"] for c in r3["changes_this_run"]}
    assert ch[("asset", "modified")] >= 1 and ch[("asset", "new")] == 1 and ch[("asset", "deleted")] == 1
    assert ch[("guideline_content", "modified")] == 1
    assert db.one("SELECT status FROM assets WHERE id='a2'")["status"] == "deleted"
    # history is kept
    assert db.scalar("SELECT count(*) FROM sync_runs") == 3


async def test_deletion_not_declared_when_scan_incomplete(env, fake: FakeFrontify):
    cfg, db, bus, pipe = env
    await pipe.run(ExportOptions(download=False, guidelines=False, knowledge=False, index=False))
    fake.fail_once["FolderAssets"] = 99  # folder asset listing keeps failing -> crawl incomplete
    fake.state["assets"]["f2"] = []
    await pipe.run(ExportOptions(download=False, guidelines=False, knowledge=False, index=False))
    assert db.one("SELECT status FROM assets WHERE id='a3'")["status"] == "active"  # not wrongly marked deleted


async def test_resume_partial_download_and_hardlink_dedupe(env, fake: FakeFrontify):
    cfg, db, bus, pipe = env
    await pipe.run(ExportOptions(download=False, guidelines=False, knowledge=False, index=False))
    dest = cfg.export_path / "brands/acme/assets/documents/Logos/Primary/Dark/Voice Guide.txt"
    dest.parent.mkdir(parents=True)
    part = dest.with_name(dest.name + ".part")
    part.write_bytes(fake.files["a3"][:10])
    await pipe.run(ExportOptions(scan=False, guidelines=False, knowledge=False, index=False, categories={"documents"}))
    assert dest.read_bytes() == fake.files["a3"] and not part.exists()


async def test_transient_api_errors_are_retried_during_scan(env, fake: FakeFrontify):
    cfg, db, bus, pipe = env
    fake.fail_once["Brands"] = 1
    fake.fail_once["RootAssets"] = 1
    await pipe.run(ExportOptions(download=False, guidelines=False, knowledge=False, index=False))
    assert db.scalar("SELECT count(*) FROM assets WHERE status='active'") == 6


async def test_duplicate_detection(env, fake: FakeFrontify):
    cfg, db, bus, pipe = env
    fake.files["a4"] = fake.files["a3"]  # identical bytes under two assets
    fake.state["assets"]["l2"][0]["size"] = len(fake.files["a3"])
    report = await pipe.run(ExportOptions(guidelines=False, knowledge=False, index=False))
    assert report["totals"]["duplicates"] == 1
