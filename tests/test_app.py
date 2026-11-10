# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import time

from fastapi.testclient import TestClient

from src.app import create_app
from tests.fake_frontify import TOKEN, FakeFrontify


def wait(c, timeout=20):
    end = time.time() + timeout
    while time.time() < end:
        s = c.get("/api/status").json()
        if not s["running"] and s["phase"] in ("done", "analyzed", "failed"):
            return s
        time.sleep(0.05)
    raise AssertionError("timeout")


def test_ui_flow_analyze_then_export_and_token_never_returned(tmp_path):
    fake = FakeFrontify()
    app = create_app(api_transport=fake.transport, download_transport=fake.transport)
    body = {"url": "https://acme.frontify.com", "token": TOKEN, "dest": str(tmp_path / "out"), "name": "CLIENTE_01", "concurrency": 3}
    with TestClient(app) as c:
        assert c.get("/").status_code == 200 and "EXPORTAR TODO" in c.get("/").text
        assert c.post("/api/analyze", json={**body, "token": ""}).status_code == 400
        assert c.post("/api/analyze", json=body).status_code == 200
        s = wait(c)
        assert s["phase"] == "analyzed" and s["result"]["assets"] == 6 and s["found"] == 6
        assert c.post("/api/export", json=body).status_code == 200
        s = wait(c)
        assert s["phase"] == "done" and s["percent"] == 100
        assert (s["found"], s["downloaded"], s["errors"]) == (6, 4, 2) and s["documents"] >= 4
        assert s["result"]["summary"]["assets_failed"] == 1 and s["folder"].endswith("CLIENTE_01")
        assert TOKEN not in c.get("/api/status").text and TOKEN not in c.get("/api/config").text
        assert (tmp_path / "out/CLIENTE_01/README_AI.md").exists()
        assert c.post("/api/open-folder").status_code == 200


def test_bad_token_reports_error(tmp_path):
    import httpx
    app = create_app(api_transport=httpx.MockTransport(lambda r: httpx.Response(401)))
    with TestClient(app) as c:
        c.post("/api/export", json={"url": "acme.frontify.com", "token": "x" * 12, "dest": str(tmp_path)})
        s = wait(c)
        assert s["phase"] == "failed" and "rejected" in s["message"]


def test_docker_locked_destination(tmp_path, monkeypatch):
    fake = FakeFrontify()
    monkeypatch.setenv("EXPORT_DIR_LOCKED", "1")
    monkeypatch.setenv("EXPORT_DIR", str(tmp_path / "mounted"))
    monkeypatch.setenv("HOST_EXPORT_DIR", "./EXPORTS")
    app = create_app(api_transport=fake.transport, download_transport=fake.transport)
    with TestClient(app) as c:
        cfg = c.get("/api/config").json()
        assert cfg["locked"] and not cfg["can_pick_folder"]
        # whatever the browser sends, files only go to the mounted folder
        assert c.post("/api/export", json={"url": "acme.frontify.com", "token": TOKEN, "dest": "/etc"}).status_code == 200
        s = wait(c)
        assert s["phase"] == "done" and s["folder"].startswith(str(tmp_path / "mounted"))
        assert "./EXPORTS" in c.post("/api/open-folder").json()["error"]
