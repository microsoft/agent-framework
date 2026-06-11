---
status: proposed
contact: evmattso
date: 2026-04-10
deciders: evmattso
---

# Foundry Toolbox Support in FoundryChatClient

## What is the goal of this feature?

Enable Agent Framework users to consume Foundry **toolboxes** — named, versioned bundles of tool definitions stored server-side in an Azure AI Foundry project — directly from `FoundryChatClient`, without dropping to the raw `azure-ai-projects` SDK.

A user who has configured a toolbox in the Foundry portal (or via the raw SDK) should be able to load it into an agent with a single call:

```python
toolbox = await client.get_toolbox("research_tools")
agent = Agent(client=client, instructions="...", tools=toolbox)
```

**Success metric:** an agent can consume a toolbox with no manual handling of version-resolution logic on the user's side.

## What is the problem being solved?

`azure-ai-projects==2.1.0a20260409002` ships a new `BetaToolboxesOperations` surface, reachable as `AIProjectClient.beta.toolboxes` on the raw SDK client (and therefore as `FoundryChatClient.project_client.beta.toolboxes` through our wrapper), that lets teams:
- Group related hosted tools (code interpreter, file search, MCP, web search, etc.) under a named toolbox
- Version toolboxes immutably, so agents can pin to a specific configuration for production stability
- Share toolboxes across multiple agents in a project

However, consuming a toolbox from the framework today requires:
1. Knowing the raw SDK accessor path (`client.project_client.beta.toolboxes`)
2. Making two calls for the common case — `.get(name)` to find the default version, then `.get_version(name, version)` to actually retrieve tools
3. Manually unpacking `toolbox.tools` before passing them to `Agent(tools=...)`

None of this is hard, but it's the kind of boilerplate that should live in the client. Every other hosted tool in `FoundryChatClient` (code interpreter, file search, web search, image generation, MCP) already has a factory method (`get_code_interpreter_tool()`, etc.). Toolbox support should fit the same shape on the chat-client composition surface.

## API Changes

### One new method on the FoundryChatClient surface

The public toolbox-consumption surface lands on:

- `RawFoundryChatClient` (inherited by `FoundryChatClient`) in `_chat_client.py`

The implementation delegates to shared helper functions in `_tools.py` so there is a single source of truth for the SDK calls.

**Scope note:** `FoundryAgent` is intentionally not part of this design. `FoundryAgent` is the runtime surface for invoking an already-configured server-side Foundry agent; if that agent should use a toolbox, the toolbox/tools should already be configured on the Foundry side (UI or `azure-ai-projects` authoring flow) before MAF connects to it.

**Scope note:** Authoring a server-side agent whose definition references a toolbox (via `PromptAgentDefinition(tools=toolbox.tools, ...)` + `client.agents.create_version(...)`) is deliberately outside MAF scope. That is an `azure-ai-projects` / service-resource authoring concern, not a future MAF feature. Users who need it should use the raw Azure SDK directly.

```python
async def get_toolbox(
    self,
    name: str,
    *,
    version: str | None = None,
) -> ToolboxVersionObject:
    """Fetch a Foundry toolbox by name.

    If ``version`` is ``None``, resolves the toolbox's current default version
    (two requests). If ``version`` is specified, fetches that version directly
    (single request).

    :param name: The name of the toolbox.
    :param version: Optional immutable version identifier to pin to.
    :return: A ``ToolboxVersionObject``. Pass its ``tools`` attribute to
        ``Agent(tools=toolbox.tools)``.
    :raises azure.core.exceptions.ResourceNotFoundError: If the toolbox or
        version does not exist.
    """

```

### Return types: raw SDK models, no custom wrappers

Methods return the `azure.ai.projects.models` types directly:

- `get_toolbox()` → `ToolboxVersionObject` (has `.name`, `.version`, `.tools`, `.id`, `.created_at`, `.description`, `.metadata`, `.policies`)

No custom wrapper classes are defined. Returning the SDK types directly:
- Eliminates maintenance overhead of keeping a custom wrapper aligned with SDK changes
- Matches the existing convention — `get_code_interpreter_tool()` returns the raw `CodeInterpreterTool` SDK type
- Means any new fields the SDK adds to these types flow through automatically

`Agent(..., tools=...)` will accept the fetched toolbox object directly by flattening to `toolbox.tools` internally.

### Design decisions

**Instance methods, not `@staticmethod` factories.** Existing `get_code_interpreter_tool()` / `get_mcp_tool()` / etc. are `@staticmethod` because they're pure factories with no network I/O. Toolbox fetching requires the project client, so these new methods must be instance methods. This is a deliberate departure from the existing-factory pattern, justified by the async-with-I/O nature of the operation.

**Raw SDK type passthrough (no custom wrappers).** There is only one toolbox type in the Foundry SDK and maintaining a shadow wrapper would create alignment risk as the SDK evolves. The raw `ToolboxVersionObject` and `ToolboxObject` carry all the fields users need. Individual tools inside `toolbox.tools` are the same `azure.ai.projects.models.Tool` subclasses returned by other factory methods.

**Two-request default-version path.** When `version=None`, implementation calls `.get(name)` to find `default_version`, then `.get_version(name, default_version)` for the tools. Caching the default-version mapping was considered and rejected — default versions can change server-side via `update(default_version=...)`, and a stale cache would silently give callers the wrong tools. Two requests at agent setup is acceptable.

**No discovery/listing surface in MAF.** Discovery is intentionally left to the raw `azure-ai-projects` client. MAF does not currently expose project-resource listing surfaces for many other Foundry resources (deployments, vector stores, agents, etc.), so the toolbox design stays narrowly focused on explicit retrieval by name/version.

**Shared helpers in `_tools.py`.** The SDK-call helper function (`fetch_toolbox`) lives in a shared module so the chat-client surface stays thin and the request logic remains centralized.

**`tools=toolbox` convenience, not a new wrapper type.** Although `get_toolbox()` returns the raw `ToolboxVersionObject`, Agent Framework can still support `tools=toolbox` / `tools=[toolbox]` by flattening the toolbox's `.tools` internally. That matches existing SDK ergonomics where some higher-level objects can be placed directly in `tools=` and unpacked underneath, without introducing a public `FoundryToolbox` wrapper.

**Errors pass through unchanged.** `ResourceNotFoundError`, `HttpResponseError`, etc. from the SDK propagate as-is. No framework-specific exception hierarchy.

## E2E Code Samples

### Primary sample

New file: `samples/02-agents/providers/foundry/foundry_chat_client_with_toolbox.py`

```python
import asyncio

from agent_framework import Agent
from agent_framework.foundry import FoundryChatClient
from azure.identity import AzureCliCredential


async def main() -> None:
    client = FoundryChatClient(credential=AzureCliCredential())

    toolbox = await client.get_toolbox("research_tools")
    print(f"Loaded toolbox {toolbox.name}@{toolbox.version} ({len(toolbox.tools)} tools)")

    agent = Agent(
        client=client,
        instructions="You are a research assistant.",
        tools=toolbox,
    )

    result = await agent.run("What are the latest developments in quantum error correction?")
    print(f"Result: {result}")


if __name__ == "__main__":
    asyncio.run(main())
```

### Version pinning

```python
toolbox = await client.get_toolbox("research_tools", version="v3")
```

### Combining multiple toolboxes

```python
toolbox_a = await client.get_toolbox("research_tools")
toolbox_b = await client.get_toolbox("some_other_tools", version="v3")

agent = Agent(
    client=client,
    instructions="...",
    tools=[toolbox_a, toolbox_b],
)
```

### Combining toolbox tools with locally defined tools

```python
toolbox = await client.get_toolbox("research_tools")

def get_internal_metrics(metric_name: str) -> dict:
    """Custom tool that reads from an internal dashboard."""
    ...

agent = Agent(
    client=client,
    instructions="...",
    tools=[get_internal_metrics, toolbox],
)
```

### Selecting only some tools from a toolbox

Developers will not always want to pass the entire toolbox through unchanged. A
small helper in the Foundry package provides local post-fetch selection without
changing the raw return type of `get_toolbox()`.

```python
from agent_framework.foundry import select_toolbox_tools

toolbox = await client.get_toolbox("research_tools")

selected_tools = select_toolbox_tools(
    toolbox,
    include_names=["githubmcp", "code_interpreter"],
)

agent = Agent(
    client=client,
    instructions="Use only the selected toolbox tools.",
    tools=selected_tools,
)
```

Supported filters:

```python
from agent_framework.foundry import FoundryHostedToolType, select_toolbox_tools

selected_tools = select_toolbox_tools(
    toolbox,
    include_types=["mcp", "code_interpreter"],  # type: Collection[FoundryHostedToolType]
    exclude_names=["internal_admin_tool"],
)
```

Helper signature:

```python
type FoundryHostedToolType = Literal[
    "code_interpreter",
    "file_search",
    "image_generation",
    "mcp",
    "web_search",
] | str

def select_toolbox_tools(
    tools: ToolboxVersionObject | Sequence[Tool | dict[str, Any]],
    *,
    include_names: Collection[str] | None = None,
    exclude_names: Collection[str] | None = None,
    include_types: Collection[FoundryHostedToolType] | None = None,
    exclude_types: Collection[FoundryHostedToolType] | None = None,
    predicate: Callable[[Tool | dict[str, Any]], bool] | None = None,
) -> list[Tool | dict[str, Any]]:
    ...
```

Normalized name precedence for `include_names` / `exclude_names`:

1. MCP `server_label`
2. generic tool `name`
3. fallback tool `type`

This keeps `get_toolbox()` as a thin fetch API and makes selection an explicit,
local post-processing step, while still allowing the ergonomic
`select_toolbox_tools(toolbox, ...)` call shape.

## Native vs MCP consumption of a Foundry toolbox

A Foundry toolbox can be consumed two ways. This design adds new implementation work only for the first:

1. **Native consumption (in scope).** Tools execute inside Foundry's agent runtime. `get_toolbox()` returns the `ToolboxVersionObject` whose `.tools` attribute carries typed tool configs that the runtime interprets server-side. This design is specifically for `FoundryChatClient`-backed local agent composition.

2. **MCP consumption (already supported through existing MCP abstractions).** A Foundry toolbox can also be exposed as an MCP server. In that case, use the existing `MCPStreamableHTTPTool(name=..., url=...)` — it already handles this path with any chat client (Foundry, OpenAI, Anthropic, etc.). No new Foundry-specific API is needed for MCP-exposed toolboxes in this design.

### MCPStreamableHTTPTool example for a Foundry toolbox endpoint

If Foundry gives you an MCP endpoint for the toolbox (for example from the
toolbox details UI / endpoint surface), the existing MCP client path is:

```python
from agent_framework import Agent, MCPStreamableHTTPTool
from agent_framework.openai import OpenAIChatClient

toolbox_mcp = MCPStreamableHTTPTool(
    name="research_tools",
    url="https://<foundry-toolbox-mcp-endpoint>",
)

agent = Agent(
    client=OpenAIChatClient(),
    instructions="You are a research assistant.",
    tools=[toolbox_mcp],
)
```

This is a different integration shape than `get_toolbox(...).tools`:

- `get_toolbox(...).tools` = **native Foundry hosted-tool configs** interpreted by the
  Foundry runtime
- `MCPStreamableHTTPTool(name=..., url=...)` = **live MCP server connection** to a
  toolbox endpoint

The design in this spec adds first-class support only for the native hosted-tool
path. The MCP path is already served by the framework's existing MCP abstractions.

These paths are not unified because they have fundamentally different execution models. Native toolbox tools are declarative configs the Foundry runtime executes; MCP consumption is a live wire protocol to a running server.

**MCP authentication inside a toolbox** is handled server-side via `project_connection_id` on individual `MCPTool` entries (OAuth connection objects configured in the Foundry project). The client never holds bearer tokens. Consent flow handling (`CONSENT_REQUIRED` → user-visible consent URL) happens during `agent.run()`, not during toolbox fetching — see Non-goals.

## Testing Strategy

Unit tests in `packages/foundry/tests/test_toolbox.py` with mocked `project_client.beta.toolboxes`. A single opt-in live round-trip, `test_integration_get_toolbox_round_trip_against_real_project`, is marked `@pytest.mark.integration`; it is skipped by default and only runs when the required Foundry credentials are available.

Coverage:

- `get_toolbox(name, version="v3")` — explicit version, single request. Assert `.get` not called, `.get_version` awaited once, returns `ToolboxVersionObject`.
- `get_toolbox(name)` — default-version resolution. Assert `.get` then `.get_version` called in order with correct args.
- Error propagation — `ResourceNotFoundError` from `.get` propagates unchanged.
- Tool passthrough — heterogeneous tool list (`CodeInterpreterTool`, `MCPTool(project_connection_id=...)`) passes through unchanged. Asserts `project_connection_id` survives.
- Agent integration smoke — `tools=toolbox` / `tools=[toolbox]` flatten to the underlying toolbox tools.
- Multiple toolbox composition smoke — `tools=[toolbox_a, toolbox_b]` flattens into a single agent tool list.
- `get_toolbox_tool_name()` — selection-name precedence is MCP `server_label`, then `name`, then `type`.
- `select_toolbox_tools(toolbox, include_names=...)` — selects by normalized tool names directly from a fetched toolbox object.
- `select_toolbox_tools(toolbox, include_types=...)` — selects by tool types with `Literal`-guided IDE completion.
- `select_toolbox_tools(..., exclude_names=..., predicate=...)` — supports exclusion + custom predicates.

Deliberately **not** covered:
- Runtime consent-flow handling for OAuth MCP tools (see Non-goals).
- Toolbox discovery/listing (`list_toolboxes`, `list_toolbox_versions`) — deliberately left to the raw Azure SDK.
- Full CRUD (`create_version`, `update`, `delete`) and server-side agent authoring — see Non-goals.

Live Foundry API integration is exercised only through the opt-in `@pytest.mark.integration` round-trip noted above; it is not part of the default test run.

## Framework dependency: `normalize_tools` flattening

The core `normalize_tools` function in `packages/core/agent_framework/_tools.py` already supports flattening composite tool inputs. Toolbox support extends that behavior so a fetched `ToolboxVersionObject` is treated as a composite tool source and flattened to its `.tools`.

That enables:

- `tools=toolbox`
- `tools=[toolbox]`
- `tools=[local_tool, toolbox]`
- `tools=[toolbox_a, toolbox_b]`

while still keeping `select_toolbox_tools(toolbox.tools, ...)` available for partial selection before the final agent construction step.

## Telemetry

Telemetry for toolbox support has two separate goals:

1. **Observe toolbox API access** — `get_toolbox()`
2. **Observe toolbox usage during agent runs** — when users pass toolbox-derived tools into `Agent(..., tools=...)`

### Request telemetry for toolbox API access

When Agent Framework constructs the `AIProjectClient` internally for `FoundryChatClient`, it already sets:

```python
user_agent=AGENT_FRAMEWORK_USER_AGENT
```

That means toolbox API requests made through:

- `project_client.beta.toolboxes.get(...)`
- `project_client.beta.toolboxes.get_version(...)`

carry the standard MAF user-agent marker and can be queried in backend request logs the same way as other Foundry SDK calls made through framework-owned clients.

Important constraint: if the caller passes an already-constructed `project_client`, Agent Framework does **not** mutate it to inject the MAF user-agent. In that case, toolbox API request telemetry reflects whatever user-agent behavior that external client was configured with.

### Runtime telemetry for toolbox usage on agent runs

Tool-level telemetry already captures which hosted Foundry tools are available / invoked during agent execution. The remaining gap is **toolbox provenance**: once the user writes `tools=toolbox` (or otherwise flattens the toolbox into tool configs), the framework sees only raw tool configs and no longer knows which toolbox name/version supplied them.

The design for closing the **client-side** observability gap is **internal provenance tracking**, not user-supplied metadata and not a new public wrapper type.

#### Provenance model

Note: this section is still under investigation.

When `get_toolbox()` or `list_toolbox_versions()` returns a `ToolboxVersionObject`, Agent Framework will attach private provenance metadata to:

- the returned toolbox object
- each tool inside `toolbox.tools`

Recommended shape (private, internal-only):

```python
tool._maf_toolbox_sources = [
    {
        "id": toolbox.id,
        "name": toolbox.name,
        "version": toolbox.version,
    }
]
```

Key properties of this approach:

- **No new public API surface** — users still work with raw `ToolboxVersionObject` / `ToolboxObject`
- **No user burden** — callers do not need to stamp metadata manually
- **Provenance follows the tool objects** — works with:
  - `tools=toolbox.tools`
  - `tools=[toolbox_a.tools, toolbox_b.tools]`
  - `tools=[*toolbox_a.tools, *toolbox_b.tools]`
- **Private attributes are not serialized** into the actual request payload sent to the model/service, so this metadata does not leak into the tool definition body

This is intentionally preferred over introducing a new public `FoundryToolbox` wrapper purely for telemetry, and preferred over a separate global provenance registry. The provenance lives on the existing tool objects so list-copying and chat-option merging naturally preserve it.

#### Span enrichment

When Agent / chat telemetry computes span attributes for a run, it should inspect the final tool list and aggregate the private toolbox provenance from any tool objects that carry it. The aggregated values are then emitted as attributes on the existing run/chat spans.

Suggested custom attributes:

- `agent_framework.foundry.toolbox.ids`
- `agent_framework.foundry.toolbox.names`
- `agent_framework.foundry.toolbox.versions`
- or a single compact attribute such as `agent_framework.foundry.toolbox.sources=["research_tools@1","some_other_tools@3"]`

The single compact `toolbox.sources` form is preferred for initial implementation because it is easy to query and easy to render from combined tool lists.

#### Scope of telemetry changes

This design does **not** require new spans. It enriches existing telemetry:

- toolbox API access continues to rely on request logs + Azure SDK distributed tracing + MAF user-agent
- agent/chat execution spans gain toolbox provenance attributes when toolbox-derived tools are present

Implementation-wise, this design most likely touches:

- `packages/foundry/agent_framework_foundry/_tools.py` — to stamp provenance on fetched toolbox objects / tools
- `packages/core/agent_framework/observability.py` — to aggregate provenance into span attributes

#### Important limitation: no server-side toolbox telemetry solution yet

Private provenance attached to tool objects is only useful on the client side. It
does **not** go over the wire to the Foundry service because those private fields
are intentionally not serialized into the request payload.

That means this design can support:

- local OpenTelemetry / exporter spans emitted by Agent Framework
- local attribution of a run to one or more fetched toolboxes

but it does **not** solve:

- server-side request-log attribution of a model/tool run back to a toolbox
- backend/database queries that need the service itself to know "this tool came from toolbox X"

At the moment, we do not have a satisfactory design for server-side toolbox
telemetry. The service would require additional structured information on the
request, and there is no accepted mechanism in this design yet for projecting
toolbox provenance into a server-visible field/header/metadata shape.

So the telemetry story in this spec is explicitly limited to **client-side
toolbox telemetry**. Server-side toolbox attribution remains an open question and
requires either:

- new service/API support, or
- a later framework design for emitting additional server-visible request metadata.

#### Deliberate non-goals for telemetry

- No requirement for users to pass explicit toolbox metadata in `default_options["metadata"]` or `run(..., options=...)`
- No new public `FoundryToolbox` wrapper type just to preserve attribution
- No attempted server-side attribution mechanism in this design (for example a custom request header or request metadata field) until there is a validated end-to-end contract for it

## Non-goals / Future Work

Explicitly out of scope for this design. Each is a separate design and PR when needed.

1. **Create/update/delete toolboxes from code.** CRUD is rare in agent consumption flows. Users who need it drop to `client.project_client.beta.toolboxes.create_version(...)`, `.update(...)`, `.delete(...)` directly.

2. **Server-side agent authoring from toolbox.** Creating a `PromptAgentDefinition(tools=toolbox.tools)` + `client.agents.create_version(...)` is a future feature covering agent authoring from code. The toolbox read API provides the building blocks; the authoring helpers are a separate design.

3. **OAuth consent-flow runtime handling.** When a toolbox contains MCP tools with `project_connection_id` pointing to an OAuth connection, the runtime may return `CONSENT_REQUIRED` mid-run. This is a runtime concern separate from toolbox fetching.

4. **Live integration tests.** This PR ships unit tests only.

5. **Toolbox caching or refresh APIs.** Each `get_toolbox()` call hits the network. Users who want caching wrap the call themselves.
