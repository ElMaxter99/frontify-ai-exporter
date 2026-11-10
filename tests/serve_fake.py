"""QA harness: the real UI wired to the in-process fake Frontify (no network, no credentials).
    python -m tests.serve_fake   ->  http://127.0.0.1:8765  (token: test-token-123456)"""
import uvicorn

from src.app import create_app
from tests.fake_frontify import FakeFrontify

if __name__ == "__main__":
    f = FakeFrontify()
    uvicorn.run(create_app(api_transport=f.transport, download_transport=f.transport), host="127.0.0.1", port=8765, log_level="warning")
