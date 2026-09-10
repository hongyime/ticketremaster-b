import os, sys, pathlib

os.environ.setdefault("JWT_SECRET", "synthetic-test-key-at-least-32-characters")
os.environ.setdefault("OUTSYSTEMS_API_KEY", "test-key")
os.environ.setdefault("CREDIT_SERVICE_URL", "http://credit-mock")
os.environ.setdefault("RABBITMQ_HOST", "localhost")
os.environ.setdefault("SEAT_HOLD_DURATION_SECONDS", "10")

# Orchestrator root — ticket-purchase-orchestrator/
_orch_root = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_orch_root))

# Repo root — ticketremaster-b/
# Needed so `from shared.queue_setup import declare_queues` inside
# startup_queue_setup.py can resolve when running tests locally.
_repo_root = _orch_root.parents[1]
sys.path.insert(0, str(_repo_root))

import pytest
from unittest.mock import patch


@pytest.fixture()
def app():
    with patch("dotenv.load_dotenv", return_value=False), \
         patch.dict(os.environ, {"REDIS_URL": ""}), \
         patch("startup_queue_setup.bootstrap"), \
         patch("dlx_consumer.start_dlx_consumer"):
        from app import create_app
        return create_app({"TESTING": True})


@pytest.fixture()
def client(app):
    return app.test_client()
