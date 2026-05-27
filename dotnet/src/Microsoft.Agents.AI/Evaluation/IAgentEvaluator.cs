// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Agents.AI;

/// <summary>
/// Batch-oriented evaluator interface for agent evaluation.
/// </summary>
/// <remarks>
/// Unlike MEAI's <c>IEvaluator</c> which evaluates one item at a time,
/// <see cref="IAgentEvaluator"/> evaluates a batch of items. This enables
/// efficient cloud-based evaluation (e.g., Foundry) and aggregate result computation.
/// </remarks>
public interface IAgentEvaluator
{
    /// <summary>Gets the evaluator name.</summary>
    string Name { get; }

    /// <summary>
    /// Evaluates a batch of items and returns aggregate results.
    /// </summary>
    /// <param name="items">The items to evaluate.</param>
    /// <param name="evalName">A display name for this evaluation run.</param>
    /// <param name="cancellationToken">Cancellation token.</param>
    /// <returns>Aggregate evaluation results.</returns>
    Task<AgentEvaluationResults> EvaluateAsync(
        IReadOnlyList<EvalItem> items,
        string evalName = "Agent Framework Eval",
        CancellationToken cancellationToken = default);
}
