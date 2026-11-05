"""Live-mode UI test: a real server (fake LLM) + the real page in jsdom (see tests/ui/live.js)."""
import shutil
import socket
import subprocess
import threading
import time
from pathlib import Path

import pytest
import uvicorn

from app.api import create_app
from app.config import Settings
from app.llm import FakeLLM

ROOT = Path(__file__).resolve().parent.parent
needs_node = pytest.mark.skipif(shutil.which("node") is None or not (ROOT / "node_modules" / "jsdom").exists(),
                                reason="needs node and jsdom (CI runs `npm install --no-save jsdom`)")


def responder(prompt: str) -> str:
    question = prompt.rsplit("Question:", 1)[-1]
    if "List notes" in question:
        return "SELECT note FROM xss"
    if "<schema>" in prompt:
        return "SELECT region, SUM(total_revenue_usd) AS total FROM sales GROUP BY region ORDER BY region"
    return "SELECT COUNT(*) FROM Artist"


@pytest.fixture()
def server(tmp_path):
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    settings = Settings(demo_answers="/nonexistent.json", session_dir=tmp_path / "sess", rate_per_minute=1000,
                        upload_rate_per_minute=1000)
    srv = uvicorn.Server(uvicorn.Config(create_app(settings, FakeLLM(responder)), host="127.0.0.1", port=port, log_level="warning"))
    t = threading.Thread(target=srv.run, daemon=True)
    t.start()
    for _ in range(100):
        if srv.started:
            break
        time.sleep(0.05)
    assert srv.started, "server did not start"
    yield f"http://127.0.0.1:{port}"
    srv.should_exit = True
    t.join(timeout=10)


@needs_node
def test_upload_flow_in_a_simulated_browser(server):
    r = subprocess.run(["node", str(ROOT / "tests/ui/live.js"), server], capture_output=True, text=True, cwd=ROOT, timeout=90)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "ui live ok" in r.stdout
