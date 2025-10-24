# Basic agentic chat — implementation plan

## Scenario goal
Establish the smallest end-to-end slice where a .NET AG-UI `AGUIClient` sends a user message, the ASP.NET Core hosting layer relays it to an agent built on Microsoft.Extensions.AI abstractions, and the streamed response is pushed back to the client while preserving conversation state.

## References reviewed
- `llms-full.txt` for AG-UI event, message, and state semantics.
- Microsoft.Extensions.AI knowledge (ChatClient abstractions, `AIAgent`, `ChatClientAgentRunOptions`) — unable to query `#microsoft.docs.mcp`, relying on existing API familiarity.
- Legacy prototype under `dotnet\src\bin\dotnet` for SSE handling patterns, AG-UI DTO shaping, and HttpClient wiring techniques to reuse/adapt for the production API.

## Minimum deliverables
1. **Client package** `Microsoft.Agents.AI.AGUI`
   - Public surface limited to `AGUIClient : AIAgent`. Constructor accepts `HttpClient httpClient, string id, string description, IEnumerable<ChatMessage> messages, JsonElement state`, internally issuing `CreateNewThread()` from the base class.
   - `RunAsync(ChatClientAgentRunOptions input)` → `IAsyncEnumerable<AgentRunResponse>` and `RunStreamingAsync(ChatClientAgentRunOptions input)` → `IAsyncEnumerable<AgentRunResponseUpdate)`; both translate `tools`, `context`, and `forwardedProps` into `ChatOptions` (even if initial scenario omits actual tool usage).
   - SSE consumer lifted from the prototype concept: map AG-UI text/lifecycle events into `AgentRunResponse`/`AgentRunResponseUpdate`, store the raw event inside `RawRepresentation`, and maintain assistant message/state snapshots.
2. **Server package** `Microsoft.Agents.AI.Hosting.AGUI.AspNetCore`
   - `IEndpointRouteBuilder.MapAGUIAgent(string path, Func<IEnumerable<ChatMessage>, IEnumerable<AITool>, JsonElement, IEnumerable<KeyValuePair<string, string>>, JsonElement, AIAgent> agentFactory)` extension configuring a `/runs` endpoint.
   - Input translation aligning with `RunAgentInput`: `threadId` → `AgentThread GetNewThread(string conversationId)`, `messages` → `IEnumerable<ChatMessage>`, `tools` → `IEnumerable<AITool>`, `context`/`state` → `AIContext`, `forwardedProps` → `ChatOptions` additional properties, `runId` drives emitted lifecycle events.
   - Stream AG-UI events directly over SSE (pattern borrowed from the prototype), synthesizing lifecycle events (`RUN_STARTED`, `RUN_FINISHED`, `RUN_ERROR`) when the downstream agent omits them.
3. **Integration test project** scaffold proving client/server round-trip with WebApplicationFactory (initially leveraging simple echo behavior, no tool-call coverage).

## Client flow (minimal happy path)
1. `AGUIClient` constructor captures injectable `HttpClient`, agent metadata, current history, and state, delegating thread creation through base `AIAgent`.
2. `RunAsync` / `RunStreamingAsync`:
   - Build `ChatOptions` from `ChatClientAgentRunOptions` (merge tools/context/forwarded props even if empty) and prepare `RunAgentInput`.
   - Issue POST to server endpoint with `Accept: text/event-stream` using the legacy prototype’s resilient SSE reader for guidance.
3. Stream handling:
   - Aggregate `TEXT_MESSAGE_START`, `TEXT_MESSAGE_CONTENT`, `TEXT_MESSAGE_END` into `AgentRunResponseUpdate` deltas, emitting through base mechanisms, and store original AG-UI event under `RawRepresentation`.
   - Relay lifecycle events into updates, ensuring assistant message persistence once terminal `RUN_FINISHED` arrives.
4. Upon completion, append the assistant message to the local conversation log and update stored state (no tool call artifacts required for this slice).

## Server flow (minimal happy path)
1. `MapAGUIAgent` registers the route that deserializes `RunAgentInput` and invokes the provided factory to obtain an `AIAgent`.
2. Emit `RUN_STARTED` before invoking the agent to guarantee lifecycle signaling, mirroring the prototype’s guard behavior.
3. Execute the agent run, projecting textual deltas to `TEXT_MESSAGE_*`; forward any lifecycle signals verbatim, and synthesize missing terminal events (`RUN_FINISHED` or `RUN_ERROR`) based on completion outcome.
4. Stream the resulting events via SSE using the shared encoder (reuse the prototype encoder semantics), ensuring proper headers and flush behavior.

## Shared types (initial subset)
- `RunAgentInput` (threadId, runId, messages, context, forwardedProps, state).
- Events: `RunStartedEvent`, `RunFinishedEvent`, `RunErrorEvent`, `StepStartedEvent`, `StepFinishedEvent`, `TextMessageStart/Content/End`.
- Messages: `UserMessage`, `AssistantMessage`.
- Result wrapper for unmatched events exposing `RawRepresentation`.

## Testing & validation checkpoints
- Client unit test: simulate SSE stream using HttpMessageHandler to verify `AGUIClient` produces `AgentRunResponseUpdate` instances and final message persistence.
- Server unit test: exercise `MapAGUIAgent` with a fake `AIAgent` yielding text deltas to confirm event translation and synthesized lifecycle events.
- Integration test: WebApplicationFactory with minimal pipeline + real `AGUIClient`, asserting that the assistant reply echoed by the server lands in the client’s conversation history.

## Open items / future steps
- Formalize `RawRepresentation` structure to support downstream inspection.
- Extend error propagation coverage (`RUN_ERROR` to `AgentRunResponseUpdate`) once the base flow is stable.
- Capture authentication pluggability for `HttpClient` once end-to-end happy path is complete.
