"""Monitor Integration tests (change.md "Fix and align Generator Service
with the real Monitor Readiness Contract" sec.13) - MonitorClient-level
checks against the REAL, confirmed contract:

    GET /monitor/{curriculumId}/readiness
    -> {"generatedReady": true}   or   {"generatedReady": false}

Run against a MOCKED Monitor HTTP endpoint (mocking is allowed only in
tests, never in production code - change.md sec.10/"Web UI" rules apply the
same principle to the client). No real Monitor connection is made or
required.

Mocks `httpx.AsyncClient.get` (monkeypatched for the duration of each test)
rather than running a real HTTP server - same "standalone script, plain
asserts" convention as the other scripts/test_*.py in this repo.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx  # noqa: E402

from monitor.client import MonitorClient  # noqa: E402
from monitor.schemas import MonitorReadinessStatus  # noqa: E402


class _FakeResponse:
    def __init__(self, status_code: int, json_body=None, json_error: Exception | None = None):
        self.status_code = status_code
        self._json_body = json_body
        self._json_error = json_error

    def json(self):
        if self._json_error is not None:
            raise self._json_error
        return self._json_body


def _patch_get(response=None, exception: Exception | None = None):
    """Monkeypatches httpx.AsyncClient.get for one call - captures the real
    URL requested too, so tests can assert the client hit the real contract
    path (GET /monitor/{curriculumId}/readiness), not a guessed one.
    """
    calls = []

    async def fake_get(self, url, **kwargs):
        calls.append(url)
        if exception is not None:
            raise exception
        return response

    original = httpx.AsyncClient.get
    httpx.AsyncClient.get = fake_get
    return original, calls


def _unpatch_get(original):
    httpx.AsyncClient.get = original


async def main() -> None:
    client = MonitorClient(base_url="https://monitor.test.invalid", timeout=1.0)

    # --- Contract check: the real endpoint shape is used, not a guessed one ---
    original, calls = _patch_get(response=_FakeResponse(200, {"generatedReady": True}))
    try:
        await client.check_readiness("cur-1")
    finally:
        _unpatch_get(original)
    assert calls == ["https://monitor.test.invalid/monitor/cur-1/readiness"], calls
    print("CONTRACT  GET /monitor/{curriculumId}/readiness is the exact URL requested: OK")

    # --- TEST 1 / 9: generatedReady=true -> READY ---
    original, _ = _patch_get(response=_FakeResponse(200, {"generatedReady": True}))
    try:
        result = await client.check_readiness("cur-1")
    finally:
        _unpatch_get(original)
    assert result.status == MonitorReadinessStatus.READY, result
    assert result.is_ready is True
    print("TEST 1/9  generatedReady=true -> READY: OK")

    # --- TEST 2 / 8: generatedReady=false -> NOT_READY ---
    original, _ = _patch_get(response=_FakeResponse(200, {"generatedReady": False}))
    try:
        result = await client.check_readiness("cur-1")
    finally:
        _unpatch_get(original)
    assert result.status == MonitorReadinessStatus.NOT_READY, result
    assert result.is_ready is False
    print("TEST 2/8  generatedReady=false -> NOT_READY: OK")

    # --- TEST 3: Monitor unavailable (connection failure) ---
    original, _ = _patch_get(exception=httpx.ConnectError("simulated connection refused"))
    try:
        result = await client.check_readiness("cur-1")
    finally:
        _unpatch_get(original)
    assert result.status == MonitorReadinessStatus.MONITOR_UNAVAILABLE, result
    print("TEST 3  Monitor connection failure -> MONITOR_UNAVAILABLE: OK")

    # --- TEST 4: Monitor timeout ---
    original, _ = _patch_get(exception=httpx.TimeoutException("simulated timeout"))
    try:
        result = await client.check_readiness("cur-1")
    finally:
        _unpatch_get(original)
    assert result.status == MonitorReadinessStatus.MONITOR_UNAVAILABLE, result
    print("TEST 4  Monitor timeout -> MONITOR_UNAVAILABLE: OK")

    # --- HTTP 5xx -> MONITOR_UNAVAILABLE (also part of the unavailable matrix) ---
    original, _ = _patch_get(response=_FakeResponse(503, {}))
    try:
        result = await client.check_readiness("cur-1")
    finally:
        _unpatch_get(original)
    assert result.status == MonitorReadinessStatus.MONITOR_UNAVAILABLE, result
    print("EXTRA     Monitor HTTP 5xx -> MONITOR_UNAVAILABLE: OK")

    # --- TEST 5: malformed JSON matrix (change.md sec.9's exact 6 examples) ---
    malformed_cases = [
        ({}, "empty object"),
        ({"generatedReady": None}, "generatedReady=null"),
        ({"generatedReady": "true"}, "generatedReady as string"),
        ({"generatedReady": 1}, "generatedReady as int"),
        ({"ready": True}, "wrong field name 'ready'"),
        ({"status": "READY"}, "wrong field name 'status'"),
    ]
    for body, label in malformed_cases:
        original, _ = _patch_get(response=_FakeResponse(200, body))
        try:
            result = await client.check_readiness("cur-1")
        finally:
            _unpatch_get(original)
        assert result.status == MonitorReadinessStatus.INVALID_RESPONSE, (label, result)
    print("TEST 5/6/7  all 6 malformed-response cases -> INVALID_RESPONSE, never READY: OK")

    # --- Invalid JSON body entirely (not even parseable) ---
    original, _ = _patch_get(response=_FakeResponse(200, json_error=ValueError("not json")))
    try:
        result = await client.check_readiness("cur-1")
    finally:
        _unpatch_get(original)
    assert result.status == MonitorReadinessStatus.INVALID_RESPONSE, result
    print("EXTRA     Non-JSON response body -> INVALID_RESPONSE: OK")

    # --- Monitor not configured at all (PLUG/WAIT) -> MONITOR_UNAVAILABLE, never a fabricated READY ---
    unconfigured_client = MonitorClient(base_url=None, timeout=1.0)
    result = await unconfigured_client.check_readiness("cur-1")
    assert result.status == MonitorReadinessStatus.MONITOR_UNAVAILABLE, result
    print("EXTRA     Monitor not configured -> MONITOR_UNAVAILABLE, never a fabricated READY: OK")

    print("\nALL Monitor Integration checks passed.")


if __name__ == "__main__":
    asyncio.run(main())
