// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Diagnostics.CodeAnalysis;
using Microsoft.Shared.DiagnosticIds;

namespace Microsoft.Agents.AI;

/// <summary>
/// Options for configuring <see cref="CachingAgentSkillsSource"/>.
/// </summary>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public sealed class CachingAgentSkillsSourceOptions
{
    /// <summary>
    /// Gets or sets a delegate that returns the cache isolation key for a skills source invocation.
    /// </summary>
    /// <remarks>
    /// <para>
    /// When this delegate is <see langword="null"/>, or when it returns <see langword="null"/>,
    /// the skills are stored in the shared cache bucket. When it returns a non-null string,
    /// the skills are cached under that key.
    /// </para>
    /// <para>
    /// The isolation key should be low-cardinality and stable.
    /// High-cardinality keys (for example, per-session IDs) can cause the cache to grow without bound.
    /// </para>
    /// </remarks>
    public Func<AgentSkillsSourceContext, string?>? CacheIsolationKeySelector { get; set; }
}
