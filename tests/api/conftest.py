"""API integration test fixtures.

These tests exercise the FastAPI application as a black box —
they send HTTP requests and assert responses, focusing on the
client perspective.  External services (Qdrant, LLM, embedding)
are NOT mocked globally; individual test files patch them as needed.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

_proj_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_proj_root))

# Stub create_pool so main.py's module-level DB pool init is a no-op.
# Must happen before any test imports src.api.main (module-level code).
import src.db  # noqa: E402

src.db.create_pool = lambda name, config: MagicMock()  # type: ignore[assignment]

# Pre-load mocks for optional dependencies that may not be installed.
# These must be set before any module that imports them is loaded.
_opt_deps = {
    "httpx2": MagicMock(),
    "qdrant_client": MagicMock(),
    "qdrant_client.models": MagicMock(),
}
for _name, _mock in _opt_deps.items():
    sys.modules[_name] = _mock


@pytest.fixture
def client():
    """Return a fresh TestClient wrapping the FastAPI app.

    Calls load_app_config() to ensure the default configuration
    (from the project's config/ directory) is active.
    """
    from src.api.main import app
    from src.config import load_app_config

    load_app_config()
    return TestClient(app, raise_server_exceptions=False)
