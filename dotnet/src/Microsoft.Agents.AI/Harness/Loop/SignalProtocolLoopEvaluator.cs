// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Diagnostics.CodeAnalysis;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Shared.DiagnosticIds;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI;

/// <summary>
/// A <see cref="LoopEvaluator"/> implementing the GT1 signal protocol: the loop stops when the agent's latest response
/// contains <see cref="TaskCompleteToken"/> or <see cref="NeedInputToken"/>, and otherwise continues with feedback
/// reminding the agent to emit one of the signals.
/// </summary>
/// <remarks>
/// <see cref="TaskCompleteToken"/> takes priority over <see cref="NeedInputToken"/>. When a signal is detected, the
/// matching <see cref="LoopExitReason"/> is stamped into <see cref="LoopContext.AdditionalProperties"/> under
/// <see cref="LoopExitReason.AdditionalPropertiesKey"/>.
/// </remarks>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public sealed class SignalProtocolLoopEvaluator : LoopEvaluator
{
    /// <summary>The token signalling that the task is complete.</summary>
    public const string TaskCompleteToken = "TASK_COMPLETE:";

    /// <summary>The token signalling that the agent needs input from the user.</summary>
    public const string NeedInputToken = "NEED_INPUT:";

    /// <summary>The default feedback produced while neither signal is present.</summary>
    public const string DefaultFeedbackMessage =
        "Continue working on the task. When done, emit '" + TaskCompleteToken + " <summary>'. " +
        "If you need input, emit '" + NeedInputToken + " <question>'.";

    private readonly string _feedbackMessage;

    /// <summary>
    /// Initializes a new instance of the <see cref="SignalProtocolLoopEvaluator"/> class.
    /// </summary>
    /// <param name="feedbackMessage">Optional custom feedback used when no signal is present. When <see langword="null"/>, <see cref="DefaultFeedbackMessage"/> is used.</param>
    public SignalProtocolLoopEvaluator(string? feedbackMessage = null)
    {
        this._feedbackMessage = feedbackMessage ?? DefaultFeedbackMessage;
    }

    /// <inheritdoc />
    public override ValueTask<LoopEvaluation> EvaluateAsync(LoopContext context, CancellationToken cancellationToken = default)
    {
        _ = Throw.IfNull(context);

        string text = context.LastResponse.Text;

        if (text.Contains(TaskCompleteToken, StringComparison.Ordinal))
        {
            context.AdditionalProperties[LoopExitReason.AdditionalPropertiesKey] = LoopExitReason.Completed;
            return new ValueTask<LoopEvaluation>(LoopEvaluation.Stop());
        }

        if (text.Contains(NeedInputToken, StringComparison.Ordinal))
        {
            context.AdditionalProperties[LoopExitReason.AdditionalPropertiesKey] = LoopExitReason.NeedInput;
            return new ValueTask<LoopEvaluation>(LoopEvaluation.Stop());
        }

        return new ValueTask<LoopEvaluation>(LoopEvaluation.Continue(this._feedbackMessage));
    }
}
