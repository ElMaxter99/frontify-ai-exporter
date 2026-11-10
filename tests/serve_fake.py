"""Dev/QA harness: the real app wired to the in-process fake Frontify (no network, no credentials).
    python -m tests.serve_fake   ->  http://localhost:8765
"""
import tempfile

import uvicorn

from src.api.app import create_app
from src.config import Settings
from tests.fake_frontify import TOKEN, FakeFrontify

if __name__ == "__main__":
    tmp = tempfile.mkdtemp(prefix="fae-demo-")
    fake = FakeFrontify()
    s = Settings(_env_file=None, frontify_domain="demo.frontify.com", frontify_token=TOKEN, export_dir=f"{tmp}/exports", data_dir=f"{tmp}/data", page_size=2)
    uvicorn.run(create_app(s, api_transport=fake.transport, download_transport=fake.transport), host="127.0.0.1", port=8765, log_level="warning")
