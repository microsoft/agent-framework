// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Diagnostics.CodeAnalysis;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Shared.DiagnosticIds;

namespace Microsoft.Agents.AI;

/// <summary>
/// Provides configuration options for <see cref="LoopAgent"/>.
/// </summary>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public sealed class LoopAgentOptions
{
    /// <summary>
    /// Gets or sets the global safety cap on the number of times the wrapped agent is invoked in a single loop run,
    /// or <see langword="null"/> to use <see cref="LoopAgent.DefaultMaxIterations"/>.
    /// </summary>
    /// <remarks>
    /// This is an absolute upper bound that applies regardless of the configured <see cref="LoopEvaluator"/> set. An
    /// evaluator may stop the loop earlier, but no evaluator can cause the loop to exceed this cap, so raise this value
    /// if you intend to allow longer loops.
    /// </remarks>
    public int? MaxIterations { get; set; }

    /// <summary>
    /// Gets or sets a value indicating whether each re-invocation restarts from a clean context: the original input
    /// messages plus an aggregated feedback log, rather than the latest feedback appended to the prior conversation.
    /// Defaults to <see langword="false"/>.
    /// </summary>
    /// <remarks>
    /// <para>
    /// This rebuilds the input <em>messages</em> each iteration and resets the session before each re-invocation so no
    /// prior conversation history leaks across iterations. When the loop owns the session it creates a new one each
    /// iteration. When the caller supplies a session, <see cref="LoopAgent"/> serializes it once at the start of the run
    /// and restores a fresh clone (by deserializing that snapshot) before each re-invocation; this requires the wrapped
    /// agent to support session serialization. The first iteration still runs against the caller's supplied session.
    /// </para>
    /// <para>
    /// Note that cloning will only result in a fresh context, if the chat history storage mechanism supports cloning.
    /// For example the default in-memory storage supports cloning, since the messages are serialized as part of the snapshot.
    /// </para>
    /// <para>
    /// However, if the Conversations service is used, which stores messages in a single threaded list of messages,
    /// then the cloned session will still contain the full message history, since the snapshot only captures an id reference
    /// to the conversation and not the individual messages.
    /// </para>
    /// <para>
    /// On the other hand, if responses are used with response ids, cloning will work well, since response ids are
    /// forkable. Each new response has its own id, and is based on the id of the previous response.
    /// </para>
    /// <para>
    /// On iterations where an evaluator returns explicit messages via
    /// <see cref="LoopEvaluation.ContinueWithMessages"/>, the session is still reset (a fresh or cloned session is
    /// used); only the rebuild of the input messages from the feedback log is skipped, because the evaluator's explicit
    /// messages are sent verbatim.
    /// </para>
    /// </remarks>
    public bool FreshContextPerIteration { get; set; }

    /// <summary>
    /// Gets or sets the author name stamped on the loop-synthesized "on-behalf-of" messages that the loop injects
    /// into the wrapped agent for re-invocations, or <see langword="null"/> to leave them unattributed. Defaults to
    /// <see langword="null"/>.
    /// </summary>
    /// <remarks>
    /// When the loop re-invokes the wrapped agent it sends feedback messages on the caller's behalf. Setting this name
    /// marks those autonomous messages (for example with a value such as <c>"loop"</c>) so that callers and the wrapped
    /// agent can distinguish them from the caller's own turns. It is applied only to messages the loop synthesizes
    /// itself; messages supplied explicitly by an evaluator via <see cref="LoopEvaluation.ContinueWithMessages"/> are
    /// left untouched, and the caller's original input messages are never modified.
    /// </remarks>
    public string? OnBehalfOfAuthorName { get; set; }

    /// <summary>
    /// Gets or sets a value indicating whether the on-behalf-of messages the loop injects for re-invocations are
    /// omitted from the output surfaced back to the caller. Defaults to <see langword="false"/>.
    /// </summary>
    /// <remarks>
    /// When <see langword="false"/> (the default) a streaming run emits the injected feedback / evaluator-supplied
    /// messages as updates before each re-invocation, and a non-streaming run includes them in the aggregated
    /// transcript, so callers can see the loop acting autonomously on their behalf. Set this to <see langword="true"/>
    /// to omit those messages from the returned output and surface only the wrapped agent's responses; the messages are
    /// still sent to the wrapped agent. This setting has no effect when
    /// <see cref="NonStreamingReturnsLastResponseOnly"/> causes a non-streaming run to return only the final response.
    /// </remarks>
    public bool ExcludeOnBehalfOfMessages { get; set; }

    /// <summary>
    /// Gets or sets a value indicating whether a non-streaming run returns only the final iteration's response instead
    /// of the aggregated transcript of every iteration. Defaults to <see langword="false"/>.
    /// </summary>
    /// <remarks>
    /// By default a non-streaming <see cref="LoopAgent"/> run returns a single <see cref="AgentResponse"/> that
    /// aggregates, in order, the on-behalf-of messages the loop injected and the responses produced by every
    /// iteration — mirroring the full sequence of updates yielded by a streaming run. Set this to <see langword="true"/>
    /// to instead return only the last iteration's <see cref="AgentResponse"/>. This setting affects non-streaming runs
    /// only; streaming runs always yield every iteration's updates.
    /// </remarks>
    public bool NonStreamingReturnsLastResponseOnly { get; set; }

    /// <summary>
    /// Gets or sets an optional callback invoked whenever <see cref="LoopAgent"/> creates a new session, so the caller
    /// can capture the latest session (for example to continue the conversation after the loop completes). Defaults to
    /// <see langword="null"/>.
    /// </summary>
    /// <remarks>
    /// The callback is invoked with each session the loop itself creates: the initial loop-owned session (when the
    /// caller does not supply one) and, when <see cref="FreshContextPerIteration"/> is enabled, every session created
    /// for a re-invocation — whether a brand-new loop-owned session or a fresh clone deserialized from the caller's
    /// original session. It is not invoked for a caller-supplied session, since the caller already holds that one. When
    /// it fires multiple times, the most recent invocation carries the session the loop is currently using.
    /// </remarks>
    public Func<AgentSession, CancellationToken, ValueTask>? SessionCreatedCallback { get; set; }
}
