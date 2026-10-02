// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics.CodeAnalysis;
using Microsoft.Shared.DiagnosticIds;

namespace Microsoft.Agents.AI.Compaction;

/// <summary>
/// Describes the context-size profile used by a pre-configured <see cref="CompactionStrategy"/>.
/// </summary>
/// <remarks>
/// The size profile controls the token and message thresholds at which compaction triggers.
/// Choose a size that matches the input token limit of your model:
/// <see cref="Compact"/> for smaller context windows, <see cref="Moderate"/> for common mid-range models,
/// and <see cref="Generous"/> for models with large context windows.
/// </remarks>
/// <seealso cref="CompactionStrategy.Create"/>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public enum CompactionSize
{
    /// <summary>
    /// Maintains a smaller context window.
    /// Compaction triggers earlier and keeps less history in context.
    /// </summary>
    Compact,

    /// <summary>
    /// Maintains a medium-sized context window.
    /// This is a reasonable default for most common models.
    /// </summary>
    Moderate,

    /// <summary>
    /// Maintains a large context window.
    /// Compaction triggers later and retains more history in context.
    /// </summary>
    Generous,
}
