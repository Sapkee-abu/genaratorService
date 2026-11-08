"""Monitor Integration contract (change.md "Fix and align Generator Service
with the real Monitor Readiness Contract").

The real Monitor readiness contract is now confirmed (change.md sec.4):

    GET /monitor/{curriculumId}/readiness
    -> {"generatedReady": true}   or   {"generatedReady": false}

`generatedReady` must be a real JSON boolean - nothing else is accepted
(change.md sec.9/18: "prefer one clear contract over fallback parsing";
do not treat `ready`/`status`/`greenlight`/a non-bool `generatedReady` as
equivalent). `MonitorExternalResponse` models exactly this one field;
everything else in a response body is ignored, never required.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict


class MonitorReadinessStatus(str, Enum):
    """Internal readiness states. The gating DECISION is strictly binary
    (change.md sec.6: generatedReady == true -> READY, else -> BLOCKED) -
    NOT_READY / MONITOR_UNAVAILABLE / INVALID_RESPONSE all block generation
    identically. They stay distinct only so logs can tell *why* (change.md
    sec.16), never so Generator can compute its own readiness rule from
    them.
    """

    READY = "READY"
    NOT_READY = "NOT_READY"
    MONITOR_UNAVAILABLE = "MONITOR_UNAVAILABLE"
    INVALID_RESPONSE = "INVALID_RESPONSE"


class MonitorReadinessRequest(BaseModel):
    """What the Generator sends to check readiness - just a curriculum_id
    (change.md sec.11: single-curriculum system, no selector/second source
    of truth). This is the INTERNAL shape Generator code works with;
    `MonitorClient` is the only place that turns it into the real HTTP
    request (GET /monitor/{curriculumId}/readiness).
    """

    curriculum_id: str


class MonitorExternalResponse(BaseModel):
    """The raw shape Monitor's real HTTP API returns - exactly one required
    field. `model_config` still allows unknown extra fields (a real Monitor
    response carrying additional fields isn't itself a contract violation),
    but `generatedReady` must be present and must be a strict bool - pydantic
    would otherwise happily coerce "true"/1/"1" into True, which change.md
    sec.9 explicitly forbids ({"generatedReady": "true"} and
    {"generatedReady": 1} must both be rejected, not accepted).
    """

    model_config = ConfigDict(extra="allow", strict=True)

    generatedReady: bool


class MonitorReadinessResult(BaseModel):
    """The INTERNAL normalized result every caller in Generator actually
    branches on - never the raw external response. Built by
    `MonitorClient.check_readiness()`, the only place that touches
    `MonitorExternalResponse` at all.
    """

    status: MonitorReadinessStatus
    curriculum_id: str | None = None
    detail: str = ""  # human-readable reason - never a secret/token (change.md sec.16)
    raw_response: dict | None = None  # for logging/debugging only, never assumed structured

    @property
    def is_ready(self) -> bool:
        return self.status == MonitorReadinessStatus.READY
