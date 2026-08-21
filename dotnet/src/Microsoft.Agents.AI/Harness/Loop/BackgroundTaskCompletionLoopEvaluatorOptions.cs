// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics.CodeAnalysis;
using Microsoft.Shared.DiagnosticIds;

namespace Microsoft.Agents.AI;

/// <summary>
/// Provides configuration options for <see cref="BackgroundTaskCompletionLoopEvaluator"/>.
/// </summary>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public sealed class BackgroundTaskCompletionLoopEvaluatorOptions
{
    /// <summary>
    /// Gets or sets the template used to build the feedback produced while background tasks are still running,
    /// or <see langword="null"/> to use <see cref="BackgroundTaskCompletionLoopEvaluator.DefaultFeedbackMessageTemplate"/>.
    /// </summary>
    /// <remarks>
    /// Any occurrence of <see cref="BackgroundTaskCompletionLoopEvaluator.IncompleteTasksPlaceholder"/> in the template
    /// is replaced, on each evaluation, with a formatted list of the background tasks that are still running, and any
    /// occurrence of <see cref="BackgroundTaskCompletionLoopEvaluator.IncompleteTaskCountPlaceholder"/> is replaced with
    /// the number of those tasks. When a placeholder is absent the corresponding value is not rendered.
    /// </remarks>
    public string? FeedbackMessageTemplate { get; set; }
}
