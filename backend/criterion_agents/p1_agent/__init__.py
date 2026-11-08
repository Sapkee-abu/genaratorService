"""Re-exports this Criterion Agent's public interface from agent.py, so
`criterion_agents.registry` (and anything else) can do
`from criterion_agents import xx_agent` and call `xx_agent.run(...)` /
`xx_agent.build_data_request(...)` directly, without needing to know this
package's internal module layout.
"""

from .agent import CRITERION_CODE, AgentOutputError, build_data_request, run

__all__ = ["CRITERION_CODE", "AgentOutputError", "build_data_request", "run"]
