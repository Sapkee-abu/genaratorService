"""MonitorClient - the ONE Generator-side abstraction for talking to the
Monitor Service's Readiness API (change.md "MONITOR INTEGRATION BOUNDARY"
sec.6 / "Fix and align ... real Monitor Readiness Contract" sec.5).

Real, confirmed contract (change.md sec.4):

    GET /monitor/{curriculumId}/readiness
    -> {"generatedReady": true}   or   {"generatedReady": false}

Responsibilities: take a curriculum_id, call that endpoint, parse the
response, and return a normalized MonitorReadinessResult - nothing more.
Explicitly NOT this class's job: evaluating PS-01..PS-09, reading
ps_requirements, querying MongoDB/ChromaDB, calling a Criterion Agent, or
inventing its own readiness/Greenlight decision (change.md sec.4/6/19). It
only ever relays what the real Monitor said, or reports that it couldn't
get a usable answer - never a fabricated READY (change.md sec.5: "Do not
silently convert unavailable/malformed responses to READY").
"""

from __future__ import annotations

import httpx

from common.config import get_settings
from monitor.schemas import MonitorExternalResponse, MonitorReadinessResult, MonitorReadinessStatus


class MonitorClient:
    def __init__(self, base_url: str | None = None, timeout: float | None = None) -> None:
        settings = get_settings()
        self._base_url = base_url if base_url is not None else settings.monitor_service_url
        self._readiness_path_template = settings.monitor_readiness_path
        self._timeout = timeout if timeout is not None else settings.monitor_timeout_seconds
        # monitor_auth_token exists in settings as a placeholder only - not
        # attached to requests yet (see common/config.py's docstring; the
        # real auth mechanism is unconfirmed).

    def _readiness_url(self, curriculum_id: str) -> str:
        path = self._readiness_path_template.format(curriculum_id=curriculum_id)
        return self._base_url.rstrip("/") + path

    async def check_readiness(self, curriculum_id: str) -> MonitorReadinessResult:
        """Never raises - every failure mode becomes a MonitorReadinessResult
        with the correct status, so callers only ever branch on `.status`.
        The gating decision itself is exactly: status == READY -> continue,
        anything else -> block (change.md sec.6) - no PS/threshold/role/
        guideline logic lives here or anywhere downstream of this method.
        """
        if get_settings().monitor_contract == "aunqa-portal":
            return await self._check_portal_readiness(curriculum_id)
        if not self._base_url:
            # No real Monitor configured at all - the honest state is
            # "can't reach it", never a fabricated READY.
            return MonitorReadinessResult(
                status=MonitorReadinessStatus.MONITOR_UNAVAILABLE,
                curriculum_id=curriculum_id,
                detail="MONITOR_SERVICE_URL is not configured",
            )

        url = self._readiness_url(curriculum_id)

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.get(url)
        except httpx.TimeoutException as exc:
            return MonitorReadinessResult(
                status=MonitorReadinessStatus.MONITOR_UNAVAILABLE,
                curriculum_id=curriculum_id,
                detail=f"Monitor request timed out after {self._timeout}s: {exc}",
            )
        except httpx.RequestError as exc:
            # Covers connection refused, DNS failure, network failure, etc. -
            # everything short of a received HTTP response.
            return MonitorReadinessResult(
                status=MonitorReadinessStatus.MONITOR_UNAVAILABLE,
                curriculum_id=curriculum_id,
                detail=f"Monitor connection failed ({type(exc).__name__}): {exc}",
            )

        if response.status_code >= 500:
            return MonitorReadinessResult(
                status=MonitorReadinessStatus.MONITOR_UNAVAILABLE,
                curriculum_id=curriculum_id,
                detail=f"Monitor returned HTTP {response.status_code}",
            )
        if response.status_code >= 400:
            # A 4xx here means the integration itself is misconfigured
            # (wrong endpoint, wrong method, rejected auth once that exists)
            # - not "Monitor evaluated the curriculum and said no" - so this
            # is an availability problem, never NOT_READY.
            return MonitorReadinessResult(
                status=MonitorReadinessStatus.MONITOR_UNAVAILABLE,
                curriculum_id=curriculum_id,
                detail=f"Monitor returned HTTP {response.status_code} (client-side integration error)",
            )

        try:
            raw = response.json()
        except ValueError as exc:
            return MonitorReadinessResult(
                status=MonitorReadinessStatus.INVALID_RESPONSE,
                curriculum_id=curriculum_id,
                detail=f"Monitor response was not valid JSON: {exc}",
            )

        if not isinstance(raw, dict):
            return MonitorReadinessResult(
                status=MonitorReadinessStatus.INVALID_RESPONSE,
                curriculum_id=curriculum_id,
                detail="Monitor response JSON was not an object",
            )

        try:
            external = MonitorExternalResponse.model_validate(raw)
        except Exception as exc:  # noqa: BLE001 - pydantic ValidationError, kept generic on purpose
            # Covers: missing "generatedReady", null, non-bool ("true"/1),
            # or an entirely different field name (change.md sec.9's full
            # malformed-response matrix) - all treated identically, never
            # assumed to mean READY or NOT_READY.
            return MonitorReadinessResult(
                status=MonitorReadinessStatus.INVALID_RESPONSE,
                curriculum_id=curriculum_id,
                detail=f"Monitor response missing/invalid 'generatedReady': {exc}",
                raw_response=raw,
            )

        status = MonitorReadinessStatus.READY if external.generatedReady else MonitorReadinessStatus.NOT_READY
        return MonitorReadinessResult(status=status, curriculum_id=curriculum_id, detail="", raw_response=raw)

    async def _check_portal_readiness(self, curriculum_id: str) -> MonitorReadinessResult:
        """Adapt IDs to Monitor's documented code-based, readiness-only contract.

        No PS rules are evaluated here. Only the Monitor's exact READY allows generation.
        The current Generator core supports one curriculum; ambiguous data is blocked.
        """
        from bson import ObjectId
        from common.mongo import get_db
        result = lambda status, detail, raw=None: MonitorReadinessResult(
            status=status, curriculum_id=curriculum_id, detail=detail, raw_response=raw)
        if not self._base_url:
            return result(MonitorReadinessStatus.MONITOR_UNAVAILABLE, "MONITOR_SERVICE_URL is not configured")
        try:
            db = get_db()
            if await db.curricula.count_documents({}) != 1:
                return result(MonitorReadinessStatus.NOT_READY, "Generator currently requires exactly one curriculum")
            curriculum = await db.curricula.find_one({"_id": ObjectId(curriculum_id)})
            if not curriculum or not curriculum.get("curriculumCode"):
                return result(MonitorReadinessStatus.NOT_READY, "Curriculum was not found")
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.get(self._base_url.rstrip('/') + '/api/monitor',
                                            params={"curriculumCode": curriculum['curriculumCode']})
            response.raise_for_status()
            raw = response.json()
        except Exception as exc:
            return result(MonitorReadinessStatus.MONITOR_UNAVAILABLE, f"Monitor integration unavailable ({type(exc).__name__})")
        if (not isinstance(raw, dict) or not isinstance(raw.get('generationReadiness'), dict)
                or 'status' not in raw['generationReadiness']):
            return result(MonitorReadinessStatus.INVALID_RESPONSE, "Monitor response has no generationReadiness")
        status = raw['generationReadiness'].get('status')
        if status == 'READY':
            return result(MonitorReadinessStatus.READY, "", raw)
        if status == 'NOT_READY' or status is None:
            return result(MonitorReadinessStatus.NOT_READY, "Monitor has not confirmed READY", raw)
        return result(MonitorReadinessStatus.INVALID_RESPONSE, "Unexpected readiness status", raw)
