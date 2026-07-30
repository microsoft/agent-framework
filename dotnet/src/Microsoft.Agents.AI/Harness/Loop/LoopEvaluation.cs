// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using System.Linq;
using Microsoft.Extensions.AI;
using Microsoft.Shared.DiagnosticIds;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI;

/// <summary>
/// Represents the result produced by a <see cref="LoopEvaluator"/> after an agent iteration: whether the
/// <see cref="LoopAgent"/> should re-invoke the wrapped agent and, optionally, the feedback or explicit messages that
/// should inform the next iteration.
/// </summary>
/// <remarks>
/// An evaluator is concerned only with the judgment (continue or stop) and what to carry forward. In the common case
/// it returns a feedback string and lets the <see cref="LoopAgent"/> decide how that feedback is turned into the next
/// input (and whether the session is reset). For full control, <see cref="ContinueWithMessages"/> supplies the exact
/// messages to send next, bypassing the loop's feedback and message construction.
/// </remarks>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public sealed class LoopEvaluation
{
    private static readonly LoopEvaluation s_stop = new(shouldReinvoke: false, feedback: null, messages: null);

    private LoopEvaluation(bool shouldReinvoke, string? feedback, IReadOnlyList<ChatMessage>? messages)
    {
        this.ShouldReinvoke = shouldReinvoke;
        this.Feedback = feedback;
        this.Messages = messages;
    }

    /// <summary>Gets a value indicating whether the loop should run the wrapped agent again.</summary>
    public bool ShouldReinvoke { get; }

    /// <summary>
    /// Gets the feedback describing what is missing or what the agent should do next, or <see langword="null"/> when
    /// no feedback was produced.
    /// </summary>
    /// <remarks>This value is only meaningful when <see cref="ShouldReinvoke"/> is <see langword="true"/>.</remarks>
    public string? Feedback { get; }

    /// <summary>
    /// Gets the explicit messages to send on the next iteration, or <see langword="null"/> when the loop should build
    /// the next input from feedback instead.
    /// </summary>
    /// <remarks>
    /// When non-<see langword="null"/>, the <see cref="LoopAgent"/> sends these messages verbatim and does not apply
    /// its feedback or message construction. The session is still reset when
    /// <see cref="LoopAgentOptions.FreshContextPerIteration"/> is enabled. Only meaningful when
    /// <see cref="ShouldReinvoke"/> is <see langword="true"/>.
    /// </remarks>
    internal IReadOnlyList<ChatMessage>? Messages { get; }

    /// <summary>Creates an evaluation that stops the loop and returns the latest response to the caller.</summary>
    /// <returns>An evaluation with <see cref="ShouldReinvoke"/> set to <see langword="false"/>.</returns>
    public static LoopEvaluation Stop() => s_stop;

    /// <summary>Creates an evaluation that re-invokes the wrapped agent, optionally carrying feedback forward.</summary>
    /// <param name="feedback">
    /// Optional feedback to inform the next iteration. <see langword="null"/>, empty, or whitespace is treated as no
    /// feedback.
    /// </param>
    /// <returns>An evaluation with <see cref="ShouldReinvoke"/> set to <see langword="true"/>.</returns>
    public static LoopEvaluation Continue(string? feedback = null) => new(shouldReinvoke: true, string.IsNullOrWhiteSpace(feedback) ? null : feedback, messages: null);

    /// <summary>
    /// Creates an evaluation that re-invokes the wrapped agent with the specified messages, bypassing the loop's
    /// feedback and message construction.
    /// </summary>
    /// <param name="messages">The messages to send to the wrapped agent on the next iteration.</param>
    /// <returns>An evaluation with <see cref="ShouldReinvoke"/> set to <see langword="true"/>.</returns>
    /// <exception cref="System.ArgumentNullException"><paramref name="messages"/> is <see langword="null"/>.</exception>
    /// <remarks>
    /// Use this for full control over the next input (for example to send non-user roles, multiple messages, or
    /// non-text content). The supplied messages are sent verbatim and the loop does not accumulate or inject feedback
    /// for this iteration.
    /// </remarks>
    public static LoopEvaluation ContinueWithMessages(IEnumerable<ChatMessage> messages)
    {
        _ = Throw.IfNull(messages);
        return new LoopEvaluation(shouldReinvoke: true, feedback: null, messages: messages as IReadOnlyList<ChatMessage> ?? messages.ToList());
    }
}
