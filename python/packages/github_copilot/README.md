# Get Started with Microsoft Agent Framework GitHub Copilot

Please install this package via pip:

```bash
pip install agent-framework-github-copilot --pre
```

## GitHub Copilot Agent

The GitHub Copilot agent enables integration with GitHub Copilot, allowing you to interact with Copilot's agentic capabilities through the Agent Framework.

## Tool approval (`approval_mode="always_require"`)

The GitHub Copilot SDK owns the tool-calling loop for this provider, so approval for
custom function tools is enforced through the SDK's native pre-execution hook rather
than the standard Agent Framework approval round-trip.

When you register a `FunctionTool` declared with `approval_mode="always_require"` and you
do **not** supply your own `on_pre_tool_use` hook, `GitHubCopilotAgent` installs a default
`on_pre_tool_use` hook that returns `"ask"` for that tool and defers (`None`) for all other
tools. The `"ask"` decision routes to your `on_permission_request` handler, where you
approve or deny the call:

```python
from agent_framework import tool
from agent_framework.github import GitHubCopilotAgent, GitHubCopilotOptions
from copilot.session import PermissionHandler


@tool(approval_mode="always_require")
def delete_file(path: str) -> str:
    """Delete a file."""
    ...


agent = GitHubCopilotAgent(
    tools=[delete_file],
    # The "ask" decision is routed here; approve or deny the call.
    default_options=GitHubCopilotOptions(on_permission_request=PermissionHandler.approve_all),
)
```

> **⚠️ If you provide your own `on_pre_tool_use` hook**, it takes precedence and the agent
> does **not** install its default approval hook. In that case **you are fully responsible**
> for enforcing approval — including for any `approval_mode="always_require"` tool (e.g. by
> returning a `"deny"` or `"ask"` decision). The agent logs a warning naming any
> approval-required tool that your hook must handle.
>
> Note: with the default (deny-all) permission handler, an `always_require` tool is denied
> unless you wire an approving `on_permission_request`.

### Deprecated: `on_function_approval`

The `on_function_approval` callback is **deprecated**. It still works (and is still enforced
inside the tool handler for backward compatibility), but it emits a `DeprecationWarning` and
will be removed in a future version. Migrate to the `on_pre_tool_use` + `on_permission_request`
model described above. When `on_function_approval` is set, it gates `always_require` tools and
the default ask-hook is not installed. It is **mutually exclusive** with `on_pre_tool_use` —
setting both (whether at construction or per run) raises `ValueError`.

