---
status: proposed
contact: ShrayRastogi
date: 2026-03-22
deciders: markwallace-microsoft, javiercn, westey-m
informed: Agent Framework community
---

# AG-UI Permission Events for Copilot SDK MCP Tool Calls

## Context and Problem Statement

When using `GitHubCopilotAgent` with `MapAGUI` to serve an AG-UI endpoint, MCP tool calls triggered by the Copilot SDK are completely invisible to AG-UI clients. The Copilot SDK fires `OnPermissionRequest` callbacks for tool executions (MCP, shell, write, read, url, custom-tool), but these are handled entirely server-side. No `TOOL_CALL_*` or human-in-the-loop events reach the AG-UI SSE stream.

This means:
- **No tool visibility**: Clients cannot see which MCP tools are being called or with what arguments
- **No human-in-the-loop**: Clients cannot approve or deny tool calls through the AG-UI protocol
- **Forced auto-approve**: The only option is `PermissionHandler.ApproveAll` — no interactive approval path exists

See [Issue #4826](https://github.com/microsoft/agent-framework/issues/4826).

## Decision Drivers

- AG-UI clients must have visibility into MCP tool executions
- Human-in-the-loop approval must work with any AG-UI client, not just CopilotKit
- Solution must be backward compatible — existing `OnPermissionRequest` handlers must continue to work
- Must not introduce a dependency from `GitHubCopilotAgent` package to the AG-UI hosting package
- Should reuse existing AG-UI event types (`TOOL_CALL_*`) where possible and extend with `CUSTOM` events only where necessary
- Must align with the existing `ServerFunctionApprovalAgent` pattern for .NET tools (ADR-0006)

## Considered Options

1. **Intercept via `OnPermissionRequest` callback wrapper** — Wrap the user's `OnPermissionRequest` handler in `GitHubCopilotAgent` to emit `FunctionCallContent`/`FunctionResultContent` into the streaming channel
2. **Intercept via `session.On()` default branch** — Catch `permission.requested` events in the session event handler's `default` branch
3. **Use AG-UI Interrupt draft proposal** — Implement the draft `RUN_FINISHED { outcome: "interrupt" }` pattern
4. **Create a `DelegatingAIAgent` wrapper** — Similar to `ServerFunctionApprovalAgent`, create an `McpToolApprovalAgent` decorator

## Decision Outcome

Chosen option: **Option 1 — Intercept via `OnPermissionRequest` callback wrapper**, because:

- It is the only reliable access point for permission data in the Copilot SDK — the `OnPermissionRequest` callback is guaranteed to fire before tool execution and provides a blocking `Task<PermissionRequestResult>` return that can be awaited for HITL
- The existing `AsAGUIEventStreamAsync()` pipeline already converts `FunctionCallContent` → `TOOL_CALL_START/ARGS/END` and `FunctionResultContent` → `TOOL_CALL_RESULT`, so no AG-UI pipeline changes are needed for Phase 1 (visibility)
- Option 2 was rejected because `permission.requested` events in the `default` branch are informational only — they cannot block execution or return approval decisions
- Option 3 was rejected because the AG-UI interrupt proposal is still in draft status and may change
- Option 4 was rejected because MCP tools are managed by the Copilot SDK, not by the framework — `DelegatingAIAgent` cannot intercept them

### Implementation

The implementation has two phases that can ship independently:

**Phase 1 — Tool Call Visibility (no approval):**
- Channel creation is moved before `SessionConfig` copy so the `OnPermissionRequest` closure can write to it
- `CopySessionConfigWithPermissionEmitter()` wraps the user's `OnPermissionRequest` to emit `FunctionCallContent` (before tool execution) and `FunctionResultContent` (after permission decision) into the channel
- The existing AG-UI pipeline converts these to `TOOL_CALL_START/ARGS/END/RESULT` SSE events with zero changes to the AG-UI layer
- When `OnPermissionRequest` is `null`, no wrapper is injected — exact current behavior preserved

**Phase 2 — Human-in-the-Loop Approval:**
- AG-UI `CUSTOM` event type added to the framework (official AG-UI spec, not draft)
- `PendingApprovalStore` service stores `TaskCompletionSource<bool>` entries with configurable timeout
- When the HITL delegate is present (provided by `MapAGUI` via `AgentRunOptions.AdditionalProperties`), the wrapper blocks on the TCS instead of forwarding to the original handler
- `CUSTOM` events (`tool_approval_requested`, `tool_approval_completed`) are emitted alongside `TOOL_CALL_*` events
- `POST {pattern}/approve` endpoint registered by `MapAGUI` resolves the TCS
- The `Func<string, Task<bool>>` delegate bridges `GitHubCopilotAgent` and `PendingApprovalStore` without introducing cross-package dependencies

### Consequences

- Good, because existing `OnPermissionRequest` handlers (including `PermissionHandler.ApproveAll` and console prompts) continue to work unchanged with added TOOL_CALL visibility
- Good, because any AG-UI client can consume `TOOL_CALL_*` and `CUSTOM` events — not tied to CopilotKit
- Good, because the `CUSTOM` event type is a reusable addition to the AG-UI layer for future extensibility
- Good, because typed `PermissionRequest` subclasses (`PermissionRequestMcp`, `PermissionRequestShell`, etc.) provide rich metadata in tool call arguments
- Neutral, because the HITL delegate is passed through `AdditionalProperties` (stringly-typed key) rather than a constructor parameter — less discoverable but avoids public API surface changes
- Bad, because the `PendingApprovalStore` is an in-memory singleton — not suitable for multi-instance deployments without external state

## Validation

- All 450 existing unit tests pass across net8.0, net9.0, net10.0
- End-to-end testing confirmed with CopilotKit as AG-UI client:
  - `TOOL_CALL_START/ARGS/END` events appear on SSE stream for MCP tool calls
  - `CUSTOM tool_approval_requested` event triggers client-side approval UI
  - `POST /approve` unblocks server-side `PendingApprovalStore` and resumes tool execution
  - 60-second timeout auto-denies when client doesn't respond
- Backward compatibility verified: `Agent_With_GitHubCopilot` sample works unchanged

## Pros and Cons of the Options

### Option 1: OnPermissionRequest callback wrapper (chosen)

- Good, because it provides both visibility and blocking approval in one mechanism
- Good, because the existing AG-UI pipeline (`AsAGUIEventStreamAsync`) handles `FunctionCallContent` → `TOOL_CALL_*` automatically
- Good, because it works for all permission kinds (mcp, shell, write, read, url, custom-tool)
- Neutral, because it requires restructuring channel creation order in `RunCoreStreamingAsync`
- Neutral, because in HITL mode the server-side `OnPermissionRequest` callback is replaced by the AG-UI client's approve/deny decision — the callback is still required to be non-null (to activate the wrapper), but the actual approval comes from the end user via `POST /approve`

### Option 2: session.On() default branch interception

- Good, because it requires minimal code changes
- Bad, because `permission.requested` events in the default branch are read-only — cannot block or return decisions
- Bad, because event types are opaque (`SessionEvent` base class) without strongly-typed properties

### Option 3: AG-UI Interrupt draft proposal

- Good, because it's a standardized approach designed for exactly this use case
- Bad, because the interrupt spec is still in draft status and may change before finalization
- Bad, because it would modify `RUN_FINISHED` semantics and require `RunAgentInput.resume` support

### Option 4: DelegatingAIAgent wrapper (McpToolApprovalAgent)

- Good, because it follows the established `ServerFunctionApprovalAgent` pattern
- Bad, because MCP tools are managed by the Copilot SDK process, not by the framework — the wrapper never sees them
- Bad, because it adds an extra layer of indirection for all agent operations

## More Information

- [AG-UI Protocol Events Spec](https://docs.ag-ui.com/concepts/events) — defines `CUSTOM` as an official "Special Event"
- [AG-UI Interrupt Draft](https://docs.ag-ui.com/drafts/interrupts) — future alternative when stabilized
- [ADR-0006: User Approval](docs/decisions/0006-userapproval.md) — related decision on `ToolApprovalRequestContent` types
- [ADR-0010: AG-UI Support](docs/decisions/0010-ag-ui-support.md) — AG-UI protocol integration decision
- [Copilot SDK v0.2.0 Release Notes](https://github.com/github/copilot-sdk/releases/tag/v0.2.0) — typed `PermissionRequestResultKind`, `PermissionRequestMcp` subclass
- [Copilot SDK Streaming Events](https://github.com/github/copilot-sdk/blob/main/docs/features/streaming-events.md) — `permission.requested` event documentation

### Files Changed

| File | Change |
|------|--------|
| `dotnet/src/Microsoft.Agents.AI.GitHub.Copilot/GitHubCopilotAgent.cs` | Channel restructure, OnPermissionRequest wrapper, typed PermissionRequest subclass extraction |
| `dotnet/src/Microsoft.Agents.AI.AGUI/Shared/AGUIEventTypes.cs` | Added `Custom = "CUSTOM"` constant |
| `dotnet/src/Microsoft.Agents.AI.AGUI/Shared/CustomEvent.cs` | New — AG-UI CUSTOM event BaseEvent subclass |
| `dotnet/src/Microsoft.Agents.AI.AGUI/Shared/BaseEventJsonConverter.cs` | Added CUSTOM + STATE_DELTA deserialization cases |
| `dotnet/src/Microsoft.Agents.AI.AGUI/Shared/AGUIJsonSerializerContext.cs` | Registered CustomEvent for AOT |
| `dotnet/src/Microsoft.Agents.AI.AGUI/Shared/ToolCallStartEvent.cs` | Added JsonIgnore(WhenWritingNull) on ParentMessageId |
| `dotnet/src/Microsoft.Agents.AI.AGUI/Shared/ChatResponseUpdateAGUIExtensions.cs` | Emit CUSTOM events for approval request/completed alongside TOOL_CALL_* |
| `dotnet/src/Microsoft.Agents.AI.Hosting.AGUI.AspNetCore/AGUIEndpointRouteBuilderExtensions.cs` | Added POST /approve endpoint, PendingApprovalStore delegate wiring |
| `dotnet/src/Microsoft.Agents.AI.Hosting.AGUI.AspNetCore/PendingApprovalStore.cs` | New — TCS store with configurable timeout |
| `dotnet/src/Microsoft.Agents.AI.Hosting.AGUI.AspNetCore/AGUIOptions.cs` | New — configurable ApprovalTimeout |
| `dotnet/src/Microsoft.Agents.AI.Hosting.AGUI.AspNetCore/ServiceCollectionExtensions.cs` | Register PendingApprovalStore + AGUIOptions |
| `dotnet/Directory.Packages.props` | GitHub.Copilot.SDK 0.1.29 → 0.2.0 |
