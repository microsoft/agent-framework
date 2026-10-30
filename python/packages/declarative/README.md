# Get Started with Microsoft Agent Framework Declarative

Please install this package via pip:

```bash
pip install agent-framework-declarative
```

The package currently advertises Python 3.11–3.13 support. Python 3.10
installation remains permitted, but compatibility is not guaranteed. Python 3.14 and
3.15 can install the package, but Power Fx expressions are unavailable because
the `powerfx` dependency requires a `pythonnet` build that does not support
those Python versions.

## Release stage

This package ships at two different stability levels:

- **Declarative workflows** (`WorkflowFactory`, executors, handlers, and the
  `_workflows` surface) are **stable**.
- **Declarative agents** (`AgentFactory` and the YAML agent loading/parsing path:
  `DeclarativeLoaderError`, `ProviderLookupError`, `ProviderTypeMapping`) are
  **experimental** and may change or be removed in future versions without notice.
  Using any of these symbols emits an `ExperimentalWarning` on first use.

## Declarative features

The declarative packages provides support for building agents based on a declarative yaml specification.

## HTTP request client ownership and cookies

**Breaking change:** The HTTP client created by `DefaultHttpRequestHandler` no longer
persists response cookies. The handler still creates its client lazily, reuses it across
requests and workflows, and closes it on `aclose()` or async context-manager exit.
Timeout and redirect defaults are unchanged.

Applications requiring cookies for authentication, session continuity, or load-balancer
affinity must supply an `httpx.AsyncClient` through `client=` or `client_provider=`.
Supplied and provider-returned clients retain their configuration and cookie behavior
and must be closed by the caller. Scope cookie-bearing clients to one authenticated
principal; sharing a handler across workflows does not partition a client's cookies.
A provider returning `None` falls back to `client=`, if supplied, then to the internally
owned client with the default cookie policy.

Explicit `Cookie` request headers remain supported. Response `Set-Cookie` headers
remain available in `HttpRequestResult.headers`; disabling persistence does not redact
the response.

## HTTP response body limits

`DefaultHttpRequestHandler` limits response bodies to **10 MiB** by default.
Configure a positive integer `max_response_body_bytes` on the handler when a host
requires a different bound. The bound applies to received bytes and each decoded
stage, including intermediate redirect and authentication responses. Responses
above the bound raise `httpx.StreamError` before text conversion or workflow
assignment, and their streams are closed without closing caller-owned clients.

The handler restricts HTTPX's generated `Accept-Encoding` default to `gzip, deflate`
and supports identity, gzip, and deflate
responses, including up to four encoding stages. Unsupported encodings,
incomplete encoded bodies, and trailing encoded data raise `httpx.DecodingError`.
Empty encoded responses are validated unless the response is bodyless (HEAD,
1xx, 204, 205, 304, or a successful CONNECT response). Deflate input is retained
within the same bound until its wrapped or raw format can be validated.
Explicit request `Accept-Encoding` headers and client values that differ from
HTTPX's generated default are preserved but do not enable additional decoders.
Caller-supplied response hooks and transports must not
buffer response bodies before the handler applies its limit.

HTTPX support is limited to the 0.27 and 0.28 series because the bounded
intermediate-response cache and generated default-header integration depend
on HTTPX internals. Compatibility tests cover HTTPX 0.27.0 and 0.28.1.

## MCP handler session lifetime

`DefaultMCPToolHandler()` reuses MCP sessions through a bounded LRU cache.
When configured with `client_provider`, it instead invokes the provider and
creates a fresh MCP tool/session for every invocation, including `tools/list`.
Sessions are never reused in this mode, even if the provider returns `None`
or the same `httpx.AsyncClient` instance.

Each invocation closes its tool/session on success, failure, or cancellation.
Internally created fallback HTTP clients are also closed; caller-supplied HTTP
clients remain caller-owned and are never closed by the handler. Calling
`aclose()` rejects new invocations and waits for active provider-backed
invocations to finish cleaning up. Calling it from an active invocation's
context (including provider callbacks, inherited child tasks, and cleanup)
raises `RuntimeError` before changing handler state, rather than waiting on
itself. Close the handler outside that context or after the invocation completes.

This intentionally incurs connection and initialization overhead and does not
retain server session state between provider-backed invocations. Applications
that require shared session ownership must implement an explicitly scoped
custom `MCPToolHandler`; there is no provider-backed session-cache opt-in.
