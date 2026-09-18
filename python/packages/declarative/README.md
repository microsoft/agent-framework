# Get Started with Microsoft Agent Framework Declarative

Please install this package via pip:

```bash
pip install agent-framework-declarative
```

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

## SendActivity expression output

**Breaking change:** `SendActivity` no longer applies template interpolation to
the result of an expression. Authored text starting with `=` is evaluated once
and its result is emitted as data. For example, if `Local.message` contains
`Hello, {Local.name}!`, `activity: =Local.message` now outputs those braces
literally. There is no second variable lookup in the returned text.

If a workflow relied on that second pass, move the template into the activity
definition or construct the final text in the expression. Given `Local.name`
set to `Alice`, either of these activities emits `Hello, Alice!`:

```yaml
- kind: SendActivity
  activity: "Hello, {Local.name}!"
- kind: SendActivity
  activity:
    text: '="Hello, " & Local.name & "!"'
```

Both string activities and mappings with a `text` field support either form.
Existing directly authored templates retain their variable-resolution and
missing-value behavior. Expression recognition still requires `=` to be the
first character; leading whitespace is not removed. Non-string output conversion
and suppression of falsey results are unchanged.

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
