---
status: accepted
contact: javiercn
date: 2025-10-29
deciders: javiercn, DeagleGross, moonbox3, markwallace-microsoft
consulted: Agent Framework team
informed: .NET community
---

# AG-UI Protocol Support for .NET Agent Framework

## Context and Problem Statement

The .NET Agent Framework needed a standardized way to enable communication between AI agents and user-facing applications with support for streaming, real-time updates, and bidirectional communication. Without AG-UI protocol support, .NET agents could not interoperate with the growing ecosystem of AG-UI-compatible frontends and agent frameworks (LangGraph, CrewAI, Pydantic AI, etc.), limiting the framework's adoption and utility.

The AG-UI (Agent-User Interaction) protocol is an open, lightweight, event-based protocol that addresses key challenges in agentic applications including streaming support for long-running agents, event-driven architecture for nondeterministic behavior, and protocol interoperability that complements MCP (tool/context) and A2A (agent-to-agent) protocols.

## Decision Drivers

- Need for streaming communication between agents and client applications
- Requirement for protocol interoperability with other AI frameworks
- Support for long-running, multi-turn conversation sessions
- Real-time UI updates for nondeterministic agent behavior
- Standardized approach to agent-to-UI communication
- Framework abstraction to protect consumers from protocol changes

## Considered Options

1. **Implement AG-UI event types as public API surface** - Expose AG-UI event models directly to consumers
2. **Use custom AIContent types for lifecycle events** - Create new content types (RunStartedContent, RunFinishedContent, RunErrorContent)
3. **Current approach** - Internal event types with framework-native abstractions

## Decision Outcome

Chosen option: "Current approach with internal event types and framework-native abstractions", because it:

- Protects consumers from protocol changes by keeping AG-UI events internal
- Maintains framework abstractions through conversion at boundaries
- Uses existing framework types (AgentRunResponseUpdate, ChatMessage) for public API
- Focuses on core text streaming functionality
- Leverages existing properties (ConversationId, ResponseId, ErrorContent) instead of custom types
- Provides bidirectional client and server support

### Implementation Details

**In Scope:**
1. **Client-side AG-UI consumption** (`Microsoft.Agents.AI.AGUI` package)
   - `AGUIAgent` class for connecting to remote AG-UI servers
   - `AGUIAgentThread` for managing conversation threads
   - HTTP/SSE streaming support
   - Event-to-framework type conversion

2. **Server-side AG-UI hosting** (`Microsoft.Agents.AI.Hosting.AGUI.AspNetCore` package)
   - `MapAGUIAgent` extension method for ASP.NET Core
   - Server-Sent Events (SSE) response formatting
   - Framework-to-event type conversion
   - Agent factory pattern for per-request instantiation

3. **Text streaming events**
   - Lifecycle events: `RunStarted`, `RunFinished`, `RunError`
   - Text message events: `TextMessageStart`, `TextMessageContent`, `TextMessageEnd`
   - Thread and run ID management via `ConversationId` and `ResponseId`

### Key Design Decisions

1. **Event Models as Internal Types** - AG-UI event types are internal with conversion via extension methods; public API uses the existing types in Microsoft.Extensions.AI as those are the abstractions people are familiar with

2. **No Custom Content Types** - Run lifecycle communicated through existing `ChatResponseUpdate` properties (`ConversationId`, `ResponseId`) and standard `ErrorContent` type

3. **Agent Factory Pattern** - `MapAGUIAgent` uses factory function `(messages) => AIAgent` to allow request-specific agent configuration supporting multi-tenancy

4. **Bidirectional Conversion Architecture** - Symmetric conversion logic in shared namespace compiled into both packages for server (`AgentRunResponseUpdate` → AG-UI events) and client (AG-UI events → `AgentRunResponseUpdate`)

5. **Thread Management** - `AGUIAgentThread` stores only `ThreadId` with thread ID communicated via `ConversationId`; applications manage persistence for parity with other implementations and to be compliant with the protocol. Future extensions will support having the server manage the conversation.

6. **Custom JSON Converter** - Uses custom polymorphic deserialization via `BaseEventJsonConverter` instead of built-in System.Text.Json support to handle AG-UI protocol's flexible discriminator positioning

### Consequences

**Positive:**
- .NET developers can consume AG-UI servers from any framework
- .NET agents accessible from any AG-UI-compatible client
- Standardized streaming communication patterns
- Protected from protocol changes through internal implementation
- Symmetric conversion logic between client and server
- Framework-native public API surface

**Negative:**
- Custom JSON converter required (internal implementation detail)
- Shared code uses preprocessor directives (`#if ASPNETCORE`)
- Additional abstraction layer between protocol and public API

**Neutral:**
- Initial implementation focused on text streaming
- Applications responsible for thread persistence
