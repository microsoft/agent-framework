---
# These are optional elements. Feel free to remove any of them.
status: proposed
contact: dmkorolev
date: 2025-08-20
deciders: adityam, Reuben.Bond, sergeymenshykh, markwallace, rbarreto, dmytrostruk, westey-m, eavanvalkenburg, stephentoub
consulted: 
informed: 
---

# Agent Discovery: Simplified App-Scoped Design

## Summary

This document proposes a minimal, app-scoped discovery API for listing agents and fetching metadata for a single agent. To avoid colliding with user-defined routes, the discovery API is served under a reserved, well-known prefix:

- GET /.well-known/agentframework/v1/agents — enumerate agents registered in the app.
- GET /.well-known/agentframework/v1/agents/{agentId} — fetch detailed metadata for a specific agent.

It intentionally omits registration endpoints and any per-agent “card” requirement. If you later want peer agents to discover each other directly, you can optionally add per-agent cards without breaking this design.

Note on prefix choice:
- We standardize on the RFC 8615 “.well-known” space: /.well-known/agentframework/...
- Implementations MAY provide aliases (e.g., /.agent-framework/...) or redirects for compatibility.

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

Reserved prefix:
- Canonical base: /.well-known/agentframework/v1/...
- Implementations MAY also serve:
  - Alias: /.agent-framework/v1/... (ensure your web server doesn’t block “dotfile” paths)
  - Legacy: /v1/agents (optional 308 redirect to the well-known path)

### GET /.well-known/agentframework/v1/agents

Returns a list of agents visible to the caller. Start with a plain list; add pagination when needed.

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
      "id": "image-annotator",
      "name": "Image Annotator",
      "summary": "Annotates images with labels and boxes.",
      "version": "1.4.2",
      "tags": ["vision", "annotation"]
    },
    {
      "id": "faq-search",
      "name": "FAQ Search",
      "summary": "Semantic search over internal FAQs.",
      "version": "0.9.0",
      "tags": ["search", "knowledge"]
    }
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

### GET /.well-known/agentframework/v1/agents/{agentId}

Returns full metadata for one agent.

Potential query parameters (optional, we can extend in next versions of protocol):
- view — summary|full (default: full)
- include — e.g., include=endpoints

Response (full view example):

```json
{
  "id": "image-annotator",
  "name": "Image Annotator",
  "version": "1.4.2",
  "description": "Annotates images and returns JSON labels and bounding boxes.",
  "owner": { "name": "Vision Team", "email": "vision@example.com" },
  "tags": ["vision", "annotation"],
  "endpoints": [
    { "method": "POST", "path": "/v1/message:send",   "description": "Send message to agent" },
    { "method": "POST", "path": "/v1/message:stream", "description": "Send message with streaming (SSE)" },
    { "method": "GET",  "path": "/v1/tasks/{id}",     "description": "Get task status/results" }
  ],
  "capabilities": {},
  "created_at": "2025-06-12T08:15:00Z",
  "updated_at": "2025-08-15T10:01:03Z",
  "metadata": {}
}
```

Questions:
- do we want to initially support non-HTTP requests? should be define more complex object in endpoints?
```json
{
    "transport": "HTTP",
    "httpMethod": "GET",
    ... 
}
```

## Minimal Data Model (AgentMetadata v1)

Top-level fields:
- id: stable, path-safe identifier (string)
- name: human-readable name (string)
- version: semantic version (string)
- summary: short summary (string)
- description: longer description (string)
- owner: { name, email?, url? }
- tags: [string]
- endpoints: [Endpoint] — minimal, actionable HTTP entry points to invoke the agent
- capabilities: object — dictionary of well-known feature flags (empty for v1; keys can be added later as needed)
- created_at, updated_at: RFC3339 timestamps
- metadata: object — additional, vendor-specific fields; free-form extension point

Endpoint:
- method: HTTP method (e.g., "GET", "POST")
- path: URL path relative to the same host (string)
- description: optional human-readable description (string)

Capabilities:
- A free-form object for future well-known feature flags (e.g., {"streaming": true}) but intentionally empty in this version.

You can publish a JSON Schema at a stable URL later; for now, treat the above as normative fields.

## Versioning and Content Negotiation

- Protocol versioning is encoded in the URL path as /vX beneath the reserved prefix. Breaking changes will increment X (e.g., /.well-known/agentframework/v1 -> /.well-known/agentframework/v2). Additive, backwards-compatible changes MAY be introduced within a major version without changing X.
- Clients should select the desired major version by calling the corresponding /vX endpoints. No content-type version negotiation is required for protocol compatibility.
- Media type: application/json is sufficient. If desired, you MAY also advertise a custom media type (e.g., application/agent-metadata+json;version=1) for stronger schema signaling, but the canonical protocol version is the /vX path.

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
