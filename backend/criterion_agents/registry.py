"""Criterion Agent registry: maps a criterion_code (from master_config.json's
`criterion_order`) to its own agent module (change.md sec.5 - PS/P1/P2/P3/
P4/P8 must be separate Agents, not one generic agent with a changing
prompt). master.py dispatches through this instead of importing/calling one
shared function directly, so FAIL -> retry always lands back on the exact
same Agent module that produced the Result JSON (change.md sec.11: "Do NOT
switch to another Criterion Agent").
"""

from __future__ import annotations

from types import ModuleType

from criterion_agents import p1_agent, p2_agent, p3_agent, p4_agent, p8_agent, ps_agent

AGENTS: dict[str, ModuleType] = {
    "PS": ps_agent,
    "P1": p1_agent,
    "P2": p2_agent,
    "P3": p3_agent,
    "P4": p4_agent,
    "P8": p8_agent,
}


def get_agent(criterion_code: str) -> ModuleType:
    try:
        return AGENTS[criterion_code]
    except KeyError as exc:
        raise KeyError(
            f"No Criterion Agent registered for '{criterion_code}' - "
            f"known agents: {sorted(AGENTS)}"
        ) from exc
