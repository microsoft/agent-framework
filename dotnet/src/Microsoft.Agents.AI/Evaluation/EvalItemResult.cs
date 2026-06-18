// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Linq;

namespace Microsoft.Agents.AI;

/// <summary>
/// Per-item result from a Foundry evaluation run, with individual evaluator scores and error details.
/// </summary>
public sealed class EvalItemResult
{
    /// <summary>
    /// Initializes a new instance of the <see cref="EvalItemResult"/> class.
    /// </summary>
    /// <param name="itemId">The output item ID from the evaluation API.</param>
    /// <param name="status">The item evaluation status (e.g., "pass", "fail", "error").</param>
    /// <param name="scores">Per-evaluator score results.</param>
    public EvalItemResult(string itemId, string status, IReadOnlyList<EvalScoreResult> scores)
    {
        this.ItemId = itemId;
        this.Status = status;
        this.Scores = scores;
    }

    /// <summary>Gets the output item ID from the evaluation API.</summary>
    public string ItemId { get; }

    /// <summary>Gets the item evaluation status (e.g., "pass", "fail", "error", "errored").</summary>
    public string Status { get; }

    /// <summary>Gets the per-evaluator score results.</summary>
    public IReadOnlyList<EvalScoreResult> Scores { get; }

    /// <summary>Gets or sets an error code when the item evaluation errored.</summary>
    public string? ErrorCode { get; set; }

    /// <summary>Gets or sets an error message when the item evaluation errored.</summary>
    public string? ErrorMessage { get; set; }

    /// <summary>Gets or sets the response ID from the evaluation API (e.g., for response-based evals).</summary>
    public string? ResponseId { get; set; }

    /// <summary>Gets or sets the input text echoed back by the evaluation API.</summary>
    public string? InputText { get; set; }

    /// <summary>Gets or sets the output text echoed back by the evaluation API.</summary>
    public string? OutputText { get; set; }

    /// <summary>Gets or sets token usage information from the evaluation.</summary>
    public IReadOnlyDictionary<string, int>? TokenUsage { get; set; }

    /// <summary>Gets whether this item is in an error state.</summary>
    public bool IsError => this.Status is "error" or "errored";

    /// <summary>Gets whether this item passed all evaluators.</summary>
    public bool IsPassed => this.Scores.Count > 0 && this.Scores.All(s => s.Passed == true);

    /// <summary>Gets whether this item failed any evaluator.</summary>
    public bool IsFailed => this.Scores.Any(s => s.Passed == false);
}

/// <summary>
/// A single evaluator's score on one evaluation item.
/// </summary>
/// <param name="Name">The evaluator name that produced this score.</param>
/// <param name="Score">The numeric score value.</param>
/// <param name="Passed">Whether the evaluator considered this a pass, or null if not determined.</param>
public record EvalScoreResult(string Name, double Score, bool? Passed = null);

/// <summary>
/// Per-evaluator pass/fail breakdown from an evaluation run.
/// </summary>
/// <param name="Passed">Number of items that passed for this evaluator.</param>
/// <param name="Failed">Number of items that failed for this evaluator.</param>
public record PerEvaluatorResult(int Passed, int Failed);
