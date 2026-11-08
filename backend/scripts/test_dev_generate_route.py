"""Wiring tests for the Development/Test generate route (fix.md "single Generator core").

These verify ROUTING/GATING only - that `/api/dev/generate` and the production
`/api/generate` reach the SAME generation core, that only the entry gate differs,
that the dev route is opt-in and can never coexist with a configured Monitor, and
that the real-Generator claim is not made by scripts. In this file `run_master` is
replaced by a recording stand-in purely to observe which route reaches it; REAL
generation through the browser is proven by scripts/browser_e2e.py (real Master,
Gemini, MCP, Chroma, Mongo) and is NOT claimed by these tests.

Each case runs in its own subprocess because settings are read at import time.
All Mongo writes (Monitor gate logs) go to a temporary DB that is dropped afterwards.
"""

from __future__ import annotations

import ast
import asyncio
import os
import subprocess
import sys
import uuid
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
FRONTEND = BACKEND.parent / "frontend"


def _run_case(case: str, env_extra: dict, db: str) -> subprocess.CompletedProcess:
    env = {**os.environ, "MONGODB_DB_NAME": db, "PYTHONIOENCODING": "utf-8", **env_extra}
    env.pop("MONITOR_SERVICE_URL", None)
    env.pop("GENERATOR_DEV_MODE", None)
    env.update(env_extra)
    return subprocess.run([sys.executable, __file__, "--case", case], env=env, cwd=str(BACKEND), capture_output=True, text=True, timeout=180)


# ------------------------------- in-subprocess cases -------------------------------
async def case_default() -> None:
    import api_server
    import httpx

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=api_server.app), base_url="http://t") as c:
        assert (await c.post("/api/dev/generate")).status_code == 404, "dev route must NOT exist by default"
        r = await c.post("/api/generate", json={"curriculum_id": "cur-1"})
        assert r.status_code == 412 and r.json()["detail"]["reason"] == "MONITOR_UNAVAILABLE", r.text
    assert not api_server._jobs
    print("default: /api/dev/generate absent (404); /api/generate -> 412 MONITOR_UNAVAILABLE; no job created")


async def case_dev() -> None:
    import api_server
    import httpx

    calls: list[str] = []

    async def recording_run_master(run_id=None):  # observation stand-in ONLY (see module docstring)
        calls.append(run_id)
        out = BACKEND / "output" / f"_wiring_{run_id}.docx"
        return out

    api_server.run_master = recording_run_master
    launched: list[tuple[str, str]] = []
    orig_new = api_server._new_job

    def spy_new(mode):
        job_id = orig_new(mode)
        launched.append((mode, job_id))
        return job_id

    api_server._new_job = spy_new

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=api_server.app), base_url="http://t") as c:
        # production route, Monitor not configured: gate refuses, the Generator core is never reached
        r = await c.post("/api/generate", json={"curriculum_id": "cur-1"})
        assert r.status_code == 412 and not calls and not launched, (r.status_code, calls, launched)

        # development route: same core (_new_job -> _start_job -> _execute -> run_master), no gate
        r = await c.post("/api/dev/generate")
        assert r.status_code == 200 and r.json()["mode"] == "development", r.text
        job_id = r.json()["job_id"]
        for _ in range(100):
            if api_server._jobs[job_id]["status"] != "running":
                break
            await asyncio.sleep(0.02)
        assert calls == [job_id], f"run_master not reached with the dev job id: {calls}"
        assert launched == [("development", job_id)]
        assert api_server._jobs[job_id]["mode"] == "development"
        st = (await c.get(f"/api/generate/{job_id}/status")).json()
        assert st["mode"] == "development"

        # a second dev request while one is active is refused exactly like production (409)
        api_server._active_job_id = "busy"
        assert (await c.post("/api/dev/generate")).status_code == 409
        api_server._active_job_id = None

        # production route is still gated after the dev route ran
        assert (await c.post("/api/generate", json={"curriculum_id": "cur-1"})).status_code == 412
        assert calls == [job_id]
    print("dev: /api/dev/generate -> _new_job('development') -> run_master(job) ; /api/generate still 412 and never reaches run_master; 409 while busy")


def case_dev_with_monitor() -> None:
    try:
        import api_server  # noqa: F401
    except RuntimeError as exc:
        assert "MONITOR_SERVICE_URL" in str(exc), exc
        print("dev+monitor: startup refused ->", str(exc)[:90])
        return
    raise AssertionError("GENERATOR_DEV_MODE with a configured Monitor must refuse to start")


# ------------------------------- static checks -------------------------------
def static_checks() -> None:
    src = (BACKEND / "api_server.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    run_master_users = [f.name for f in ast.walk(tree) if isinstance(f, (ast.AsyncFunctionDef, ast.FunctionDef))
                        for n in ast.walk(f) if isinstance(n, ast.Call) and getattr(n.func, "id", "") == "run_master"]
    assert run_master_users == ["_execute"], f"run_master must only be called by the shared _execute: {run_master_users}"
    creators = sorted({f.name for f in ast.walk(tree) if isinstance(f, (ast.AsyncFunctionDef, ast.FunctionDef))
                       for n in ast.walk(f) if isinstance(n, ast.Call) and getattr(n.func, "id", "") == "_new_job"})
    assert creators == ["dev_generate", "start_generate"], creators
    gate = src[src.index("async def start_generate"):src.index("_new_job(\"production\")")]
    assert "check_readiness" in gate and "status_code=412" in gate, "production gate code missing before job creation"
    dev = src[src.index("async def dev_generate"):]
    assert "check_readiness" not in dev.split("@app.get")[0], "dev route must not touch the Monitor client at all"

    offenders = []
    for root in (BACKEND / "api", BACKEND / "master_agent", BACKEND / "common", FRONTEND / "src"):
        for path in root.rglob("*"):
            if path.suffix in {".py", ".ts", ".tsx"} and "real_generate" in path.read_text(encoding="utf-8", errors="ignore"):
                offenders.append(str(path))
    assert "real_generate" not in src
    assert not offenders, offenders
    print("static: run_master only reachable via shared _execute; both routes create jobs via _new_job; dev route has no Monitor call; "
          "no web-path file references real_generate")


def main() -> None:
    static_checks()
    db = f"aunqa_ps_test_wire_{uuid.uuid4().hex[:8]}"
    try:
        for case, env, label in [("default", {}, "1  default process: dev route absent, production gate 412"),
                                 ("dev", {"GENERATOR_DEV_MODE": "true"}, "2  GENERATOR_DEV_MODE: dev route shares the Generator core; production gate intact"),
                                 ("dev_with_monitor", {"GENERATOR_DEV_MODE": "true", "MONITOR_SERVICE_URL": "http://monitor.invalid"},
                                  "3  dev mode refused when a Monitor is configured")]:
            r = _run_case(case, env, db)
            assert r.returncode == 0, f"{case} failed:\n{r.stdout[-800:]}\n{r.stderr[-1500:]}"
            print(f"TEST {label}: OK\n     {r.stdout.strip().splitlines()[-1]}")
        print("\nALL 3 dev-route wiring checks + static checks passed (real generation is proven by scripts/browser_e2e.py)")
    finally:
        from motor.motor_asyncio import AsyncIOMotorClient

        sys.path.insert(0, str(BACKEND))
        from common.config import Settings

        async def _drop():
            client = AsyncIOMotorClient(Settings().mongodb_uri)
            assert db.startswith("aunqa_ps_test_wire_")
            await client.drop_database(db)

        asyncio.run(_drop())


if __name__ == "__main__":
    if "--case" in sys.argv:
        sys.path.insert(0, str(BACKEND))
        which = sys.argv[sys.argv.index("--case") + 1]
        if which == "default":
            asyncio.run(case_default())
        elif which == "dev":
            asyncio.run(case_dev())
        else:
            case_dev_with_monitor()
    else:
        main()
