// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI.AzureAI.ContentUnderstanding;

/// <summary>
/// Selects how <see cref="ContentUnderstandingContextProvider"/> scopes its tracked document
/// registry.
/// </summary>
public enum StateScope
{
    /// <summary>
    /// Default. State is partitioned by <c>AgentSession</c>; multiple users sharing one
    /// provider instance get isolated document caches, including the built-in tools which are
    /// rebuilt per turn against the calling session's partition (safe under concurrent use).
    /// When the hosting layer creates a fresh session per HTTP request, state is lost across
    /// turns — use <see cref="PerAgent"/> instead.
    /// </summary>
    PerSession = 0,

    /// <summary>
    /// State is keyed by <c>Agent.Id ?? Agent.Name</c>, ignoring any session supplied by the
    /// caller. Use this when a single agent instance serves one logical user (e.g. DevUI,
    /// CLI samples, or any host that does not persist session state across turns). Sharing
    /// one provider across multiple end-users in this mode would cross-contaminate caches.
    /// </summary>
    PerAgent = 1,
}
