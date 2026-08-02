// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Globalization;
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

    /// <summary>
    /// Asserts that every per-evaluator score on every item is at least <paramref name="minScore"/>.
    /// </summary>
    /// <remarks>
    /// <para>
    /// Designed for CI gates on generated rubric evaluators (for example
    /// <c>results.AssertScoreAtLeast(0.80)</c>). Walks <see cref="DetailedItems"/> across this
    /// result and any <see cref="SubResults"/> from workflow evaluations.
    /// </para>
    /// <para>
    /// When <see cref="DetailedItems"/> is <see langword="null"/>, the assertion is a no-op for
    /// this level. Providers that surface per-evaluator scores (such as Foundry) populate
    /// <see cref="DetailedItems"/>; providers that only emit aggregate <see cref="Items"/>
    /// metrics do not.
    /// </para>
    /// </remarks>
    /// <param name="minScore">Minimum acceptable score (inclusive).</param>
    /// <param name="evaluator">
    /// When set, only check scores whose <see cref="EvalScoreResult.Name"/> matches.
    /// </param>
    /// <param name="message">Optional custom failure message.</param>
    /// <exception cref="InvalidOperationException">
    /// Thrown when any matching score is below the threshold.
    /// </exception>
    public void AssertScoreAtLeast(double minScore, string? evaluator = null, string? message = null)
    {
        var offenders = new List<string>();
        CollectScoreOffenders(this, minScore, evaluator, offenders);

        if (offenders.Count > 0)
        {
            throw new InvalidOperationException(
                message ?? FormatOffenders(
                    $"{offenders.Count} score(s) below threshold {minScore.ToString(CultureInfo.InvariantCulture)}"
                        + (evaluator is not null ? $" for {evaluator}" : string.Empty),
                    offenders));
        }
    }

    /// <summary>
    /// Asserts that every item's score for the given rubric dimension is at least
    /// <paramref name="minScore"/>.
    /// </summary>
    /// <remarks>
    /// Walks <see cref="EvalScoreResult.Dimensions"/> across <see cref="DetailedItems"/>
    /// (and any <see cref="SubResults"/>) looking for the named dimension. Non-applicable
    /// dimensions are skipped by default; pass <paramref name="requireApplicable"/>=<see langword="true"/>
    /// to fail when no applicable score is produced for an item. If dimension data exists
    /// but the requested <paramref name="dimensionId"/> is never present, the assertion fails
    /// to surface likely typos or evaluator mismatches.
    /// </remarks>
    /// <param name="dimensionId">Dimension id — matches the rubric definition.</param>
    /// <param name="minScore">Minimum acceptable dimension score (inclusive).</param>
    /// <param name="evaluator">
    /// When set, only consider scores whose <see cref="EvalScoreResult.Name"/> matches.
    /// </param>
    /// <param name="requireApplicable">
    /// When <see langword="true"/>, items with no applicable score for the dimension also fail
    /// the assertion. Defaults to <see langword="false"/> (skip).
    /// </param>
    /// <param name="message">Optional custom failure message.</param>
    /// <exception cref="InvalidOperationException">
    /// Thrown when the dimension fails the threshold on any item.
    /// </exception>
    public void AssertDimensionScoreAtLeast(
        string dimensionId,
        double minScore,
        string? evaluator = null,
        bool requireApplicable = false,
        string? message = null)
    {
        var offenders = new List<string>();
        var missing = new List<string>();
        CollectDimensionOffenders(this, dimensionId, minScore, evaluator, requireApplicable, offenders, missing);

        var problems = new List<string>();
        bool hasAnyDimensionData = HasAnyDimensionData(this, evaluator);
        if (hasAnyDimensionData && !HasDimension(this, dimensionId, evaluator))
        {
            problems.Add(
                $"Dimension '{dimensionId}' was not found in results"
                + (evaluator is not null ? $" for evaluator '{evaluator}'." : "."));
        }

        if (offenders.Count > 0)
        {
            problems.Add(FormatOffenders(
                $"{offenders.Count} dimension score(s) for '{dimensionId}' below {minScore.ToString(CultureInfo.InvariantCulture)}",
                offenders));
        }

        if (missing.Count > 0)
        {
            problems.Add(FormatOffenders(
                $"Dimension '{dimensionId}' not applicable on {missing.Count} item(s)",
                missing));
        }

        if (problems.Count > 0)
        {
            throw new InvalidOperationException(message ?? string.Join("; ", problems));
        }
    }

    /// <summary>
    /// Asserts that no item ended in a failed or errored state. Includes any sub-results
    /// from workflow evaluations.
    /// </summary>
    /// <param name="message">Optional custom failure message.</param>
    /// <exception cref="InvalidOperationException">
    /// Thrown when any item failed or errored.
    /// </exception>
    public void AssertNoFailedItems(string? message = null)
    {
        var bad = new List<string>();
        CollectFailedItems(this, bad);

        if (bad.Count > 0)
        {
            throw new InvalidOperationException(
                message ?? FormatOffenders($"{bad.Count} item(s) failed or errored", bad));
        }
    }

    private static void CollectScoreOffenders(
        AgentEvaluationResults results,
        double minScore,
        string? evaluator,
        List<string> offenders)
    {
        if (results.DetailedItems is not null)
        {
            foreach (var item in results.DetailedItems)
            {
                foreach (var score in item.Scores)
                {
                    if (evaluator is not null && score.Name != evaluator)
                    {
                        continue;
                    }

                    if (score.Score < minScore)
                    {
                        offenders.Add($"{item.ItemId}/{score.Name}={score.Score.ToString("F3", CultureInfo.InvariantCulture)}");
                    }
                }
            }
        }

        if (results.SubResults is not null)
        {
            foreach (var sub in results.SubResults.Values)
            {
                CollectScoreOffenders(sub, minScore, evaluator, offenders);
            }
        }
    }

    private static void CollectDimensionOffenders(
        AgentEvaluationResults results,
        string dimensionId,
        double minScore,
        string? evaluator,
        bool requireApplicable,
        List<string> offenders,
        List<string> missing)
    {
        if (results.DetailedItems is not null)
        {
            foreach (var item in results.DetailedItems)
            {
                bool foundApplicable = false;
                foreach (var score in item.Scores)
                {
                    if (evaluator is not null && score.Name != evaluator)
                    {
                        continue;
                    }

                    if (score.Dimensions is null)
                    {
                        continue;
                    }

                    foreach (var rs in score.Dimensions)
                    {
                        if (rs.Id != dimensionId)
                        {
                            continue;
                        }

                        if (!rs.Applicable)
                        {
                            continue;
                        }

                        foundApplicable = true;
                        if (rs.Score is null || rs.Score.Value < minScore)
                        {
                            var actual = rs.Score is null
                                ? "null"
                                : rs.Score.Value.ToString(CultureInfo.InvariantCulture);
                            offenders.Add($"{item.ItemId}/{score.Name}/{dimensionId}={actual}");
                        }
                    }
                }

                if (requireApplicable && !foundApplicable)
                {
                    missing.Add(item.ItemId);
                }
            }
        }

        if (results.SubResults is not null)
        {
            foreach (var sub in results.SubResults.Values)
            {
                CollectDimensionOffenders(sub, dimensionId, minScore, evaluator, requireApplicable, offenders, missing);
            }
        }
    }

    private static void CollectFailedItems(AgentEvaluationResults results, List<string> bad)
    {
        if (results.DetailedItems is not null)
        {
            foreach (var item in results.DetailedItems)
            {
                if (item.IsFailed || item.IsError)
                {
                    bad.Add($"{item.ItemId}:{item.Status}");
                }
            }
        }

        if (results.SubResults is not null)
        {
            foreach (var sub in results.SubResults.Values)
            {
                CollectFailedItems(sub, bad);
            }
        }
    }

    private static bool HasAnyDimensionData(AgentEvaluationResults results, string? evaluator)
    {
        if (results.DetailedItems is not null)
        {
            foreach (var item in results.DetailedItems)
            {
                foreach (var score in item.Scores)
                {
                    if (evaluator is not null && score.Name != evaluator)
                    {
                        continue;
                    }

                    if (score.Dimensions is { Count: > 0 })
                    {
                        return true;
                    }
                }
            }
        }

        if (results.SubResults is not null)
        {
            foreach (var sub in results.SubResults.Values)
            {
                if (HasAnyDimensionData(sub, evaluator))
                {
                    return true;
                }
            }
        }

        return false;
    }

    private static bool HasDimension(AgentEvaluationResults results, string dimensionId, string? evaluator)
    {
        if (results.DetailedItems is not null)
        {
            foreach (var item in results.DetailedItems)
            {
                foreach (var score in item.Scores)
                {
                    if (evaluator is not null && score.Name != evaluator)
                    {
                        continue;
                    }

                    if (score.Dimensions is null)
                    {
                        continue;
                    }

                    if (score.Dimensions.Any(rs => rs.Id == dimensionId))
                    {
                        return true;
                    }
                }
            }
        }

        if (results.SubResults is not null)
        {
            foreach (var sub in results.SubResults.Values)
            {
                if (HasDimension(sub, dimensionId, evaluator))
                {
                    return true;
                }
            }
        }

        return false;
    }

    private static string FormatOffenders(string prefix, List<string> offenders)
    {
        const int MaxShown = 5;
        if (offenders.Count <= MaxShown)
        {
            return $"{prefix}: {string.Join(", ", offenders)}";
        }

        var shown = string.Join(", ", offenders.GetRange(0, MaxShown));
        return $"{prefix}: {shown} (+{offenders.Count - MaxShown} more)";
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
