"""Generator Service config (master_config.json): the per-criterion
specification - `name` and `evidence_top_k` (each criterion's content
differs, so each needs a different amount of evidence) - plus the order
criteria are generated in and the current academic year.

Served to the Master Agent through the MCP `get_master_config` tool; Master
validates what it receives with `validate_master_config` so a missing/
invalid field fails the run immediately with a clear message.

Holds no keywords (SRS FR-010: each Criterion Agent derives its own Data
Request from its Target Slots) and no guideline / required_evidence
(criterion rules and data completeness belong to Monitor's ps_requirements).
"""

from __future__ import annotations

import json
from pathlib import Path

from common.config import get_settings


class MasterConfigError(RuntimeError):
    pass


def read_master_config() -> dict:
    path = Path(get_settings().master_config_path)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise MasterConfigError(f"master_config.json not found at {path.resolve()}") from exc
    except json.JSONDecodeError as exc:
        raise MasterConfigError(f"master_config.json is not valid JSON: {exc}") from exc


def validate_master_config(config: dict) -> dict:
    """Returns `config` unchanged if valid, else raises MasterConfigError."""
    order = config.get("criterion_order")
    if not isinstance(order, list) or not order:
        raise MasterConfigError("criterion_order must be a non-empty list")

    criteria = config.get("criteria") or {}
    for code in order:
        entry = criteria.get(code)
        if not isinstance(entry, dict):
            raise MasterConfigError(f"criteria.{code} is missing (listed in criterion_order)")
        name = entry.get("name")
        if not isinstance(name, str) or not name.strip():
            raise MasterConfigError(f"criteria.{code}.name must be a non-empty string")
        top_k = entry.get("evidence_top_k")
        if not isinstance(top_k, int) or isinstance(top_k, bool) or top_k <= 0:
            raise MasterConfigError(f"criteria.{code}.evidence_top_k must be a positive integer")

    year = config.get("current_academic_year")
    if year is not None and not isinstance(year, int):
        raise MasterConfigError("current_academic_year must be an integer (B.E.)")

    return config
