---
status: accepted
contact: westey-m
date: 2026-02-24
deciders: sergeymenshykh, markwallace, rbarreto, dmytrostruk, westey-m, eavanvalkenburg, stephentoub, lokitoth, alliscode, taochenosu, moonbox3
consulted:
informed:
---

# AdditionalProperties for AIAgent and AgentSession

## Context and Problem Statement

The `AIAgent` base class currently exposes `Id`, `Name`, and `Description` as its core metadata properties, and `AgentSession` exposes only a `StateBag` property.
Neither type has a mechanism for attaching arbitrary metadata, such as protocol-specific descriptors (e.g., A2A agent cards), hosting attributes, session-level tags, or custom user-defined metadata for discovery and routing.

Other types in the framework already carry `AdditionalProperties` — notably `AgentRunOptions`, `AgentResponse`, and `AgentResponseUpdate` — all using `AdditionalPropertiesDictionary` from `Microsoft.Extensions.AI`.
Adding a similar property to `AIAgent` and `AgentSession` would give both types a consistent, extensible metadata surface.

Related: [Work Item #2133](https://github.com/microsoft/agent-framework/issues/2133)

## Decision Drivers

- **Consistency**: Other core types (`AgentRunOptions`, `AgentResponse`, `AgentResponseUpdate`) already expose `AdditionalProperties`. `AIAgent` and `AgentSession` are the major abstractions that lack this.
- **Extensibility**: Hosting libraries, protocol adapters (A2A, AG-UI), and discovery mechanisms need a place to attach agent-level and session-level metadata without subclassing.
- **Simplicity**: The solution should be easy to understand and use; avoid over-engineering.
- **Minimal breaking change**: The addition should not require changes to existing agent implementations.
- **Clear semantics**: Users should understand what `AdditionalProperties` on an agent or session means and how it differs from `AdditionalProperties` on `AgentRunOptions`.

## Considered Options

### Surface Area

- **Option A**: Public get-only property, auto-initialized (`AdditionalPropertiesDictionary AdditionalProperties { get; } = new()`) on both `AIAgent` and `AgentSession`
- **Option B**: Public get/set nullable property (`AdditionalPropertiesDictionary? AdditionalProperties { get; set; }`) on both `AIAgent` and `AgentSession`
- **Option C**: Constructor-injected dictionary with public get-only accessor on both `AIAgent` and `AgentSession`
- **Option D**: External container/wrapper object — metadata lives outside `AIAgent` and `AgentSession`; no changes to the base classes

### Semantics

- **Option 1**: Metadata only — describes the agent or session; not propagated when calling `IChatClient`
- **Option 2**: Passed down the stack — merged into `ChatOptions.AdditionalProperties` during `ChatClientAgent` runs

## Decision Outcome

The chosen option is **Option D + Option 1**: an external container/wrapper object, used purely as metadata.

### Consequences

- Good, because `AIAgent` and `AgentSession` remain unchanged, avoiding any increase to the core framework surface area while still enabling extensible metadata.
- Good, because an external wrapper (owned by hosting/protocol libraries or user code, not the `AIAgent` / `AgentSession` base classes) can internally use `AdditionalPropertiesDictionary` to stay consistent with existing patterns on `AgentRunOptions`, `AgentResponse`, and `AgentResponseUpdate`.
- Good, because metadata-only semantics keep a clean separation from per-run extensibility (`AgentRunOptions.AdditionalProperties`) and avoid unexpected side effects during agent execution.
- Good, because no additional allocation occurs on `AIAgent` or `AgentSession` when no metadata is needed; external wrappers can be created only when metadata is required.
- Bad, because callers and libraries must manage and pass around both the agent/session instance and its associated metadata wrapper, keeping them correctly associated.
- Bad, because different hosting or protocol layers may define their own wrapper types, which can fragment the ecosystem unless conventions are agreed upon.

## Pros and Cons of the Options

### Option A — Public get-only property, auto-initialized

The property is always non-null and ready to use. Users add metadata after construction.

```csharp
public abstract partial class AIAgent
{
    public AdditionalPropertiesDictionary AdditionalProperties { get; } = new();
}

public abstract partial class AgentSession
{
    public AdditionalPropertiesDictionary AdditionalProperties { get; } = new();
}

// Usage
agent.AdditionalProperties["protocol"] = "A2A";
agent.AdditionalProperties.Add<MyAgentCardInfo>(cardInfo);
session.AdditionalProperties["tenant"] = tenantId;
```

- Good, because users never encounter `null` — no defensive null checks needed.
- Good, because the dictionary reference cannot be replaced, preventing accidental data loss.
- Good, because it is the simplest API surface to use.
- Neutral, because it always allocates, even when no metadata is needed. The allocation cost is negligible.
- Bad, because it cannot be set at construction time as a single object (users must populate it post-construction).

### Option B — Public get/set nullable property

Matches the existing pattern on `AgentRunOptions`, `AgentResponse`, and `AgentResponseUpdate`.

```csharp
public abstract partial class AIAgent
{
    public AdditionalPropertiesDictionary? AdditionalProperties { get; set; }
}

public abstract partial class AgentSession
{
    public AdditionalPropertiesDictionary? AdditionalProperties { get; set; }
}

// Usage
agent.AdditionalProperties ??= new();
agent.AdditionalProperties["protocol"] = "A2A";
session.AdditionalProperties ??= new();
session.AdditionalProperties["tenant"] = tenantId;
```

- Good, because it is consistent with the existing `AdditionalProperties` pattern on `AgentRunOptions` and `AgentResponse`.
- Good, because it avoids allocation when no metadata is needed.
- Bad, because every consumer must null-check before reading or writing.
- Bad, because the entire dictionary can be replaced, risking accidental loss of metadata set by other components (e.g., a hosting library sets metadata, then user code replaces the dictionary).

### Option C — Constructor-injected with public get

The dictionary is provided at construction time and exposed as get-only.

```csharp
public abstract partial class AIAgent
{
    public AdditionalPropertiesDictionary AdditionalProperties { get; }

    protected AIAgent(AdditionalPropertiesDictionary? additionalProperties = null)
    {
        this.AdditionalProperties = additionalProperties ?? new();
    }
}

public abstract partial class AgentSession
{
    public AdditionalPropertiesDictionary AdditionalProperties { get; }

    protected AgentSession(AdditionalPropertiesDictionary? additionalProperties = null)
    {
        this.AdditionalProperties = additionalProperties ?? new();
    }
}
```

- Good, because an agent's metadata can be established before any code runs against it.
- Bad, because `AdditionalPropertiesDictionary` has no read-only variant, so the constructor-injection pattern gives a false sense of immutability — callers can still mutate the dictionary contents after construction.
- Bad, because it requires adding a constructor parameter to the abstract base classes, which is a source-breaking change for all existing `AIAgent` and `AgentSession` subclasses (even with a default value, it changes the constructor signature that derived classes chain to).
- Bad, because it is more complex with little practical benefit over Option A, since post-construction mutation is equally possible.

### Option D — External container/wrapper object

Rather than adding `AdditionalProperties` to `AIAgent` or `AgentSession`, users wrap the agent or session in a container object that carries both the instance and any associated metadata. No changes to the base classes are required.

```csharp
public class AgentWithMetadata
{
    public required AIAgent Agent { get; init; }
    public AdditionalPropertiesDictionary? AdditionalProperties { get; set; }
}

public class SessionWithMetadata
{
    public required AgentSession Session { get; init; }
    public AdditionalPropertiesDictionary? AdditionalProperties { get; set; }
}

// Usage
var wrapper = new AgentWithMetadata
{
    Agent = myAgent,
    AdditionalProperties = new() { ["protocol"] = "A2A" }
};
```

- Good, because it requires no changes to `AIAgent` or `AgentSession`, avoiding any risk of breaking existing implementations.
- Good, because metadata is clearly external to the agent and session, eliminating any ambiguity about whether it might be passed down the execution stack.
- Good, because the container pattern gives the user full control over the metadata lifecycle and serialization.
- Bad, because it is not discoverable — users must know about the container convention; there is no built-in API surface guiding them.

### Option 1 — Metadata only

`AdditionalProperties` on `AIAgent` and `AgentSession` is descriptive metadata. It is **not** automatically propagated when the agent calls downstream services such as `IChatClient`.

- Good, because it keeps a clean separation of concerns: agent/session-level metadata vs. per-run options.
- Good, because it avoids unintended side effects — metadata added for discovery or hosting won't leak into LLM requests.
- Good, because per-run extensibility is already served by `AgentRunOptions.AdditionalProperties` (see [ADR 0014](0014-feature-collections.md)), so there is no gap.
- Neutral, because users who want to pass agent metadata to the chat client can still do so manually via `AgentRunOptions`.

### Option 2 — Passed down the stack

`AdditionalProperties` on `AIAgent` and `AgentSession` are automatically merged into `ChatOptions.AdditionalProperties` (or similar) when `ChatClientAgent` invokes the underlying `IChatClient`.

- Good, because it provides an automatic way to send agent-level configuration to the LLM provider.
- Bad, because it conflates metadata (describing the agent) with operational parameters (controlling LLM behavior), leading to potential confusion.
- Bad, because it risks leaking unrelated metadata into LLM calls (e.g., hosting tags, discovery URLs).
- Bad, because it would be `ChatClientAgent`-specific behavior on a base-class property, creating inconsistency for non-`ChatClientAgent` implementations.
- Bad, because it duplicates the purpose of `AgentRunOptions.AdditionalProperties`, which already serves as the per-run extensibility point for passing data down the stack.

## Serialization Considerations

`AIAgent` instances are not typically serialized, so `AdditionalProperties` on `AIAgent` does not raise serialization concerns.

`AgentSession` instances, however, are routinely serialized and deserialized — for example, to persist conversation state across application restarts. Adding `AdditionalProperties` to `AgentSession` introduces a serialization challenge: `AdditionalPropertiesDictionary` is a `Dictionary<string, object?>`, and `object?` values do not carry enough type information for the JSON deserializer to reconstruct the original CLR types.

### Default behavior — JsonElement round-tripping

By default, when an `AgentSession` with `AdditionalProperties` is serialized and later deserialized, any complex objects stored as values in the dictionary will be deserialized as `JsonElement` rather than their original types. This is the same behavior exhibited by `ChatMessage.AdditionalProperties` and other `AdditionalPropertiesDictionary` usages in `Microsoft.Extensions.AI`, and is the approach we will follow.

### Custom serialization via JsonSerializerOptions

`AIAgent.SerializeSessionAsync` and `AIAgent.DeserializeSessionAsync` already accept an optional `JsonSerializerOptions` parameter. Users who need strongly-typed round-tripping of `AdditionalProperties` values can supply custom options with appropriate converters or type info resolvers. This is non-trivial to implement but provides full control over deserialization behavior when needed.

## More Information

- [ADR 0014 — Feature Collections](0014-feature-collections.md) established that `AdditionalProperties` on `AgentRunOptions` serves as the per-run extensibility mechanism. The proposed agent-level and session-level properties serve a complementary, distinct purpose: static metadata describing the agent or session itself.
- `AdditionalPropertiesDictionary` is defined in `Microsoft.Extensions.AI` and is already a dependency of `Microsoft.Agents.AI.Abstractions`. No new package references are needed.
- Type-safe access is available via the existing `AdditionalPropertiesExtensions` helper methods (`Add<T>`, `TryGetValue<T>`, `Contains<T>`, `Remove<T>`), which use `typeof(T).FullName` as the dictionary key.
