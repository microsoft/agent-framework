// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using Microsoft.Extensions.AI.Evaluation;

namespace Microsoft.Agents.AI;

/// <summary>
/// Aggregate evaluation results across multiple items.
/// </summary>
public sealed class AgentEvaluationResults
{
    private readonly List<EvaluationResult> _items;

    /// <summary>
    /// Initializes a new instance of the <see cref="AgentEvaluationResults"/> class.
    /// </summary>
    /// <param name="providerName">Name of the evaluation provider.</param>
    /// <param name="items">Per-item MEAI evaluation results.</param>
    /// <param name="inputItems">The original eval items that were evaluated, for auditing.</param>
    public AgentEvaluationResults(string providerName, IEnumerable<EvaluationResult> items, IReadOnlyList<EvalItem>? inputItems = null)
    {
        this.ProviderName = providerName;
        this._items = new List<EvaluationResult>(items);
        this.InputItems = inputItems;
    }

    /// <summary>Gets the evaluation provider name.</summary>
    public string ProviderName { get; }

    /// <summary>Gets the portal URL for viewing results (Foundry only).</summary>
    public Uri? ReportUrl { get; set; }

    /// <summary>Gets the Foundry evaluation ID (Foundry only).</summary>
    public string? EvalId { get; set; }

    /// <summary>Gets the Foundry evaluation run ID (Foundry only).</summary>
    public string? RunId { get; set; }

    /// <summary>Gets the evaluation run status (e.g., "completed", "failed", "canceled", "timeout").</summary>
    public string? Status { get; set; }

    /// <summary>Gets error details when the evaluation run failed.</summary>
    public string? Error { get; set; }

    /// <summary>Gets the per-item MEAI evaluation results.</summary>
    public IReadOnlyList<EvaluationResult> Items => this._items;

    /// <summary>
    /// Gets the original eval items that produced these results, for auditing.
    /// Each entry corresponds positionally to <see cref="Items"/> — <c>InputItems[i]</c>
    /// is the query/response that produced <c>Items[i]</c>.
    /// </summary>
    public IReadOnlyList<EvalItem>? InputItems { get; }

    /// <summary>Gets per-agent results for workflow evaluations.</summary>
    public IReadOnlyDictionary<string, AgentEvaluationResults>? SubResults { get; set; }

    /// <summary>Gets per-evaluator pass/fail breakdown (Foundry only).</summary>
    public IReadOnlyDictionary<string, PerEvaluatorResult>? PerEvaluator { get; set; }

    /// <summary>
    /// Gets detailed per-item results from the Foundry output_items API,
    /// including individual evaluator scores, error info, and token usage.
    /// </summary>
    public IReadOnlyList<EvalItemResult>? DetailedItems { get; set; }

    /// <summary>Gets the number of items that passed.</summary>
    public int Passed => this._items.Count(ItemPassed);

    /// <summary>Gets the number of items that failed.</summary>
    public int Failed => this._items.Count(i => !ItemPassed(i));

    /// <summary>Gets the total number of items evaluated.</summary>
    public int Total => this._items.Count;

    /// <summary>Gets whether all items passed.</summary>
    public bool AllPassed
    {
        get
        {
            if (this.SubResults is not null)
            {
                return this.SubResults.Values.All(s => s.AllPassed)
                    && (this.Total == 0 || this.Failed == 0);
            }

            return this.Total > 0 && this.Failed == 0;
        }
    }

    /// <summary>
    /// Asserts that all items passed. Throws <see cref="InvalidOperationException"/> on failure.
    /// </summary>
    /// <param name="message">Optional custom failure message.</param>
    /// <exception cref="InvalidOperationException">Thrown when any items failed.</exception>
    public void AssertAllPassed(string? message = null)
    {
        if (!this.AllPassed)
        {
            var detail = message ?? $"{this.ProviderName}: {this.Passed} passed, {this.Failed} failed out of {this.Total}.";
            if (this.ReportUrl is not null)
            {
                detail += $" See {this.ReportUrl} for details.";
            }

            if (this.SubResults is not null)
            {
                var failedAgents = this.SubResults
                    .Where(kvp => !kvp.Value.AllPassed)
                    .Select(kvp => kvp.Key);
                detail += $" Failed agents: {string.Join(", ", failedAgents)}.";
            }

            throw new InvalidOperationException(detail);
        }
    }

    private static bool ItemPassed(EvaluationResult result)
    {
        foreach (var metric in result.Metrics.Values)
        {
            // Trust the evaluator's own pass/fail determination first.
            if (metric.Interpretation?.Failed == true)
            {
                return false;
            }

            // A boolean false is unambiguous — the check failed.
            if (metric is BooleanMetric boolean && boolean.Value == false)
            {
                return false;
            }

            // Numeric metrics without Interpretation are informational scores;
            // the evaluator should set Interpretation if it wants pass/fail semantics.
        }

        return result.Metrics.Count > 0;
    }
}
