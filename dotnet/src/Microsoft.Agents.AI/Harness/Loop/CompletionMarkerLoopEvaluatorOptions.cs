// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics.CodeAnalysis;
using Microsoft.Shared.DiagnosticIds;

namespace Microsoft.Agents.AI;

/// <summary>
/// Provides configuration options for <see cref="CompletionMarkerLoopEvaluator"/>.
/// </summary>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public sealed class CompletionMarkerLoopEvaluatorOptions
{
    /// <summary>
    /// Gets or sets the template used to build the feedback produced when the completion marker has not yet appeared,
    /// or <see langword="null"/> to use <see cref="CompletionMarkerLoopEvaluator.DefaultFeedbackMessageTemplate"/>.
    /// </summary>
    /// <remarks>
    /// Any occurrence of <see cref="CompletionMarkerLoopEvaluator.CompletionMarkerPlaceholder"/> in the template is
    /// replaced with the configured completion marker. Any occurrence of
    /// <see cref="CompletionMarkerLoopEvaluator.LastResponsePlaceholder"/> is replaced, on each evaluation, with the
    /// text of the agent's latest response — useful for echoing the agent's prior output back to it when the consuming
    /// <see cref="CompletionMarkerLoopEvaluator"/> is used with a fresh context per iteration.
    /// </remarks>
    public string? FeedbackMessageTemplate { get; set; }
}
