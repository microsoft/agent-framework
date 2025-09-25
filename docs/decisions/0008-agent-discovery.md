---
# These are optional elements. Feel free to remove any of them.
status: proposed
contact: dmkorolev
date: 2025-08-20
deciders: adityam, reubenbond, sergeymenshykh, markwallace, rbarreto, dmytrostruk, westey-m, eavanvalkenburg, stephentoub
consulted: 
informed: 
---

# Agent Discovery: Simplified App-Scoped Design

## Summary

This document proposes a minimal, app-scoped discovery API for listing agents and fetching metadata for a single agent.

The goal of "agent discovery" feature is to expose 2 different types of endpoints:
  1) The discovery endpoints. Those should return the metadata about registered agents.
  2) The generic-way of communicating with registered agents. The goal is to have a strongly-typed schema to be able to send and retrieve messages for specific actor / conversation.

## How other frameworks and protocols handle discovery today

- A2A “Card” endpoints
  - Pattern: Agents expose GET /v1/card (or /.well-known/agent-card) with a JSON manifest describing identity, capabilities, and links (e.g., OpenAPI).
  - Use case: Direct agent-to-agent or client-to-agent discovery without a central registry.
  - Trade-offs: No built-in global listing; requires clients to know or crawl base URLs.

- OpenAI/ChatGPT Plugins (legacy)
  - Endpoint: /.well-known/ai-plugin.json describes the plugin (name, auth, description) and links to an OpenAPI spec.
  - Model: Self-describing service manifest + formal API contract; essentially a “card” for a plugin.

- MCP (Model Context Protocol)
  - Mechanism: Upon connection (JSON-RPC over stdio/WebSocket), the client calls list endpoints (tools/list, resources/list, prompts/list) to discover capabilities.
  - Scope: Discovery is per-server session; “how to find servers” is external (config/host app).

- OpenRPC (JSON-RPC ecosystems)
  - Method: rpc.discover returns an OpenRPC document listing all methods, params, and schemas.
  - Nature: Built-in RPC introspection—akin to a “card” over RPC.

Rule of thumb:
- Centralized, app-scoped discovery (this proposal) mirrors service registries.
- Per-service manifests (card-style) mirror OIDC discovery, plugin manifests, and protocol introspection (MCP, OpenRPC, GraphQL, gRPC reflection).

## Endpoint Design

This design keeps the surface area minimal and future-proof:
- Simple mental model: one collection endpoint, one item endpoint.
- Works regardless of how agents are managed (static config, code plugins, database, etc.).
- Leaves room for pagination and richer filtering without forcing it from day one.
- Decouples “how agents are registered” from “how they are discovered.”

### Discovery endpoints `/agents/v1` and `/agents/v1/{agentName}`

Returns a list of agents and metadata about specific agent visible to the caller

Potentially we can support different query parameters or features (such as pagination), but that can be added in the next version of the protocol.
- q — free-text search across name/description/tags.
- tag — filter by tag (repeatable).
- include — comma-separated field groups to embed, e.g., include=capabilities,endpoints (defaults to a summary view).
- pagination — support for fetching agents in batches.

Response (summary view example):

```json
{
  "agents": [
    {
      "name": "pirate",
      "description": "Agent which talks like a pirate",
      "version": "1.4.2",
      "instructions": "Talk like a pirate",
      "model": "gpt-4o",
      "metadata": {
        "common-words": [ "argh", "matey" ]
      }
    },
    ...
  ]
}
```

This scheme maps to the existing definition of base `AIAgent` class:
```csharp
public abstract class AIAgent
{
    public virtual string Id { get; } = Guid.NewGuid().ToString();
    public virtual string? Name { get; }
    public virtual string? Description { get; }
}
```

## Minimal Data Model (AgentMetadata v1)

- name: name of agent registration in-app (string)
- description: description (string)
- version: semantic version (string)
- instructions: if a chat agent has instructions on how to act (string)
- model: the underlying model used (string)
- metadata: object — additional, vendor-specific fields; free-form extension point

Questions:
1) if i.e. `AIAgent` is a concurrent-orchestration, then we can make a more complex schema exposing information about how agent is defined. I wonder if we want to support this
```json
{
  ... ,
  "structure": {
    "lie": {
      "type": "chat",
      "instructions": "tell only lies",
      "model": "gpt-4o"
    },
    "truth": {
      "type": "chat",
      "instructions": "tell only truth",
      "model": "gpt4.1"
    }
  }
}
```

## Communication endpoints `/actors/v1/{actorType}/{actorKey}/messages/{messageId}`

Agent Discovery is only good if there is an established way to communicate to the agents. Without an implemented in-place endpoint for sending/retrieving messages (for actor and conversation) users can build too different schemas, and make the client-side work unbearable for multiple different apps.

Based on this thought I am proposing an `actors/v1/...` route group, which allows sending / retrieving and cancelling the message processing. All these endpoints include `actorType`, `actorKey` and `messageId` as the uri params.

- `actorType` here is the same as the name of agent registration (in our case - `pirate`).
- `actorKey` is the unique identifier of the conversation. For simplicity - GUID would work.
- `messageId` is the identifier of the message in the conversation. GUID should work here fine as well.

The sending message API (HTTP POST) also has a body to fill in the actual data like message to the chat. `Method` is an already known agentic-framework term (method name to invoke on the agent). `Params` is a free-typed representation of input: in chat-client case it is a user message typed in the chat.
```json
{
  "method": "run",
  "params": [
    { "$type": "text", "content": "hey matey!" }
  ]
}
```

## Versioning and Content Negotiation

- Protocol versioning is encoded in the URL path as /vX beneath the reserved prefix. Breaking changes will increment X (e.g., /agents/v1 -> /agents/v2). Additive, backwards-compatible changes MAY be introduced within a major version without changing X.

## Security, Caching, and Performance

- Auth: Use your platform’s standard authentication/authorization; no per-agent auth metadata is modeled. Since the same server typically serves both discovery and agent calls, the auth model is consistent across both.
- Server policy: The server decides which agents to return; there is no per-agent visibility field in the model.
- Caching: Support ETag/Last-Modified on both endpoints. Clients can send If-None-Match.
- Partial responses: include can help minimize payloads if implemented.
- Pagination: Add page/per_page when you outgrow a single page; design leaves room for it.

## Error Model

- 401/403 for auth/authz failures
- 404 when agentId not found
- 406 if Accept not supported (if you later add custom media types)
- Use RFC7807 application/problem+json for error bodies if desired

## How this relates to A2A “/v1/card”

- What /v1/card is: a per-agent document served by the agent itself (common in agent-to-agent setups) so a client that only knows an agent’s base URL can fetch its capabilities directly.
- Why you may not need it now: your discovery is centralized at the app level, and you don’t need agent self-registration or direct peer discovery.
- When to consider it later: if you want agents to be discoverable without going through the app, expose either:
  - GET /.well-known/agent-card (preferred, well-known)
  - or GET /v1/card
  returning an equivalent metadata shape (or a subset) to AgentMetadata v1.
