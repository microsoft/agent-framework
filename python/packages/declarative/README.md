# Get Started with Microsoft Agent Framework Declarative

Please install this package via pip:

```bash
pip install agent-framework-declarative
```

The package currently advertises Python 3.11–3.13 support. Python 3.14 and
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

`WorkflowFactory` creates its default `AgentFactory` lazily when loading an
agent definition from the workflow's `agents` section, including references to
agent YAML files. That path uses the experimental declarative-agent APIs and
emits the corresponding warning. When no custom `agent_factory` is supplied,
`WorkflowFactory` loads `env_file` during initialization, independently of agent
creation. Workflow expressions such as `=Env.NAME` can read those variables when
`restrict_env_to_configuration=False`; explicit `configuration` values still
take precedence.

Workflows containing only workflow actions use the stable workflow APIs. To use
agents through that surface, create them with the appropriate client and pass
them through `WorkflowFactory(agents=...)` or `register_agent(...)`. Registered
agents take precedence over matching YAML definitions and bypass declarative
agent loading.

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

**Security fix:** `DefaultMCPToolHandler` creates and closes a fresh MCP
tool/session for every invocation, including `tools/list`. Independently
constructed workflows may safely share a handler without sharing MCP protocol
state, even with identical endpoint and header configuration. There is no
initialized-client or discovery cache.

Each invocation closes its tool/session on success, failure, or cancellation.
Internally created HTTP clients are also closed. The optional `client_provider`
is called once per invocation and may return a reusable `httpx.AsyncClient`
to share an HTTP connection pool, not an MCP session. Returned clients are
borrowed and never closed by the handler. Returning `None` selects an internally
owned client.

Provider, connection, discovery, and transport failures raise exceptions and fail
the workflow action, including after approval. Remote tool error responses still
produce `MCPToolResult(is_error=True)` and populate `output.result` with an error
string. Custom handlers should return error results only for tool-level errors;
raised exceptions are not converted into workflow results.

The legacy `cache_max_size` parameter is accepted for compatibility, but is
deprecated and ignored. Passing any non-`None` value emits `DeprecationWarning`;
the value is not validated. Omitting it or passing `None` emits no warning.
It cannot restore session caching or sharing.

The handler no longer implements `aclose()` or an async context manager.
Replace `async with DefaultMCPToolHandler() as handler:`
with `handler = DefaultMCPToolHandler()` and remove handler shutdown calls.
Continue to manage caller-owned HTTP clients with their own context manager.
Hosts must cancel and await active invocations before closing borrowed clients;
admission limits and deadlines also belong to the host.

This intentionally adds connection and initialization overhead. Implicit
server-side state does not persist across tool calls, approval waits, or
checkpoint resumes. Workflow checkpoints and approval verification are
unchanged; no request-scope migration flag is required. Applications that need
MCP session continuity must provide an explicitly scoped custom `MCPToolHandler`
or pass explicit remote state handles as tool arguments. See the
[decision record](../../../docs/decisions/0053-python-invocation-owned-mcp-sessions.md).
