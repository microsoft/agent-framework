---
status: proposed
---

# Own declarative MCP sessions per invocation

## Context and Problem Statement

A shared `DefaultMCPToolHandler` caches initialized MCP clients by connection
configuration. Independently constructed workflows with identical endpoint and
headers can therefore share server-side protocol state. Workflow-owned session
identity would partition that cache, but also require Core changes for run
admission, approval routing, nested workflows, and checkpoint recovery.

## Considered Options

- Retain the cache and propagate workflow identity through Core and declarative requests.
- Create and close a protocol session for each invocation.
- Require every host to implement a custom handler.

## Decision Outcome

Choose invocation ownership, matching the lifetime principle in [.NET PR #9722](https://github.com/microsoft/agent-framework/pull/9722).
Every invocation, including `tools/list`, connects and closes its own
`MCPStreamableHTTPTool`. Cleanup completes before the call returns, including
on failure or cancellation. Cleanup failures are logged without replacing the
invocation result or error; cancellation still propagates.

Keep the existing optional Python `client_provider` callback. Its clients are
borrowed and remain host-owned; returning `None` creates an internally owned
client. This separates HTTP connection pooling from MCP protocol-session
ownership without introducing a factory abstraction or new transport options.
Core already supports both ownership modes, so no Core changes are necessary.

Remove the initialized-client cache, `aclose()`, and the handler async context
manager. Retain `cache_max_size` as a deprecated, ignored compatibility parameter;
non-`None` values emit `DeprecationWarning` without validation, and omission or
`None` emits no warning. It does not restore session caching.
Hosts own admission, deadlines, cancellation, and shutdown
coordination. They must cancel and await active invocations before disposing
borrowed HTTP clients.

This is an intentional API and behavioral break. Replace handler context
managers with ordinary construction and remove handler shutdown calls. Each call
pays connection and discovery overhead. Implicit server-session continuity no
longer survives subsequent calls, approval waits, or checkpoint resumes.
Applications needing continuity must use explicit remote state handles or an
explicitly scoped custom handler. Existing checkpoint and approval contracts
remain unchanged; no workflow identity field or checkpoint migration is added.
