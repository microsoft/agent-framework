---
status: proposed
contact: sergeymenshykh
date: 2026-10-29
---

# Give the MCP skills catalog ownership of discovery and refresh

## Context and Problem Statement

The .NET MCP skills source currently performs discovery, metadata validation,
and skill construction, while `McpSkillsLoader` owns the cached list and refresh
queue. The loader invokes callbacks into the source to retrieve metadata.
Consequently, one catalog refresh crosses the source, loader, and generic cache.

Future cache-scope support may require the source to select a separate catalog
for each cache partition. The discovery and refresh implementation should belong
to that catalog rather than to the source selecting it.

## Decision Drivers

- Make ownership of discovery, catalog state, and refresh policy clear.
- Remove the loader's retrieval callbacks into the source.
- Preserve existing public APIs and all caching and verification behavior.
- Establish a per-catalog boundary without implementing cache-scope routing yet.

## Considered Options

- Rename the loader without moving functionality. This is a smaller change but
  leaves discovery and refresh ownership split across two objects.
- Move catalog policy into the source and introduce a protocol client. This
  separates retrieval from policy but mixes future scope selection with
  per-scope state ownership.
- Merge the loader into the source. This removes a class but has the same
  scope-selection problem.
- Keep a thin source and move its discovery implementation into a renamed
  catalog. The catalog becomes larger, but owns one coherent lifecycle.

## Decision Outcome

Proposed option: keep `AgentMcpSkillsSource` as the framework adapter and catalog
owner, rename `McpSkillsLoader` to `McpSkillsCatalog`, and move protocol retrieval,
pagination, metadata validation, skill construction, and response-lifetime
handling into the catalog. Server capability checks, the diagnostic for
unsupported servers, and the total-loaded-skills diagnostic remain in the source.

`McpCache` remains unchanged and owns only storage, expiration checks, and
per-key coordination. `AgentMcpSkill` changes only through mechanical
loader-to-catalog renames; its constructor shape and logic stay the same.
`AgentMcpSkillResource` remains unchanged.

The source owns one catalog for now. Cache-scope selection, dictionary lifetime,
and eviction policy are deferred. The caller retains ownership of the MCP
client. TTL, refresh ordering, cancellation, failure handling, held manifests,
shared mutable list results, and disposal behavior are preserved.

This follows the separation between metadata discovery and lazy file retrieval
in the [MCP Skills specification](https://github.com/modelcontextprotocol/ext-skills/blob/main/specification/beta/skills.mdx).
It does not introduce a cache library, background refresh, or new public API.

Deciders must be designated before requesting approval; this record remains
proposed until the repository's ADR approval process is completed.
