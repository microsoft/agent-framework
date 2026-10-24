# Get Started with Microsoft Agent Framework GitHub Copilot

Please install this package via pip:

```bash
pip install agent-framework-github-copilot
```

## GitHub Copilot Agent

The GitHub Copilot agent enables integration with GitHub Copilot, allowing you to interact with Copilot's agentic capabilities through the Agent Framework.

## Runtime connection configuration

`GitHubCopilotAgent` and `RawGitHubCopilotAgent` default to
`allow_runtime_connection_overrides=False`. Per-run `provider` and `mcp_servers`
options raise `AgentInvalidRequestException` before the agent starts the SDK client,
creates a session, or resumes one. This includes supplying a connection when no
default is configured, and clearing a configuration with an empty object or `None`.
Ordinary runtime options, such as `model` and `timeout`, remain supported.

Configure application-owned connections in `default_options`:

```python
from agent_framework.github import GitHubCopilotAgent, GitHubCopilotOptions

agent = GitHubCopilotAgent(
    default_options=GitHubCopilotOptions(
        provider={"type": "openai", "base_url": "https://application.example/v1"},
    ),
)
```

**Migration:** existing code passing `provider` or `mcp_servers` through
`run(options=...)` must move those settings to `default_options`, or explicitly
enable trusted runtime connection configuration:

```python
agent = GitHubCopilotAgent(allow_runtime_connection_overrides=True)
```

With opt-in, runtime connection options retain their existing precedence over
defaults. The flag is a constructor argument, not an SDK session option; it cannot
be enabled through the incoming options mapping. Apply the same policy to both
streaming and non-streaming calls. Applications opting in are responsible for
validating or filtering connection settings received over HTTP or from other
untrusted inputs.

## Tool approval (`approval_mode="always_require"`)

The GitHub Copilot SDK owns the tool-calling loop for this provider, so approval for
custom function tools is enforced through the SDK's native pre-execution hook rather
than the standard Agent Framework approval round-trip.

When you register a `FunctionTool` declared with `approval_mode="always_require"` and you
do **not** supply your own `on_pre_tool_use` hook, `GitHubCopilotAgent` installs a default
`on_pre_tool_use` hook that returns `"ask"` for that tool and defers (`None`) for all other
tools. The `"ask"` decision routes to your `on_permission_request` handler, where you
approve or deny the call. Other session hooks, such as `on_post_tool_use` or
`on_session_start`, are preserved alongside this default approval hook:

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

### Approving for the rest of the session

`PermissionDecisionApproveForSession` scopes its approval with either an `approval` (tool
prompts) or a `domain` (URL prompts). Both are optional, so a bare
`PermissionDecisionApproveForSession()` carries no scope at all and the Copilot CLI cannot
interpret it.

`GitHubCopilotAgent` therefore scopes such a decision automatically, using the request that
triggered it — a shell prompt becomes an approval for that prompt's command identifiers, an
MCP prompt an approval for that server and tool, a URL prompt an approval for that URL's
domain, and so on:

```python
from copilot.generated.rpc import PermissionDecisionApproveForSession


def on_permission_request(request, invocation):
    # Scoped to `request` automatically; approves that kind of call for the whole session.
    return PermissionDecisionApproveForSession()
```

The decision is only ever narrowed, never widened. When the prompt reports that it cannot
offer session-scoped approval (`can_offer_session_approval=False`), or the request kind has
no session-scoped approval at all (such as a `hook` prompt), the decision is downgraded to a
single-use approval and a warning is logged. Pass an explicit `approval=` or `domain=` when
you want to approve something other than the request being handled — decisions that already
specify a scope are forwarded unchanged.

### Deprecated: `on_function_approval`

The `on_function_approval` callback is **deprecated**. It still works (and is still enforced
inside the tool handler for backward compatibility), but it emits a `DeprecationWarning` and
will be removed in a future version. Migrate to the `on_pre_tool_use` + `on_permission_request`
model described above. When `on_function_approval` is set, it gates `always_require` tools and
the default ask-hook is not installed. It is **mutually exclusive** with `on_pre_tool_use` —
setting both (whether at construction or per run) raises `ValueError`.

## Workspace-driven session options

`on_permission_request` and `on_pre_tool_use` gate **tool calls**. They do not cover
configuration the CLI picks up from the working directory it runs in, which is a separate
mechanism with its own switches.

So that a session behaves the same way in every checkout, `GitHubCopilotAgent` leaves the
following off by default:

| Option | Default | Effect when enabled |
| --- | --- | --- |
| `enable_file_hooks` | `False` | The CLI loads file hooks from the working directory's `.github/hooks/` and runs the commands they define, independently of the tool-approval path. |

Opt in per agent or per run when your workflow needs the checkout to drive the session:

```python
agent = GitHubCopilotAgent(
    default_options=GitHubCopilotOptions(enable_file_hooks=True),
)
```

Only enable these for a working directory whose contents you trust to act on the host.

To make the default visible rather than silent, the agent logs a warning through the
`agent_framework.github_copilot` logger the first time it starts a session in a working
directory that defines hooks it is not loading. See
[`github_copilot_with_file_hooks.py`](../../samples/02-agents/providers/github_copilot/github_copilot_with_file_hooks.py)
for a runnable example.
