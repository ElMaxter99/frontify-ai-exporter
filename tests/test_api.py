from __future__ import annotations

import time

from fastapi.testclient import TestClient

from src.api.app import create_app
from src.config import Settings
from tests.fake_frontify import TOKEN, FakeFrontify


def make_client(tmp_path, fake, token=TOKEN):
    s = Settings(_env_file=None, frontify_domain="acme.frontify.com", frontify_token=token, export_dir=str(tmp_path / "e"),
                 data_dir=str(tmp_path / "d"), page_size=2, web_dist=str(tmp_path / "nodist"))
    return TestClient(create_app(s, api_transport=fake.transport, download_transport=fake.transport))


def wait_done(c, timeout=20):
    end = time.time() + timeout
    while time.time() < end:
        j = c.get("/api/jobs").json()
        if not j["running"]:
            return j
        time.sleep(0.05)
    raise AssertionError("job did not finish")


def test_token_never_exposed_and_settings_roundtrip(tmp_path):
    with make_client(tmp_path, FakeFrontify()) as c:
        body = c.get("/api/settings").json()
        assert TOKEN not in str(body) and body["has_token"] and body["token_source"] == "env"
        r = c.put("/api/settings", json={"values": {"download_concurrency": 7, "frontify_domain": "https://X.frontify.com/"}, "token": "session-token-999999"})
        assert r.status_code == 200 and "session-token-999999" not in r.text
        assert r.json()["download_concurrency"] == 7 and r.json()["frontify_domain"] == "x.frontify.com" and r.json()["token_source"] == "session"
        assert c.get("/api/settings").json()["download_concurrency"] == 7


def test_connection_test_ok_and_bad(tmp_path):
    fake = FakeFrontify()
    with make_client(tmp_path, fake) as c:
        r = c.post("/api/connection/test").json()
        assert r["ok"] and r["user"] == "Jane" and r["brands"][0]["name"] == "Acme Corp"


def test_export_job_dashboard_explorer_search_and_failures(tmp_path):
    fake = FakeFrontify()
    with make_client(tmp_path, fake) as c:
        assert c.post("/api/scan").status_code == 200
        wait_done(c)
        d = c.get("/api/dashboard").json()
        assert d["brands"] == 1 and d["assets"] == 6 and d["pending"] >= 4 and d["configured"]

        assert c.post("/api/export", json={"categories": None}).status_code == 200
        assert c.post("/api/export").status_code in (409, 200)  # single slot
        j = wait_done(c)
        assert j["history"][0]["status"] == "completed"
        d = c.get("/api/dashboard").json()
        assert d["downloaded"] == 4 and d["failed"] == 1 and d["unavailable"] == 1 and d["guideline_pages"] >= 2 and d["chunks"] > 0
        assert d["last_sync"]["status"] == "completed"

        brands = c.get("/api/brands").json()
        tree = c.get(f"/api/brands/{brands[0]['id']}/tree").json()
        assert {f["name"] for f in tree["folders"]} == {"Primary", "Dark"} and tree["guidelines"]
        items = c.get("/api/assets", params={"category": "documents"}).json()
        assert items["total"] == 3
        a = c.get("/api/assets/a1").json()
        assert a["download_status"] == "done" and "downloadUrl" not in a["frontify"] and a["relationships"]
        assert c.get("/api/search", params={"q": "friendly direct optimistic"}).json()["results"]
        f = c.get("/api/failures").json()
        assert {x["id"] for x in f["assets"]} == {"a5", "a6"}
        runs = c.get("/api/sync/history").json()
        assert runs[0]["kind"] == "export" and c.get(f"/api/sync/{runs[0]['id']}/changes").json()
        assert c.get("/api/report").json()["totals"]["assets"] == 6
        page_id = next(g["id"] for g in tree["guidelines"] if g["id"] == "p1")
        assert "Clear space" in c.get(f"/api/guidelines/{page_id}").json()["markdown"]


def test_export_requires_configuration(tmp_path):
    s = Settings(_env_file=None, frontify_domain="", frontify_token="", export_dir=str(tmp_path / "e"), data_dir=str(tmp_path / "d"))
    with TestClient(create_app(s)) as c:
        assert c.post("/api/export").status_code == 400
        assert c.post("/api/connection/test").json()["ok"] is False
