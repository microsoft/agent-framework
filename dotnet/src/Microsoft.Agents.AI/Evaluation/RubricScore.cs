// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI;

/// <summary>
/// A single dimension's score from a rubric-based evaluator run.
/// </summary>
/// <remarks>
/// <para>
/// Rubric evaluators (such as the generated rubric evaluators produced by Azure AI Foundry's
/// adaptive evals) emit one <see cref="RubricScore"/> per dimension per item, alongside an
/// overall weighted score. Attach instances to <see cref="EvalScoreResult.Dimensions"/> as
/// a typed view of the per-dimension breakdown returned by the provider
/// (e.g. <c>properties.dimension_scores</c>).
/// </para>
/// <para>
/// Non-rubric evaluators (built-in quality, safety, or agent-behavior evaluators) leave
/// <see cref="EvalScoreResult.Dimensions"/> as <see langword="null"/>.
/// </para>
/// </remarks>
/// <param name="Id">Dimension identifier — matches the id defined on the rubric.</param>
/// <param name="Score">
/// Numeric score for the dimension, or <see langword="null"/> when the dimension was marked
/// non-applicable for this item. Foundry rubric evaluators emit integer scores on a 1–5 scale.
/// </param>
/// <param name="Applicable">Whether the dimension applied to this item.</param>
/// <param name="Weight">Dimension weight, mirroring the rubric definition.</param>
/// <param name="Reason">Short rationale produced by the evaluator.</param>
public sealed record RubricScore(
    string Id,
    int? Score,
    bool Applicable,
    int Weight,
    string Reason);
