---
status: proposed
contact: baywet
date: 2026-10-29
deciders: westey-m
---

# Explicit allowed hosts for declarative HTTP requests

## Context and Problem Statement

Declarative HTTP actions receive their destination URLs from workflow content. The application running a
workflow knows which services it intends to contact, while network addressing, DNS, and proxy configuration
vary across deployments. How should the default HTTP handler determine which destinations are authorized?

## Decision Drivers

- Require explicit application authorization before any HTTP request or client-provider invocation.
- Support intentionally configured internal services without classifying deployment-specific networks.
- Preserve existing redirect, header, timeout, and client-ownership behavior.
- Apply the same host-and-port policy across all supported target frameworks and client sources.

## Considered Options

### Permit any HTTP(S) destination

Good: no application migration is required.
Bad: workflow URLs alone determine the available destinations.

### Classify resolved addresses as public or non-public

Good: rejects common local address ranges without application configuration.
Bad: public addressing does not express application authorization, deployment routing varies, and the handler
must maintain address rules and connection-time resolution logic across target frameworks.

### Require an application-owned host allowlist

Good: the application explicitly defines its destinations, including internal services, without address
classification or custom DNS resolution.
Bad: existing applications must configure their hosts, and allowing a hostname trusts its DNS and routing.

## Decision Outcome

Chosen option: "Require an application-owned host allowlist".

Every constructor requires an explicit list; an empty list denies every request. Constructor overloads accept
exact host names or IP literals with optional ports, copy and normalize the list, and authorize the canonical URL before client selection and every
handler-managed redirect. Matching is case-insensitive with IDN and trailing-dot normalization; wildcards and
implicit subdomains are not supported. Entries authorize exact host-and-port pairs; an omitted port defaults
to 443. Explicit ports must be from 1 to 65535, and IPv6 literals must be bracketed when specifying a port.
The request's effective port must match, including on redirects. Entries do not restrict schemes or IP ranges:
both HTTP and HTTPS remain supported, so an entry for port 443 also permits an HTTP URL explicitly using port 443.
Applications that require HTTPS must enforce that additional policy before supplying an authenticated client.
Only HTTP(S) URLs are accepted, and existing redirect restrictions remain in effect. Workflow-supplied Host
headers are rejected before client selection; the transport derives the authority from the allowed URL.

The transport handles normal DNS resolution, proxies, and routing. The internally owned client disables
automatic redirects and cookies on every target framework. Supplied clients remain caller-owned and must
disable automatic redirects or independently enforce the same allowlist on redirects inside their transport.
The handler does not inspect or reconfigure an opaque supplied transport.

This is a breaking API and behavioral change: the parameterless, client-only, and provider-only constructors
are removed. Callers must supply an allowlist at construction, including when supplying a client or provider.
The HTTP sample and integration caller configure their intended hosts explicitly.
