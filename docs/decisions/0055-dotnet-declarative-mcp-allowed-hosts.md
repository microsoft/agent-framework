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
- Preserve the existing constructor signature and per-invocation session lifetime.

## Considered Options

- Permit all destinations: preserves current behavior, but provides no application-owned destination policy.
- Require a new constructor signature: makes configuration explicit, but removes an existing API.
- Retain the existing constructor with an empty policy and add an allowlist overload: preserves binary
  compatibility, but applications must migrate their configuration to continue invoking tools.

## Decision Outcome

Chosen option: retain the existing constructor with an empty policy and add an allowlist overload.

The application supplies exact hosts or IP literals with optional ports. The list is copied, an omitted
port defaults to 443, and an empty list denies every invocation, including discovery. Matching uses the
same shared normalization as HTTP: case-insensitive IDN names, trailing DNS dots removed, and exact
effective ports, without wildcards or implicit subdomains. Workflow-supplied Host headers are rejected.

Both HTTP and HTTPS remain supported. Applications requiring HTTPS must enforce that additional policy.
DNS, proxy configuration, and routing remain transport responsibilities. The application-owned factory
must disable cookies and automatic redirects, and any delegating handlers must preserve the validated
destination and bind credentials to the intended origin.

This changes behavior without removing the existing constructor. Callers must supply their intended
destinations through the new overload; applications with different policies can provide an `IMcpToolHandler`.
Session creation, protocol selection, and resource disposal remain unchanged.
