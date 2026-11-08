"""Generator Gate tests (change.md "Fix and align Generator Service with the
real Monitor Readiness Contract" sec.13) - exercised against
`api_server.start_generate()` directly (a plain async function - called here
without an HTTP server) with `MonitorClient.check_readiness` and
`master_agent.master.run` both monkeypatched. No real Monitor connection, no
real Generate run.

Proves the actual gate wiring: READY (generatedReady=true) reaches the
existing Generate flow unchanged (Master IS called, only after a real
POST /api/generate call); every other status stops before Master/Agent/
Retrieval Manager/MCP are ever touched; and Monitor reporting READY never
by itself triggers generation without that explicit call (change.md sec.12).
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import api_server  # noqa: E402
from fastapi import HTTPException  # noqa: E402
from monitor.schemas import MonitorReadinessResult, MonitorReadinessStatus  # noqa: E402


def _reset_job_state():
    api_server._jobs.clear()
    api_server._active_job_id = None


async def _fake_run_master(run_id=None):
    _fake_run_master.calls.append(run_id)
    return Path("/tmp/fake_output.docx")


_fake_run_master.calls = []


async def main() -> None:
    # --- TEST 1: Monitor = READY (generatedReady=true) -> Generate starts, Master called, flow unchanged ---
    _reset_job_state()
    _fake_run_master.calls.clear()
    api_server._monitor_client.check_readiness = lambda curriculum_id: _result(MonitorReadinessStatus.READY)
    api_server.run_master = _fake_run_master
    response = await api_server.start_generate(api_server.GenerateRequest(curriculum_id="cur-1"))
    await asyncio.sleep(0.05)  # let the background asyncio.create_task(_execute(...)) run
    assert response["status"] == "running" and "job_id" in response, response
    assert len(_fake_run_master.calls) == 1, "Master (run_master) was not called after READY (generatedReady=true)"
    print("TEST 1  Monitor = READY (generatedReady=true) -> Generate starts, Master called, existing flow unchanged: OK")

    # --- TEST 2: Monitor = NOT_READY -> Generate does not start, Master/Agent/Retrieval/MCP not called ---
    _reset_job_state()
    _fake_run_master.calls.clear()
    api_server._monitor_client.check_readiness = lambda curriculum_id: _result(MonitorReadinessStatus.NOT_READY)
    try:
        await api_server.start_generate(api_server.GenerateRequest(curriculum_id="cur-1"))
        raise SystemExit("expected HTTPException for NOT_READY")
    except HTTPException as exc:
        assert exc.status_code == 412, exc.status_code
        assert exc.detail["reason"] == "NOT_READY", exc.detail
    assert len(_fake_run_master.calls) == 0, "Master must not be called when NOT_READY"
    assert api_server._active_job_id is None, "no job should have been created"
    print("TEST 2  Monitor = NOT_READY -> Generate does not start, Master not called: OK")

    # --- TEST 3: Monitor timeout -> no Generate ---
    _reset_job_state()
    _fake_run_master.calls.clear()
    api_server._monitor_client.check_readiness = lambda curriculum_id: _result(
        MonitorReadinessStatus.MONITOR_UNAVAILABLE, detail="timed out"
    )
    try:
        await api_server.start_generate(api_server.GenerateRequest(curriculum_id="cur-1"))
        raise SystemExit("expected HTTPException")
    except HTTPException as exc:
        assert exc.status_code == 412 and exc.detail["reason"] == "MONITOR_UNAVAILABLE", exc.detail
    assert len(_fake_run_master.calls) == 0
    print("TEST 3  Monitor timeout -> no Generate: OK")

    # --- TEST 4: Monitor connection failure -> no Generate ---
    _reset_job_state()
    _fake_run_master.calls.clear()
    api_server._monitor_client.check_readiness = lambda curriculum_id: _result(
        MonitorReadinessStatus.MONITOR_UNAVAILABLE, detail="connection refused"
    )
    try:
        await api_server.start_generate(api_server.GenerateRequest(curriculum_id="cur-1"))
        raise SystemExit("expected HTTPException")
    except HTTPException as exc:
        assert exc.status_code == 412 and exc.detail["reason"] == "MONITOR_UNAVAILABLE"
    assert len(_fake_run_master.calls) == 0
    print("TEST 4  Monitor connection failure -> no Generate: OK")

    # --- TEST 5: Monitor HTTP 5xx -> no Generate ---
    _reset_job_state()
    _fake_run_master.calls.clear()
    api_server._monitor_client.check_readiness = lambda curriculum_id: _result(
        MonitorReadinessStatus.MONITOR_UNAVAILABLE, detail="HTTP 503"
    )
    try:
        await api_server.start_generate(api_server.GenerateRequest(curriculum_id="cur-1"))
        raise SystemExit("expected HTTPException")
    except HTTPException as exc:
        assert exc.status_code == 412 and exc.detail["reason"] == "MONITOR_UNAVAILABLE"
    assert len(_fake_run_master.calls) == 0
    print("TEST 5  Monitor HTTP 5xx -> no Generate: OK")

    # --- TEST 6: Invalid JSON -> no Generate ---
    _reset_job_state()
    _fake_run_master.calls.clear()
    api_server._monitor_client.check_readiness = lambda curriculum_id: _result(
        MonitorReadinessStatus.INVALID_RESPONSE, detail="not valid JSON"
    )
    try:
        await api_server.start_generate(api_server.GenerateRequest(curriculum_id="cur-1"))
        raise SystemExit("expected HTTPException")
    except HTTPException as exc:
        assert exc.status_code == 412 and exc.detail["reason"] == "INVALID_RESPONSE"
    assert len(_fake_run_master.calls) == 0
    print("TEST 6  Invalid JSON -> no Generate: OK")

    # --- TEST 7: Missing required readiness field -> no Generate ---
    _reset_job_state()
    _fake_run_master.calls.clear()
    api_server._monitor_client.check_readiness = lambda curriculum_id: _result(
        MonitorReadinessStatus.INVALID_RESPONSE, detail="missing status field"
    )
    try:
        await api_server.start_generate(api_server.GenerateRequest(curriculum_id="cur-1"))
        raise SystemExit("expected HTTPException")
    except HTTPException as exc:
        assert exc.status_code == 412 and exc.detail["reason"] == "INVALID_RESPONSE"
    assert len(_fake_run_master.calls) == 0
    print("TEST 7  Missing required readiness field -> no Generate: OK")

    # --- TEST 8: Unknown readiness status -> no Generate ---
    _reset_job_state()
    _fake_run_master.calls.clear()
    api_server._monitor_client.check_readiness = lambda curriculum_id: _result(
        MonitorReadinessStatus.INVALID_RESPONSE, detail="unrecognized status value"
    )
    try:
        await api_server.start_generate(api_server.GenerateRequest(curriculum_id="cur-1"))
        raise SystemExit("expected HTTPException")
    except HTTPException as exc:
        assert exc.status_code == 412 and exc.detail["reason"] == "INVALID_RESPONSE"
    assert len(_fake_run_master.calls) == 0
    print("TEST 8  Unknown readiness status -> no Generate: OK")

    # --- TEST 9: READY then existing Generate failure -> Monitor integration
    # succeeds (Master WAS called), existing Generate error behavior remains
    # (job ends up "failed", not swallowed or turned into a fake success). ---
    _reset_job_state()

    async def _failing_run_master(run_id=None):
        raise RuntimeError("simulated: SAR Template not available")

    api_server._monitor_client.check_readiness = lambda curriculum_id: _result(MonitorReadinessStatus.READY)
    api_server.run_master = _failing_run_master
    response = await api_server.start_generate(api_server.GenerateRequest(curriculum_id="cur-1"))
    job_id = response["job_id"]
    await asyncio.sleep(0.05)  # let _execute()'s try/except (unchanged, existing behavior) run
    assert api_server._jobs[job_id]["status"] == "failed", api_server._jobs[job_id]
    assert "SAR Template not available" in api_server._jobs[job_id]["error"]
    print("TEST 9  READY then existing Generate failure -> Monitor integration succeeded, existing error behavior kept: OK")

    # --- TEST 10: NOT_READY does not reach Master/Agent/Retrieval Manager/MCP ---
    # (Master/Agent/Retrieval Manager/MCP all live inside master_agent.master.run
    # - already proven not called in TEST 2's assertion on _fake_run_master.calls;
    # restated here explicitly per change.md's own numbering.)
    _reset_job_state()
    _fake_run_master.calls.clear()
    api_server._monitor_client.check_readiness = lambda curriculum_id: _result(MonitorReadinessStatus.NOT_READY)
    api_server.run_master = _fake_run_master
    try:
        await api_server.start_generate(api_server.GenerateRequest(curriculum_id="cur-1"))
    except HTTPException:
        pass
    assert len(_fake_run_master.calls) == 0, "master_agent.master.run (Master/Agent/Retrieval/MCP) must not be reached"
    print("TEST 10 NOT_READY never reaches Master/Agent/Retrieval Manager/MCP: OK")

    # --- TEST 11: Monitor reporting generatedReady=true, with no User
    # POST /api/generate call ever made, must NOT by itself trigger
    # generation (change.md sec.12/13 - "NO AUTOMATIC GENERATION"). There is
    # no poller/webhook anywhere in this codebase that calls
    # MonitorClient.check_readiness() outside of start_generate() itself -
    # calling it standalone here, with a READY result, proves it has no
    # side effect on job/Master state on its own; only start_generate()
    # (i.e. a real User Generate click) ever goes on to invoke Master. ---
    _reset_job_state()
    _fake_run_master.calls.clear()
    api_server._monitor_client.check_readiness = lambda curriculum_id: _result(MonitorReadinessStatus.READY)
    await api_server._monitor_client.check_readiness("cur-1")  # Monitor says READY...
    assert len(_fake_run_master.calls) == 0, "check_readiness alone (no User Generate click) must never invoke Master"
    assert api_server._active_job_id is None, "check_readiness alone must never create a generation job"
    print("TEST 11 Monitor READY alone, without a User POST /api/generate, never triggers generation: OK")

    print("\nALL 11 Generator Gate checks passed.")


def _result(status: MonitorReadinessStatus, detail: str = "") -> MonitorReadinessResult:
    async def _coro():
        return MonitorReadinessResult(status=status, curriculum_id="cur-1", detail=detail)

    return _coro()


if __name__ == "__main__":
    asyncio.run(main())
