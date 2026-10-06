---
status: proposed
contact: "@jpalvarezl"
date: 2026-10-06
deciders: ["@eavanvalkenburg", "@westey-m"]
informed: ["@SergeyMenshykh", "@rogerbarreto", "@moonbox3", "@baywet", "@peibekwe"]
---

# Expose opaque OpenAI conversation storage for .NET hosting

## Context and Problem Statement

The .NET OpenAI hosting package stores Conversations API metadata, items, and
the per-agent conversation index in internal in-memory services. Applications
can persist `AgentSession`, but cannot replace the protocol storage that DevUI
uses to list and reopen conversations after a process restart.

## Decision Drivers

- Enable durable DevUI and built-in OpenAI Conversations hosting.
- Avoid exposing the large internal OpenAI wire-model graph as public API.
- Preserve caller-isolation scoping in the existing hosting layer.
- Allow database implementations without coupling the hosting package to a
  specific database provider.

## Considered Options

- Make the existing internal conversation storage interfaces and wire models
  public.
  - Good: minimal adapter code.
  - Neutral: storage implementations use strongly typed protocol objects.
  - Bad: permanently exposes a large, rapidly evolving wire-model surface.
- Add a public store contract over opaque JSON records.
  - Good: small public surface, database-neutral, and wire models remain
    internal.
  - Neutral: store implementations treat payloads as opaque documents.
  - Bad: implementations cannot query type-specific item fields without parsing
    the JSON themselves.
- Keep storage internal and add only a custom-route sample.
  - Good: no framework API change.
  - Neutral: demonstrates application-owned persistence.
  - Bad: does not make the built-in Conversations endpoints or DevUI durable.

## Decision Outcome

Chosen option: "Add a public store contract over opaque JSON records", because
it enables database-backed built-in hosting while keeping protocol conversion,
validation, and caller-isolation behavior inside the hosting package.
