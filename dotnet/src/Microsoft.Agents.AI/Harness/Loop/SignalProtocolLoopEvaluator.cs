// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Diagnostics.CodeAnalysis;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Shared.DiagnosticIds;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI;

/// <summary>
/// A <see cref="LoopEvaluator"/> implementing the GT1 signal protocol: the loop stops when an assistant message in the
/// agent's latest response contains <see cref="TaskCompleteToken"/> or <see cref="NeedInputToken"/> at the start of a
/// line, and otherwise continues with feedback reminding the agent to emit one of the signals.
/// </summary>
/// <remarks>
/// <para>
/// A token only counts when it starts its own line: it must appear at the start of the message or right after a line
/// break, optionally preceded by spaces or tabs. Mentions anywhere else on a line (for example
/// "I'll emit <c>TASK_COMPLETE:</c> when done", or a token quoted in backticks) are ignored, so the agent can talk about
/// the protocol without accidentally ending the loop.
/// </para>
/// <para>
/// <see cref="TaskCompleteToken"/> takes priority over <see cref="NeedInputToken"/>. When a signal is detected, the
/// matching <see cref="LoopExitReason"/> is stamped into <see cref="LoopContext.AdditionalProperties"/> under
/// <see cref="LoopExitReason.AdditionalPropertiesKey"/>.
/// </para>
/// </remarks>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public sealed class SignalProtocolLoopEvaluator : LoopEvaluator
{
    /// <summary>The token signalling that the task is complete. Only recognized at the start of a line.</summary>
    public const string TaskCompleteToken = "TASK_COMPLETE:";

    /// <summary>The token signalling that the agent needs input from the user. Only recognized at the start of a line.</summary>
    public const string NeedInputToken = "NEED_INPUT:";

    /// <summary>The default feedback produced while neither signal is present.</summary>
    public const string DefaultFeedbackMessage =
        "Continue working on the task. When done, start a new line with '" + TaskCompleteToken + " <summary>'. " +
        "If you need input, start a new line with '" + NeedInputToken + " <question>'.";

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

        if (AssistantMessageHasSignal(context, TaskCompleteToken))
        {
            context.AdditionalProperties[LoopExitReason.AdditionalPropertiesKey] = LoopExitReason.Completed;
            return new ValueTask<LoopEvaluation>(LoopEvaluation.Stop());
        }

        if (AssistantMessageHasSignal(context, NeedInputToken))
        {
            context.AdditionalProperties[LoopExitReason.AdditionalPropertiesKey] = LoopExitReason.NeedInput;
            return new ValueTask<LoopEvaluation>(LoopEvaluation.Stop());
        }

        return new ValueTask<LoopEvaluation>(LoopEvaluation.Continue(this._feedbackMessage));
    }

    /// <summary>
    /// Determines whether any assistant-role message in the latest response contains <paramref name="token"/> at the
    /// start of a line. Messages are matched individually so a token cannot be formed across message boundaries, and
    /// non-assistant messages (for example tool results or echoed user input) never trigger a signal.
    /// </summary>
    private static bool AssistantMessageHasSignal(LoopContext context, string token)
    {
        foreach (ChatMessage message in context.LastResponse.Messages)
        {
            if (message.Role == ChatRole.Assistant && ContainsTokenAtLineStart(message.Text, token))
            {
                return true;
            }
        }

        return false;
    }

    /// <summary>
    /// Determines whether <paramref name="text"/> contains <paramref name="token"/> at the start of a line, allowing only
    /// spaces and tabs between the preceding line break (or the start of the text) and the token.
    /// </summary>
    private static bool ContainsTokenAtLineStart(string text, string token)
    {
        int index = text.IndexOf(token, StringComparison.Ordinal);
        while (index >= 0)
        {
            int i = index - 1;
            while (i >= 0 && (text[i] == ' ' || text[i] == '\t'))
            {
                i--;
            }

            // Checking for '\n' covers both "\n" and "\r\n" line endings.
            if (i < 0 || text[i] == '\n')
            {
                return true;
            }

            index = text.IndexOf(token, index + token.Length, StringComparison.Ordinal);
        }

        return false;
    }
}
