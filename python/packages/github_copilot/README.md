# Get Started with Microsoft Agent Framework GitHub Copilot

Please install this package via pip:

```bash
pip install agent-framework-github-copilot
```

## GitHub Copilot Agent

The GitHub Copilot agent enables integration with GitHub Copilot, allowing you to interact with Copilot's agentic capabilities through the Agent Framework.

The agent requires GitHub Copilot CLI version 1.0.85 or higher. When the agent starts, it checks the CLI version
and raises an error if the version is older or cannot be determined. This applies to the CLI bundled with the
`github-copilot-sdk` package as well as one selected with `cli_path`, `GITHUB_COPILOT_CLI_PATH`, or `COPILOT_CLI_PATH`.

## Context providers and function middleware

Context providers can contribute messages, instructions, and tools to a run.
`GitHubCopilotAgent` supports agent middleware, but the SDK owns its tool-calling loop
and does not run Agent Framework function middleware. If a context provider contributes
function middleware through `SessionContext.extend_middleware()`, the run raises
`MiddlewareException` before creating or resuming an SDK session or registering its tools.
This applies to both response modes and to `RawGitHubCopilotAgent`.

Use `Agent` with a chat client when provider-contributed function middleware is required.

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

`GitHubCopilotAgent` therefore scopes such a decision automatically when the request provides
a structured session approval — a shell prompt becomes an approval for that prompt's command
identifiers, an MCP prompt an approval for that server and tool, and so on:

```python
from copilot.generated.rpc import PermissionDecisionApproveForSession


def on_permission_request(request, invocation):
    # Scoped to `request` automatically; approves that kind of call for the whole session.
    return PermissionDecisionApproveForSession()
```

The decision is only ever narrowed, never widened. A bare decision for a URL prompt is
downgraded to a single-use approval because the framework cannot safely infer the Copilot
CLI's exact URL permission scope. The same downgrade occurs when the prompt reports that it
cannot offer session-scoped approval (`can_offer_session_approval=False`), or the request
kind has no session-scoped approval at all (such as a `hook` prompt). A warning is logged in
each case. Pass an explicit `approval=` or `domain=` when you want to approve a specific
scope for the session — decisions that already specify a scope are forwarded unchanged.

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

## MCP configuration and session lifetime

Constructor `default_options` provide SDK session defaults. Per-run `options` override
the corresponding defaults for that request, including `mcp_servers`. Reusing an
`AgentSession` with a `service_session_id` resumes SDK/CLI-owned service-session state.
Forwarding a narrower MCP configuration, such as changing a server's `tools` from
`["*"]` to `[]`, is not an authorization or revocation guarantee for capabilities
already resident in that session. Enforce authorization at the MCP service/tool boundary.

Use a fresh service session when narrowing configured capabilities: create
`fresh_session = agent.create_session()`, then pass it to
`await agent.run("Start a new conversation", session=fresh_session, options=restricted_options)`,
where `restricted_options` contains the narrowed `mcp_servers` configuration.
The new session has no `service_session_id`; do not copy the previous service-session
state or reuse its SDK `session_id` in constructor or per-run options. A fresh session
starts a new conversation rather than continuing the previous one.
