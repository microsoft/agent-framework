// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using Microsoft.Shared.DiagnosticIds;

namespace Microsoft.Agents.AI;

/// <summary>
/// Provides configuration options for <see cref="AIJudgeLoopEvaluator"/>.
/// </summary>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public sealed class AIJudgeLoopEvaluatorOptions
{
    /// <summary>
    /// Gets or sets the system instructions used to prompt the judge, or <see langword="null"/> to use
    /// <see cref="AIJudgeLoopEvaluator.DefaultInstructions"/>.
    /// </summary>
    /// <remarks>
    /// Any occurrence of <see cref="AIJudgeLoopEvaluator.CriteriaPlaceholder"/> in the instructions is replaced with
    /// the rendered <see cref="Criteria"/> (or removed when no criteria are supplied). Instructions that omit the
    /// placeholder do not receive the criteria.
    /// </remarks>
    public string? Instructions { get; set; }

    /// <summary>
    /// Gets or sets an optional list of additional criteria the agent's response must satisfy, evaluated by the judge
    /// alongside the original request.
    /// </summary>
    /// <remarks>
    /// When supplied, the criteria are rendered into the judge instructions wherever
    /// <see cref="AIJudgeLoopEvaluator.CriteriaPlaceholder"/> appears (including in
    /// <see cref="AIJudgeLoopEvaluator.DefaultInstructions"/>). When <see langword="null"/> or empty, the placeholder is
    /// removed and no criteria are added.
    /// </remarks>
    public IEnumerable<string>? Criteria { get; set; }

    /// <summary>
    /// Gets or sets the template used to build the feedback produced when the judge decides the original request was
    /// not fully addressed, or <see langword="null"/> to use
    /// <see cref="AIJudgeLoopEvaluator.DefaultFeedbackMessageTemplate"/>.
    /// </summary>
    /// <remarks>
    /// Any occurrence of <see cref="AIJudgeLoopEvaluator.GapAnalysisPlaceholder"/> in the template is replaced with the
    /// judge's gap analysis (or a placeholder when none is available).
    /// </remarks>
    public string? FeedbackMessageTemplate { get; set; }
}
