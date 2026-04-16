# agent-framework-hyperlight

Alpha Hyperlight-backed CodeAct integrations for Microsoft Agent Framework.

## Installation

```bash
pip install agent-framework-hyperlight --pre
```

This package depends on `hyperlight-sandbox`, the packaged Python guest, and the
Wasm backend package on supported platforms. If the backend is not published for
your current platform yet, `execute_code` will fail at runtime when it tries to
create the sandbox.

## Quick start

### Context provider (recommended)

Use `HyperlightCodeActProvider` to automatically inject the `execute_code` tool
and CodeAct instructions into every agent run. Tools registered on the provider
are available inside the sandbox via `call_tool(...)` but are **not** exposed as
direct agent tools.

```python
from agent_framework import Agent, tool
from agent_framework_hyperlight import HyperlightCodeActProvider

@tool
def compute(operation: str, a: float, b: float) -> float:
    """Perform a math operation."""
    ops = {"add": a + b, "subtract": a - b, "multiply": a * b, "divide": a / b}
    return ops[operation]

codeact = HyperlightCodeActProvider(
    tools=[compute],
    approval_mode="never_require",
)

agent = Agent(
    client=client,
    name="CodeActAgent",
    instructions="You are a helpful assistant.",
    context_providers=[codeact],
)

result = await agent.run("Multiply 6 by 7 using execute_code.")
```

### Standalone tool

Use `HyperlightExecuteCodeTool` directly when you want full control over how the
tool is added to the agent. This is useful when mixing sandbox tools with
direct-only tools on the same agent.

```python
from agent_framework import Agent, tool
from agent_framework_hyperlight import HyperlightExecuteCodeTool

@tool
def send_email(to: str, subject: str, body: str) -> str:
    """Send an email (direct-only, not available inside the sandbox)."""
    return f"Email sent to {to}"

execute_code = HyperlightExecuteCodeTool(
    tools=[compute],
    approval_mode="never_require",
)

agent = Agent(
    client=client,
    name="MixedToolsAgent",
    instructions="You are a helpful assistant.",
    tools=[send_email, execute_code],
)
```

### Manual static wiring

For fixed configurations where provider lifecycle overhead is unnecessary, build
the CodeAct instructions once and pass them to the agent at construction time:

```python
execute_code = HyperlightExecuteCodeTool(
    tools=[compute],
    approval_mode="never_require",
)

codeact_instructions = execute_code.build_instructions(tools_visible_to_model=False)

agent = Agent(
    client=client,
    name="StaticWiringAgent",
    instructions=f"You are a helpful assistant.\n\n{codeact_instructions}",
    tools=[execute_code],
)
```

### File mounts and network access

Mount host directories into the sandbox and allow outbound HTTP to specific
domains:

```python
from agent_framework_hyperlight import HyperlightCodeActProvider, FileMount

codeact = HyperlightCodeActProvider(
    tools=[compute],
    file_mounts=[
        "/host/data",                                 # shorthand — same path in sandbox
        ("/host/models", "/sandbox/models"),           # explicit host → sandbox mapping
        FileMount("/host/config", "/sandbox/config"),  # named tuple
    ],
    allowed_domains=[
        "api.github.com",                             # all methods
        ("internal.api.example.com", "GET"),           # GET only
    ],
)
```

## Notes

- This package is intentionally separate from `agent-framework-core` so CodeAct
  usage and installation remain optional.
- Alpha-package samples live under `packages/hyperlight/samples/`.
- `file_mounts` accepts a single string shorthand, an explicit `(host_path,
  mount_path)` pair, or a `FileMount` named tuple. The host-side path in the
  explicit forms may be a `str` or `Path`. Use the explicit two-value form when
  the host path differs from the sandbox path.
- `allowed_domains` accepts a single string target such as `"github.com"` to
  allow all backend-supported methods, an explicit `(target, method_or_methods)`
  tuple such as `("github.com", "GET")`, or an `AllowedDomain` named tuple.
