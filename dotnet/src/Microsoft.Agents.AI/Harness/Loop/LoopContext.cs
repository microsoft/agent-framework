// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using Microsoft.Extensions.AI;
using Microsoft.Shared.DiagnosticIds;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI;

/// <summary>
/// Provides the per-run state that a <see cref="LoopEvaluator"/> uses to decide whether a
/// <see cref="LoopAgent"/> should re-invoke the wrapped agent and what feedback to provide.
/// </summary>
/// <remarks>
/// A single <see cref="LoopContext"/> instance is created for each <see cref="LoopAgent"/> run and is
/// reused across iterations, with <see cref="Iteration"/> and <see cref="LastResponse"/> updated before
/// each call to <see cref="LoopEvaluator.EvaluateAsync"/>. Because evaluator instances are expected to be
/// stateless and may be shared across concurrent runs, any per-run mutable state must be stored on this
/// context — for example via <see cref="AdditionalProperties"/> — rather than in fields on the evaluator itself.
/// </remarks>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public sealed class LoopContext
{
    /// <summary>
    /// Initializes a new instance of the <see cref="LoopContext"/> class.
    /// </summary>
    /// <param name="agent">The wrapped <see cref="AIAgent"/> that is being looped.</param>
    /// <param name="session">The <see cref="AgentSession"/> used for the loop.</param>
    /// <param name="initialMessages">The messages passed in for the first iteration of the loop.</param>
    /// <param name="lastResponse">The <see cref="AgentResponse"/> produced by the iteration that just completed.</param>
    /// <param name="runOptions">The <see cref="AgentRunOptions"/> that were passed to the loop run, if any.</param>
    /// <exception cref="System.ArgumentNullException">
    /// <paramref name="agent"/>, <paramref name="session"/>, <paramref name="initialMessages"/>, or
    /// <paramref name="lastResponse"/> is <see langword="null"/>.
    /// </exception>
    public LoopContext(
        AIAgent agent,
        AgentSession session,
        IReadOnlyList<ChatMessage> initialMessages,
        AgentResponse lastResponse,
        AgentRunOptions? runOptions = null)
    {
        this.Agent = Throw.IfNull(agent);
        this.Session = Throw.IfNull(session);
        this.InitialMessages = Throw.IfNull(initialMessages);
        this.LastResponse = Throw.IfNull(lastResponse);
        this.RunOptions = runOptions;
    }

    /// <summary>Gets the wrapped <see cref="AIAgent"/> that is being looped.</summary>
    public AIAgent Agent { get; }

    /// <summary>Gets the <see cref="AgentSession"/> used for the loop.</summary>
    /// <remarks>
    /// When the caller does not provide a session, <see cref="LoopAgent"/> creates one up front. By default the same
    /// session is reused across every iteration so that conversation continuity is preserved and the original request
    /// is not replayed. When <see cref="LoopAgentOptions.FreshContextPerIteration"/> is enabled, <see cref="LoopAgent"/>
    /// resets the session before each re-invocation: a loop-owned session is created anew, while a caller-supplied
    /// session is restored from a snapshot taken at the start of the run by deserializing a fresh clone.
    /// </remarks>
    public AgentSession Session { get; internal set; }

    /// <summary>Gets the messages that were passed in for the first iteration of the loop.</summary>
    public IReadOnlyList<ChatMessage> InitialMessages { get; }

    /// <summary>Gets the <see cref="AgentRunOptions"/> that were passed to the loop run, if any.</summary>
    public AgentRunOptions? RunOptions { get; }

    /// <summary>Gets the number of completed agent runs so far (1-based after the first run).</summary>
    public int Iteration { get; internal set; }

    /// <summary>Gets the <see cref="AgentResponse"/> produced by the iteration that just completed.</summary>
    public AgentResponse LastResponse { get; internal set; }

    /// <summary>
    /// Gets the feedback accumulated across iterations so far, one entry per re-invoked iteration in order.
    /// </summary>
    /// <remarks>
    /// Each entry is the feedback supplied by the evaluator that requested the corresponding re-invocation, or
    /// <see langword="null"/> when that iteration produced no feedback string (for example a plain
    /// <see cref="LoopEvaluation.Continue(string)"/> with no text, or a <see cref="LoopEvaluation.ContinueWithMessages"/>
    /// that supplied explicit messages instead). The log records one entry per re-invoked iteration regardless of mode,
    /// so the last entry always corresponds to the most recent re-invoked iteration. This log is owned and populated by
    /// <see cref="LoopAgent"/>; evaluators may read it to reason over prior feedback.
    /// </remarks>
    public IReadOnlyList<string?> Feedback { get; internal set; } = [];

    /// <summary>
    /// Gets a mutable bag of per-run state shared across iterations and available to every evaluator.
    /// </summary>
    /// <remarks>
    /// This dictionary is owned by the loop run (not by any evaluator instance) so that evaluators can remain
    /// stateless. Evaluators can stash arbitrary per-run state here keyed by a collision-resistant key.
    /// </remarks>
    public AdditionalPropertiesDictionary AdditionalProperties { get; } = new();
}
