import pathlib
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

# notification-service connects to Redis and initializes flask-socketio's
# RedisManager (via message_queue=...) at *import time*. There is no live
# Redis broker in the test environment, so redis.from_url must be mocked
# before the module is imported. flask-socketio's RedisManager also calls
# redis.from_url() internally for its pub/sub manager, so this single patch
# covers both the app's own redis_client AND socketio's fanout - the real
# Server/AsyncServer objects still initialize normally (self.server is a real
# object, not None), so socketio.emit() and the /stats eio.sockets lookup
# work against real in-memory socketio internals with no network I/O.
_mock_redis_client = MagicMock()
_mock_redis_client.ping.return_value = True

_redis_patch = patch("redis.from_url", return_value=_mock_redis_client)
_redis_patch.start()

import app as notification_app  # noqa: E402  (import must follow the patches above)


@pytest.fixture()
def mock_redis():
    """The mocked redis client the app module holds a reference to."""
    _mock_redis_client.reset_mock()
    _mock_redis_client.ping.return_value = True
    return _mock_redis_client


@pytest.fixture()
def client():
    notification_app.app.config["TESTING"] = True
    return notification_app.app.test_client()


@pytest.fixture()
def app_module():
    return notification_app
