// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Shared.DiagnosticIds;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI;

/// <summary>
/// A <see cref="LoopEvaluator"/> that keeps re-invoking the wrapped agent until a <see cref="TodoProvider"/> has no
/// remaining (incomplete) todo items, optionally only while the agent is operating in one of a configured set of modes
/// tracked by an <see cref="AgentModeProvider"/>.
/// </summary>
/// <remarks>
/// <para>
/// The required <see cref="TodoProvider"/> — and, when modes are configured, the <see cref="AgentModeProvider"/> — are
/// not supplied directly. They are resolved at evaluation time from the looped agent via
/// <see cref="AIAgent.GetService{TService}(object?)"/>. This works because an agent surfaces its registered
/// <see cref="AIContextProvider"/> instances through <c>GetService</c>, so a single <see cref="TodoProvider"/> (and
/// <see cref="AgentModeProvider"/>) attached to the agent's session is discovered automatically. It also means this
/// evaluator can be added directly to a harness agent's loop without any additional wiring.
/// </para>
/// <para>
/// When one or more modes are configured, the evaluator only requests re-invocation while the session's current mode is
/// one of those modes; in any other mode it returns <see cref="LoopEvaluation.Stop"/> (which, per <see cref="LoopAgent"/>
/// semantics, declines to drive continuation rather than vetoing other evaluators). When no modes are configured the
/// evaluator applies in every mode and no <see cref="AgentModeProvider"/> is required.
/// </para>
/// <para>
/// While incomplete todos remain the evaluator continues with feedback built from a template (see
/// <see cref="TodoCompletionLoopEvaluatorOptions.FeedbackMessageTemplate"/>) with the remaining todo list substituted
/// for <see cref="RemainingTodosPlaceholder"/>. How that feedback is delivered to the agent (and whether the session is
/// reset) is decided by the <see cref="LoopAgent"/> that consumes this evaluator.
/// </para>
/// </remarks>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public sealed class TodoCompletionLoopEvaluator : LoopEvaluator
{
    /// <summary>
    /// The placeholder token within <see cref="DefaultFeedbackMessageTemplate"/> (or a custom
    /// <see cref="TodoCompletionLoopEvaluatorOptions.FeedbackMessageTemplate"/>) that is replaced, on each evaluation,
    /// with a formatted list of the remaining (incomplete) todo items.
    /// </summary>
    public const string RemainingTodosPlaceholder = "{remaining_todos}";

    /// <summary>The default template used to build the feedback produced while incomplete todo items remain.</summary>
    public const string DefaultFeedbackMessageTemplate =
        "You still have incomplete todo items. Continue working until every item is complete, marking each item as " +
        "complete when finished. The following items are still open:\n" + RemainingTodosPlaceholder;

    private readonly HashSet<string>? _modes;
    private readonly string _feedbackMessageTemplate;

    /// <summary>
    /// Initializes a new instance of the <see cref="TodoCompletionLoopEvaluator"/> class.
    /// </summary>
    /// <param name="options">
    /// Optional configuration for the evaluator, including <see cref="TodoCompletionLoopEvaluatorOptions.Modes"/> and
    /// the feedback message template. When <see langword="null"/>, defaults are used (applies in every mode).
    /// </param>
    /// <exception cref="ArgumentException">
    /// <see cref="TodoCompletionLoopEvaluatorOptions.Modes"/> is non-<see langword="null"/> but empty, or contains a
    /// <see langword="null"/>, empty, or whitespace mode name.
    /// </exception>
    public TodoCompletionLoopEvaluator(TodoCompletionLoopEvaluatorOptions? options = null)
    {
        if (options?.Modes is not null)
        {
            var modeSet = new HashSet<string>(StringComparer.Ordinal);
            foreach (string mode in options.Modes)
            {
                if (string.IsNullOrWhiteSpace(mode))
                {
                    throw new ArgumentException("Mode names must not be null, empty, or whitespace.", nameof(options));
                }

                modeSet.Add(mode);
            }

            if (modeSet.Count == 0)
            {
                throw new ArgumentException("At least one mode must be supplied when modes are specified. Leave Modes null to apply in every mode.", nameof(options));
            }

            this._modes = modeSet;
        }

        this._feedbackMessageTemplate = options?.FeedbackMessageTemplate ?? DefaultFeedbackMessageTemplate;
    }

    /// <inheritdoc />
    public override async ValueTask<LoopEvaluation> EvaluateAsync(LoopContext context, CancellationToken cancellationToken = default)
    {
        _ = Throw.IfNull(context);

        TodoProvider todoProvider = context.Agent.GetService<TodoProvider>()
            ?? throw new InvalidOperationException(
                $"{nameof(TodoCompletionLoopEvaluator)} requires a {nameof(TodoProvider)} to be registered on the agent, but none could be resolved via GetService.");

        // When modes are configured, only drive re-invocation while the current mode is one of them.
        if (this._modes is not null)
        {
            AgentModeProvider modeProvider = context.Agent.GetService<AgentModeProvider>()
                ?? throw new InvalidOperationException(
                    $"{nameof(TodoCompletionLoopEvaluator)} was configured with modes but no {nameof(AgentModeProvider)} could be resolved from the agent via GetService.");

            string currentMode = modeProvider.GetMode(context.Session);
            if (!this._modes.Contains(currentMode))
            {
                return LoopEvaluation.Stop();
            }
        }

        List<TodoItem> remaining = await todoProvider.GetRemainingTodosAsync(context.Session, cancellationToken).ConfigureAwait(false);
        if (remaining.Count == 0)
        {
            return LoopEvaluation.Stop();
        }

        string feedback = this._feedbackMessageTemplate.Replace(RemainingTodosPlaceholder, FormatRemainingTodos(remaining));
        return LoopEvaluation.Continue(feedback);
    }

    private static string FormatRemainingTodos(List<TodoItem> remaining)
    {
        var sb = new StringBuilder();
        for (int i = 0; i < remaining.Count; i++)
        {
            TodoItem item = remaining[i];
            sb.Append("- ").Append(item.Id).Append(": ").Append(item.Title);
            if (!string.IsNullOrWhiteSpace(item.Description))
            {
                sb.Append(" — ").Append(item.Description);
            }

            if (i < remaining.Count - 1)
            {
                sb.Append('\n');
            }
        }

        return sb.ToString();
    }
}
