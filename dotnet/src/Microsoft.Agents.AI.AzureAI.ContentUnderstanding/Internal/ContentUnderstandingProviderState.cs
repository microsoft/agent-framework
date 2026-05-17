// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Concurrent;

namespace Microsoft.Agents.AI.AzureAI.ContentUnderstanding;

/// <summary>
/// Per-session state persisted by <see cref="ContentUnderstandingContextProvider"/> into
/// <c>AgentSession.StateBag</c>.
/// </summary>
/// <remarks>
/// Holds the document registry plus the set of document keys already injected into the
/// LLM context (so cross-turn promotion does not re-inject). Serialized with
/// <c>System.Text.Json</c>; <see cref="ConcurrentDictionary{TKey,TValue}"/> and
/// <see cref="HashSet{T}"/> are both round-trippable.
/// </remarks>
internal sealed class ContentUnderstandingProviderState
{
    /// <summary>Document registry keyed by <see cref="DocumentEntry.DocumentKey"/>.</summary>
    public ConcurrentDictionary<string, DocumentEntry> Documents { get; init; } = new();

    /// <summary>Keys of documents whose rendered result has already been injected into a turn.</summary>
    /// <remarks>
    /// Used by Phase 6 cross-turn promotion to avoid duplicate injection. Persisted to state
    /// so it survives serialization across turns.
    /// </remarks>
    public HashSet<string> InjectedKeys { get; init; } = new(StringComparer.Ordinal);
}
