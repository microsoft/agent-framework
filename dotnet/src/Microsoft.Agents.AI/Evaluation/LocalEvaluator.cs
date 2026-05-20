// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI.Evaluation;

namespace Microsoft.Agents.AI;

/// <summary>
/// Evaluator that runs check functions locally without API calls.
/// </summary>
public sealed class LocalEvaluator : IAgentEvaluator
{
    private readonly EvalCheck[] _checks;

    /// <summary>
    /// Initializes a new instance of the <see cref="LocalEvaluator"/> class.
    /// </summary>
    /// <param name="checks">The check functions to run on each item.</param>
    public LocalEvaluator(params EvalCheck[] checks)
    {
        this._checks = checks;
    }

    /// <inheritdoc />
    public string Name => "LocalEvaluator";

    /// <inheritdoc />
    public Task<AgentEvaluationResults> EvaluateAsync(
        IReadOnlyList<EvalItem> items,
        string evalName = "Local Eval",
        CancellationToken cancellationToken = default)
    {
        var results = new List<EvaluationResult>(items.Count);

        foreach (var item in items)
        {
            cancellationToken.ThrowIfCancellationRequested();

            var evalResult = new EvaluationResult();

            foreach (var check in this._checks)
            {
                var EvalCheckResult = check(item);
                evalResult.Metrics[EvalCheckResult.CheckName] = new BooleanMetric(
                    EvalCheckResult.CheckName,
                    EvalCheckResult.Passed,
                    reason: EvalCheckResult.Reason)
                {
                    Interpretation = new EvaluationMetricInterpretation
                    {
                        Rating = EvalCheckResult.Passed
                            ? EvaluationRating.Good
                            : EvaluationRating.Unacceptable,
                        Failed = !EvalCheckResult.Passed,
                    },
                };
            }

            results.Add(evalResult);
        }

        return Task.FromResult(new AgentEvaluationResults(this.Name, results, inputItems: items));
    }
}
