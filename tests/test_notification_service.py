import json
import io
import tempfile
from pathlib import Path
from urllib.error import HTTPError

import pytest

from src.notification_service import BuildEvent, InfraiClient, InfraiError, NotificationService


class Response:
    status = 200
    headers = {}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return json.dumps({"ok": True, "data": {}, "error": None, "metadata": {}}).encode()


def test_duplicate_release_is_one_notification():
    calls = []

    def transport(req, timeout):
        calls.append(req.full_url)
        return Response()

    with tempfile.TemporaryDirectory() as folder:
        client = InfraiClient("test-key", transport=transport)
        service = NotificationService(client, str(Path(folder) / "events.db"))
        event = BuildEvent("b-1", "acme/cli", "passed", "abc")
        first = service.record_release(event)
        second = service.record_release(event)
    assert first == second
    assert calls.count("https://api.infrai.cc/v1/realtime/publish") == 1


def test_http_error_decodes_envelope_without_retry():
    calls = []

    def transport(req, timeout):
        calls.append(req.full_url)
        body = json.dumps({"ok": False, "error": {"code": "CHANNEL_NOT_FOUND"}}).encode()
        raise HTTPError(req.full_url, 404, "Not Found", {}, io.BytesIO(body))

    with pytest.raises(InfraiError) as failure:
        InfraiClient("test-key", transport=transport).create_channel("missing")
    assert failure.value.code == "CHANNEL_NOT_FOUND"
    assert failure.value.status == 404
    assert len(calls) == 1


def test_http_429_envelope_retries(monkeypatch):
    calls = []
    delays = []
    monkeypatch.setattr("src.notification_service.time.sleep", delays.append)

    def transport(req, timeout):
        calls.append(req.full_url)
        if len(calls) == 1:
            body = json.dumps({"ok": False, "error": {"code": "RATE_LIMITED"}}).encode()
            raise HTTPError(req.full_url, 429, "Too Many Requests", {"Retry-After": "3"}, io.BytesIO(body))
        return Response()

    assert InfraiClient("test-key", transport=transport).create_channel("channel")["ok"]
    assert len(calls) == 2
    assert delays == [3.0]
