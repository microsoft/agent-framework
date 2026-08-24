// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using Microsoft.Shared.DiagnosticIds;

namespace Microsoft.Agents.AI;

/// <summary>
/// Provides configuration options for <see cref="TodoCompletionLoopEvaluator"/>.
/// </summary>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public sealed class TodoCompletionLoopEvaluatorOptions
{
    /// <summary>
    /// Gets or sets the set of mode names for which the evaluator drives re-invocation, or <see langword="null"/> to
    /// apply in every mode.
    /// </summary>
    /// <remarks>
    /// When <see langword="null"/>, the evaluator applies in every mode and no <see cref="AgentModeProvider"/> is
    /// required. When non-<see langword="null"/> it must contain at least one non-empty mode name; mode names are
    /// matched ordinally and an <see cref="AgentModeProvider"/> must be resolvable from the agent at evaluation time.
    /// </remarks>
    public IEnumerable<string>? Modes { get; set; }

    /// <summary>
    /// Gets or sets the template used to build the feedback produced while incomplete todo items remain,
    /// or <see langword="null"/> to use <see cref="TodoCompletionLoopEvaluator.DefaultFeedbackMessageTemplate"/>.
    /// </summary>
    /// <remarks>
    /// Any occurrence of <see cref="TodoCompletionLoopEvaluator.RemainingTodosPlaceholder"/> in the template is
    /// replaced, on each evaluation, with a formatted list of the remaining (incomplete) todo items. When the
    /// placeholder is absent the rendered list is not appended.
    /// </remarks>
    public string? FeedbackMessageTemplate { get; set; }
}
