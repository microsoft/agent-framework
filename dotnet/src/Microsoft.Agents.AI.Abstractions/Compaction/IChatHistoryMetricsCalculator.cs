// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Compaction;

// %%% TODO: Is this interface needed? Consider whether the default implementation is sufficient
// and whether custom metrics calculators are a realistic extension point.

/// <summary>
/// Computes <see cref="CompactionMetric"/> for a list of messages.
/// </summary>
/// <remarks>
/// Token counting is model-specific. Implementations can provide precise tokenization
/// (e.g., using tiktoken or a model-specific tokenizer) or use estimation heuristics.
/// </remarks>
public interface IChatHistoryMetricsCalculator // %%% NEEDED ???
{
    /// <summary>
    /// Compute metrics for the given messages.
    /// </summary>
    /// <param name="messages">The messages to analyze.</param>
    /// <returns>A <see cref="CompactionMetric"/> snapshot.</returns>
    CompactionMetric Calculate(IReadOnlyList<ChatMessage> messages);
}
