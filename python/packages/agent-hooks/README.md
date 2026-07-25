# Agent Framework Agent Hooks Middleware

Implements [AGENT-HOOKS-0.1](https://github.com/responsibleai/agent-hooks),
a framework-neutral control contract for AI agents, on Agent Framework's
middleware pipeline. Any agent-hooks interceptor (policy engine, approval
flow, egress guard, audit pipeline) plugs into an Agent Framework agent
without framework-specific glue, with the contract's fail-closed
semantics: a deny stops the action, a transform rewrites exactly what
executes, and errors terminate rather than fall through.

## Installation

```bash
pip install agent-framework-agent-hooks
```

## Usage

```python
from agent_framework import Agent
from agent_framework_agent_hooks import agent_hooks_middleware
from agent_hooks import Decision, Verdict


class EgressGuard:
    def intercept(self, context):
        if context["interception_point"] != "pre_tool_call":
            return {"decision": "allow"}
        if "confidential" in str(context["target"]):
            return {"decision": "deny", "reason": "egress_blocked"}
        return {"decision": "allow"}


agent = Agent(
    client=client,
    name="assistant",
    middleware=agent_hooks_middleware([EgressGuard()]),
)
```

One agent run is one agent-hooks session: `agent_startup` and
`agent_shutdown` bracket the run, `input`/`output` wrap it, and every
model and tool call gets its pre/post interception point. Composition
profiles, the approval seam, identity providers, and interception
records follow the published `agent-hooks-sdk` package; see
[MAPPING.md](MAPPING.md) for the seam mapping and known gaps
(streaming post-action points, session-scoped brackets).

Trust model: agent-hooks is a cooperative contract, not a security
boundary; the host process and registered interceptors are fully
trusted. See the
[specification](https://github.com/responsibleai/agent-hooks) for the
normative statement.
