// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using System.Globalization;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Shared.DiagnosticIds;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI;

/// <summary>
/// A <see cref="LoopEvaluator"/> that keeps re-invoking the wrapped agent until a <see cref="BackgroundAgentsProvider"/>
/// reports that no background tasks are still running.
/// </summary>
/// <remarks>
/// <para>
/// The required <see cref="BackgroundAgentsProvider"/> is not supplied directly. It is resolved at evaluation time from
/// the looped agent via <see cref="AIAgent.GetService{TService}(object?)"/>. This works because an agent surfaces its
/// registered <see cref="AIContextProvider"/> instances through <c>GetService</c>, so a single
/// <see cref="BackgroundAgentsProvider"/> attached to the agent's session is discovered automatically.
/// </para>
/// <para>
/// Only tasks that are still running are treated as incomplete; completed, failed, and lost tasks are terminal and do
/// not keep the loop going. While running tasks remain, the evaluator continues with feedback built from a template (see
/// <see cref="BackgroundTaskCompletionLoopEvaluatorOptions.FeedbackMessageTemplate"/>), with the running task list
/// substituted for <see cref="IncompleteTasksPlaceholder"/> and the running task count substituted for
/// <see cref="IncompleteTaskCountPlaceholder"/>. How that feedback is delivered to the agent (and whether the session
/// is reset) is decided by the <see cref="LoopAgent"/> that consumes this evaluator.
/// </para>
/// </remarks>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public sealed class BackgroundTaskCompletionLoopEvaluator : LoopEvaluator
{
    /// <summary>
    /// The placeholder token within <see cref="DefaultFeedbackMessageTemplate"/> (or a custom
    /// <see cref="BackgroundTaskCompletionLoopEvaluatorOptions.FeedbackMessageTemplate"/>) that is replaced, on each
    /// evaluation, with a formatted list of the background tasks that are still running.
    /// </summary>
    public const string IncompleteTasksPlaceholder = "{incomplete_tasks}";

    /// <summary>
    /// The placeholder token within <see cref="DefaultFeedbackMessageTemplate"/> (or a custom
    /// <see cref="BackgroundTaskCompletionLoopEvaluatorOptions.FeedbackMessageTemplate"/>) that is replaced, on each
    /// evaluation, with the number of background tasks that are still running.
    /// </summary>
    public const string IncompleteTaskCountPlaceholder = "{incomplete_task_count}";

    /// <summary>The default template used to build the feedback produced while background tasks are still running.</summary>
    public const string DefaultFeedbackMessageTemplate =
        "You still have " + IncompleteTaskCountPlaceholder + " background task(s) running that must finish before you " +
        "can complete the work:\n" + IncompleteTasksPlaceholder + "\n\n" +
        "Wait for these tasks to complete, retrieve their results, and incorporate them. Only stop once every " +
        "background task has finished.";

    private readonly string _feedbackMessageTemplate;

    /// <summary>
    /// Initializes a new instance of the <see cref="BackgroundTaskCompletionLoopEvaluator"/> class.
    /// </summary>
    /// <param name="options">
    /// Optional configuration for the evaluator, including the feedback message template. When <see langword="null"/>,
    /// defaults are used.
    /// </param>
    public BackgroundTaskCompletionLoopEvaluator(BackgroundTaskCompletionLoopEvaluatorOptions? options = null)
    {
        this._feedbackMessageTemplate = options?.FeedbackMessageTemplate ?? DefaultFeedbackMessageTemplate;
    }

    /// <inheritdoc />
    public override ValueTask<LoopEvaluation> EvaluateAsync(LoopContext context, CancellationToken cancellationToken = default)
    {
        _ = Throw.IfNull(context);

        BackgroundAgentsProvider provider = context.Agent.GetService<BackgroundAgentsProvider>()
            ?? throw new InvalidOperationException(
                $"{nameof(BackgroundTaskCompletionLoopEvaluator)} requires a {nameof(BackgroundAgentsProvider)} to be registered on the agent, but none could be resolved via GetService.");

        IReadOnlyList<BackgroundTaskInfo> incomplete = provider.GetIncompleteTasks(context.Session);
        if (incomplete.Count == 0)
        {
            return new ValueTask<LoopEvaluation>(LoopEvaluation.Stop());
        }

        string feedback = this._feedbackMessageTemplate
            .Replace(IncompleteTaskCountPlaceholder, incomplete.Count.ToString(CultureInfo.InvariantCulture))
            .Replace(IncompleteTasksPlaceholder, FormatIncompleteTasks(incomplete));
        return new ValueTask<LoopEvaluation>(LoopEvaluation.Continue(feedback));
    }

    private static string FormatIncompleteTasks(IReadOnlyList<BackgroundTaskInfo> incomplete)
    {
        var sb = new StringBuilder();
        for (int i = 0; i < incomplete.Count; i++)
        {
            BackgroundTaskInfo task = incomplete[i];
            sb.Append("- #").Append(task.Id).Append(" (").Append(task.AgentName).Append("): ").Append(task.Description);

            if (i < incomplete.Count - 1)
            {
                sb.Append('\n');
            }
        }

        return sb.ToString();
    }
}
