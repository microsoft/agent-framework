// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics.CodeAnalysis;
using Microsoft.Shared.DiagnosticIds;

namespace Microsoft.Agents.AI.Compaction;

#pragma warning disable IDE0001 // Simplify Names for namespace in comments

/// <summary>
/// Describes the compaction approach used by a pre-configured <see cref="CompactionStrategy"/>.
/// </summary>
/// <seealso cref="CompactionStrategy.Create"/>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public enum CompactionApproach
{
    /// <summary>
    /// Applies the lightest available compaction techniques.
    /// Collapses old tool call groups into concise summaries and uses truncation as an emergency backstop.
    /// </summary>
    Gentle,

    /// <summary>
    /// Balances context preservation with compaction efficiency.
    /// Applies tool result collapsing, LLM-based summarization, and truncation as an emergency backstop.
    /// </summary>
    Balanced,

    /// <summary>
    /// Applies the most aggressive available compaction techniques.
    /// Applies tool result collapsing, LLM-based summarization, turn-based sliding window, and truncation.
    /// </summary>
    Aggressive,
}

#pragma warning restore IDE0001 // Simplify Names
