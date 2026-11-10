---
status: proposed
contact: baywet
date: 2026-11-09
deciders: westey-m
---

# Explicit allowed hosts for declarative MCP invocations

## Context and Problem Statement

Declarative MCP actions receive their server URLs from workflow content. The application
owns destination configuration and the HTTP pipeline. The default MCP handler should apply
the same host-and-port policy as the [default HTTP handler](0049-dotnet-declarative-http-allowed-hosts.md).

## Decision Drivers

- Require application-configured destinations before creating an HTTP client.
- Keep host normalization and port matching consistent between HTTP and MCP.
- Make destination and transport configuration explicit while preserving per-invocation session lifetime.

## Considered Options

- Permit all destinations: preserves current behavior, but provides no application-owned destination policy.
- Require a new constructor signature: makes configuration explicit, but removes an existing API.
- Retain the existing constructor with an empty policy and add an allowlist overload: preserves binary
  compatibility, but applications must migrate their configuration to continue invoking tools.

## Decision Outcome

Chosen option: require a new constructor signature with allowed hosts and an `IHttpMessageHandlerFactory`.
Remove the constructor accepting `IHttpClientFactory` rather than retain an overload that cannot invoke tools.

The application supplies exact hosts or IP literals with optional ports. The list is copied, an omitted
port defaults to 443, and an empty list denies every invocation, including discovery. Matching uses the
same shared normalization as HTTP: case-insensitive IDN names, trailing DNS dots removed, and exact
effective ports, without wildcards or implicit subdomains. Workflow-supplied Host headers are rejected.

Both HTTP and HTTPS remain supported. Applications requiring HTTPS must enforce that additional policy.
DNS, proxy configuration, and routing remain transport responsibilities. The application supplies an
`IHttpMessageHandlerFactory`; before sending, the handler validates that each pipeline terminates in an
`HttpClientHandler`, or on .NET a `SocketsHttpHandler`, with cookies and automatic redirects disabled.
Unknown primary transports and incomplete pipelines are rejected. Redirect responses are not followed.
Application-owned delegating handlers must preserve the validated destination and bind credentials to
the intended origin.

The handler creates and disposes an HTTP client per invocation without disposing the factory-owned
pipeline. Client configuration callbacks registered through `IHttpClientFactory` do not apply; configure
headers and origin-bound authentication in delegating handlers. This matches the HTTP handler's ownership
and transport-validation contract while keeping MCP protocol sessions separate per invocation.

This removes the existing constructor. Callers must migrate to the constructor accepting their intended
destinations and a message handler factory; applications with different policies can provide an `IMcpToolHandler`.
Session creation, protocol selection, and resource disposal remain unchanged.
