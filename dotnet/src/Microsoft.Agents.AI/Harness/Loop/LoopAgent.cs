// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using System.Linq;
using System.Runtime.CompilerServices;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Logging.Abstractions;
using Microsoft.Shared.DiagnosticIds;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI;

/// <summary>
/// A <see cref="DelegatingAIAgent"/> that re-invokes the wrapped agent in a loop until the configured
/// <see cref="LoopEvaluator"/> set decides to stop.
/// </summary>
/// <remarks>
/// <para>
/// After each run of the wrapped agent, the configured evaluators are asked whether to re-invoke the agent and what
/// feedback to carry forward. This enables patterns such as iterative refinement, working through a task list, or
/// judging whether the original request was answered. Out-of-the-box evaluators include
/// <see cref="AIJudgeLoopEvaluator"/>, <see cref="CompletionMarkerLoopEvaluator"/>, and
/// <see cref="DelegateLoopEvaluator"/>.
/// </para>
/// <para>
/// When multiple evaluators are supplied they are evaluated in order after each iteration. The first evaluator that
/// asks to re-invoke wins: its feedback drives the next iteration and the remaining evaluators are not evaluated. The
/// loop stops only when every evaluator asks to stop. Consequently, evaluator order is priority order and
/// <see cref="LoopEvaluation.Stop"/> means "this evaluator does not request continuation" rather than a veto that
/// terminates the loop; place stop-only guards accordingly.
/// </para>
/// <para>
/// The caller's initial messages are sent to the wrapped agent exactly once. By default (when
/// <see cref="LoopAgentOptions.FreshContextPerIteration"/> is <see langword="false"/>) the loop reuses a single session
/// and sends only the winning evaluator's feedback as the next input, letting the agent continue from session history.
/// When <see cref="LoopAgentOptions.FreshContextPerIteration"/> is <see langword="true"/>, each re-invocation restarts
/// from the original input messages plus an aggregated feedback log, and the session is reset for each iteration: a
/// loop-owned session is created anew, while a caller-supplied session is restored from a snapshot taken at the start
/// of the run (so the wrapped agent must support session serialization). An evaluator may instead supply the exact next
/// messages via <see cref="LoopEvaluation.ContinueWithMessages"/>, bypassing this construction.
/// </para>
/// <para>
/// The loop is bounded by a global safety cap (<see cref="LoopAgentOptions.MaxIterations"/>) regardless of the
/// evaluators. If an iteration produces a pending tool-approval request, the loop stops and returns that response to
/// the caller rather than attempting to resolve the approval automatically.
/// </para>
/// <para>
/// A non-streaming run returns, by default, a single <see cref="AgentResponse"/> that aggregates the full transcript
/// in order: the on-behalf-of messages the loop injected for each re-invocation followed by that iteration's response
/// messages. The caller's original input messages are not echoed. Set
/// <see cref="LoopAgentOptions.NonStreamingReturnsLastResponseOnly"/> to instead return only the final iteration's
/// response. A streaming run always yields every iteration's updates, emitting the injected on-behalf-of messages as
/// updates before each re-invocation. The injected messages can be attributed with
/// <see cref="LoopAgentOptions.OnBehalfOfAuthorName"/>, or omitted from the surfaced output entirely with
/// <see cref="LoopAgentOptions.ExcludeOnBehalfOfMessages"/>.
/// </para>
/// </remarks>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public sealed class LoopAgent : DelegatingAIAgent
{
    /// <summary>The default value used for <see cref="LoopAgentOptions.MaxIterations"/> when none is specified.</summary>
    public const int DefaultMaxIterations = 10;

    private readonly IReadOnlyList<LoopEvaluator> _evaluators;
    private readonly int _maxIterations;
    private readonly bool _freshContextPerIteration;
    private readonly string? _onBehalfOfAuthorName;
    private readonly bool _excludeOnBehalfOfMessages;
    private readonly bool _nonStreamingReturnsLastResponseOnly;
    private readonly System.Func<AgentSession, CancellationToken, ValueTask>? _sessionCreatedCallback;
    private readonly ILogger _logger;

    /// <summary>
    /// Initializes a new instance of the <see cref="LoopAgent"/> class with a single evaluator.
    /// </summary>
    /// <param name="innerAgent">The underlying agent to invoke in a loop.</param>
    /// <param name="evaluator">The <see cref="LoopEvaluator"/> that decides whether to re-invoke the agent.</param>
    /// <param name="options">Optional configuration for the loop. When <see langword="null"/>, defaults are used.</param>
    /// <param name="loggerFactory">Optional factory used to create the loop's logger.</param>
    /// <exception cref="System.ArgumentNullException"><paramref name="innerAgent"/> or <paramref name="evaluator"/> is <see langword="null"/>.</exception>
    /// <exception cref="System.ArgumentOutOfRangeException"><see cref="LoopAgentOptions.MaxIterations"/> is less than 1.</exception>
    public LoopAgent(AIAgent innerAgent, LoopEvaluator evaluator, LoopAgentOptions? options = null, ILoggerFactory? loggerFactory = null)
        : this(innerAgent, [Throw.IfNull(evaluator)], options, loggerFactory)
    {
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="LoopAgent"/> class with one or more evaluators.
    /// </summary>
    /// <param name="innerAgent">The underlying agent to invoke in a loop.</param>
    /// <param name="evaluators">
    /// The ordered collection of <see cref="LoopEvaluator"/> that decide whether to re-invoke the agent. They are evaluated in
    /// order after each iteration and the first that asks to re-invoke wins.
    /// </param>
    /// <param name="options">Optional configuration for the loop. When <see langword="null"/>, defaults are used.</param>
    /// <param name="loggerFactory">Optional factory used to create the loop's logger.</param>
    /// <exception cref="System.ArgumentNullException"><paramref name="innerAgent"/> or <paramref name="evaluators"/> is <see langword="null"/>, or <paramref name="evaluators"/> contains a <see langword="null"/> element.</exception>
    /// <exception cref="System.ArgumentException"><paramref name="evaluators"/> is empty.</exception>
    /// <exception cref="System.ArgumentOutOfRangeException"><see cref="LoopAgentOptions.MaxIterations"/> is less than 1.</exception>
    public LoopAgent(AIAgent innerAgent, IEnumerable<LoopEvaluator> evaluators, LoopAgentOptions? options = null, ILoggerFactory? loggerFactory = null)
        : base(innerAgent)
    {
        _ = Throw.IfNull(evaluators);
        LoopEvaluator[] evaluatorArray = evaluators.ToArray();
        if (evaluatorArray.Length == 0)
        {
            throw new System.ArgumentException("At least one evaluator must be supplied.", nameof(evaluators));
        }

        foreach (LoopEvaluator item in evaluatorArray)
        {
            _ = Throw.IfNull(item, nameof(evaluators));
        }

        this._evaluators = evaluatorArray;

        this._maxIterations = Throw.IfLessThan(options?.MaxIterations ?? DefaultMaxIterations, 1);
        this._freshContextPerIteration = options?.FreshContextPerIteration ?? false;
        this._onBehalfOfAuthorName = options?.OnBehalfOfAuthorName;
        this._excludeOnBehalfOfMessages = options?.ExcludeOnBehalfOfMessages ?? false;
        this._nonStreamingReturnsLastResponseOnly = options?.NonStreamingReturnsLastResponseOnly ?? false;
        this._sessionCreatedCallback = options?.SessionCreatedCallback;
        this._logger = (loggerFactory ?? NullLoggerFactory.Instance).CreateLogger<LoopAgent>();
    }

    /// <inheritdoc />
    protected override async Task<AgentResponse> RunCoreAsync(
        IEnumerable<ChatMessage> messages,
        AgentSession? session = null,
        AgentRunOptions? options = null,
        CancellationToken cancellationToken = default)
    {
        _ = Throw.IfNull(messages);

        // Capture the caller's initial messages (sent once) and ensure the loop always runs against a session.
        IReadOnlyList<ChatMessage> initialMessages = messages as IReadOnlyList<ChatMessage> ?? messages.ToList();
        bool sessionProvidedByCaller = session is not null;
        if (session is null)
        {
            session = await this.InnerAgent.CreateSessionAsync(cancellationToken).ConfigureAwait(false);
            await this.NotifyNewSessionAsync(session, cancellationToken).ConfigureAwait(false);
        }

        // When a fresh context is requested over a caller-supplied session, snapshot the pristine session up front so
        // each re-invocation can restart from a fresh clone (see CreateFreshIterationSessionAsync). Taken before the
        // first iteration mutates the session.
        JsonElement? initialSessionSnapshot = this._freshContextPerIteration && sessionProvidedByCaller
            ? await this.InnerAgent.SerializeSessionAsync(session, cancellationToken: cancellationToken).ConfigureAwait(false)
            : null;

        LoopContext? context = null;
        List<string?> feedbackLog = [];
        IEnumerable<ChatMessage> currentMessages = initialMessages;
        int iteration = 0;

        // Aggregates the full transcript across iterations: each iteration's surfaced on-behalf-of input messages
        // followed by that iteration's response messages. Unused when only the final response is returned.
        List<ChatMessage> transcript = [];

        // The loop-synthesized on-behalf-of messages that drive the current iteration (none for the first iteration).
        IReadOnlyList<ChatMessage> currentSurfaced = [];

        while (true)
        {
            // Run the wrapped agent using the context's session once it exists (it may have been replaced for a fresh
            // context), otherwise the resolved session for the first run.
            AgentSession activeSession = context?.Session ?? session;
            AgentResponse response = await this.InnerAgent.RunAsync(currentMessages, activeSession, options, cancellationToken).ConfigureAwait(false);
            iteration++;

            // Record this iteration's on-behalf-of input (before the response it elicited) and the response itself.
            transcript.AddRange(currentSurfaced);
            transcript.AddRange(response.Messages);

            // Create the context after the first run (so LastResponse is never null) and reuse it thereafter.
            // Expose the feedback log as a read-only wrapper so evaluators cannot downcast and mutate it; the
            // wrapper still reflects entries appended by the loop.
            context ??= new LoopContext(this.InnerAgent, session, initialMessages, response, options) { Feedback = feedbackLog.AsReadOnly() };

            context.Iteration = iteration;
            context.LastResponse = response;

            // Stop and surface the response when the agent is waiting for a tool approval.
            if (HasPendingApprovalRequests(response))
            {
                return this.BuildResult(response, transcript);
            }

            // Enforce the global safety cap regardless of what the evaluators want.
            if (iteration >= this._maxIterations)
            {
                this.LogMaxIterationsReached(iteration);
                return this.BuildResult(response, transcript);
            }

            // Ask the evaluators whether to continue; stop when none of them request a re-invocation.
            LoopNextStep step = await this.EvaluateAndBuildNextAsync(context, feedbackLog, initialSessionSnapshot, cancellationToken).ConfigureAwait(false);
            if (!step.ShouldContinue)
            {
                return this.BuildResult(response, transcript);
            }

            currentMessages = step.Messages;
            currentSurfaced = step.SurfacedMessages;
        }
    }

    /// <inheritdoc />
    protected override async IAsyncEnumerable<AgentResponseUpdate> RunCoreStreamingAsync(
        IEnumerable<ChatMessage> messages,
        AgentSession? session = null,
        AgentRunOptions? options = null,
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        _ = Throw.IfNull(messages);

        // Capture the caller's initial messages (sent once) and ensure the loop always runs against a session.
        IReadOnlyList<ChatMessage> initialMessages = messages as IReadOnlyList<ChatMessage> ?? messages.ToList();
        bool sessionProvidedByCaller = session is not null;
        if (session is null)
        {
            session = await this.InnerAgent.CreateSessionAsync(cancellationToken).ConfigureAwait(false);
            await this.NotifyNewSessionAsync(session, cancellationToken).ConfigureAwait(false);
        }

        // When a fresh context is requested over a caller-supplied session, snapshot the pristine session up front so
        // each re-invocation can restart from a fresh clone (see CreateFreshIterationSessionAsync). Taken before the
        // first iteration mutates the session.
        JsonElement? initialSessionSnapshot = this._freshContextPerIteration && sessionProvidedByCaller
            ? await this.InnerAgent.SerializeSessionAsync(session, cancellationToken: cancellationToken).ConfigureAwait(false)
            : null;

        LoopContext? context = null;
        List<string?> feedbackLog = [];
        IEnumerable<ChatMessage> currentMessages = initialMessages;
        int iteration = 0;

        // The loop-synthesized on-behalf-of messages that drive the current iteration (none for the first iteration).
        IReadOnlyList<ChatMessage> currentSurfaced = [];

        while (true)
        {
            // Stream this iteration's updates to the caller while collecting them so the iteration's full
            // response can be aggregated for evaluation (true per-iteration streaming). Uses the context's
            // session once it exists (it may have been replaced for a fresh context), otherwise the resolved session.
            AgentSession activeSession = context?.Session ?? session;
            List<AgentResponseUpdate> updates = [];

            // The on-behalf-of messages that drive this iteration are surfaced before the response they elicit (none
            // for the first iteration). They are flushed lazily on the first inner update so they can be stamped with
            // that update's ResponseId/AgentId, keeping them grouped with the iteration for downstream mergers.
            bool surfacedPending = currentSurfaced.Count > 0;
            await foreach (var update in this.InnerAgent.RunStreamingAsync(currentMessages, activeSession, options, cancellationToken).ConfigureAwait(false))
            {
                if (surfacedPending)
                {
                    foreach (ChatMessage surfaced in currentSurfaced)
                    {
                        yield return CreateOnBehalfOfUpdate(surfaced, update.ResponseId);
                    }

                    surfacedPending = false;
                }

                updates.Add(update);
                yield return update;
            }

            // The inner agent produced no updates this iteration; surface the on-behalf-of messages anyway. Since there
            // is no iteration response to inherit from, generate a ResponseId so they still group together downstream.
            if (surfacedPending)
            {
                string fallbackResponseId = System.Guid.NewGuid().ToString("N");
                foreach (ChatMessage surfaced in currentSurfaced)
                {
                    yield return CreateOnBehalfOfUpdate(surfaced, fallbackResponseId);
                }
            }

            // Aggregate this iteration's updates and record the result on the context.
            iteration++;
            AgentResponse response = updates.ToAgentResponse();

            // Create the context after the first run (so LastResponse is never null) and reuse it thereafter.
            // Expose the feedback log as a read-only wrapper so evaluators cannot downcast and mutate it; the
            // wrapper still reflects entries appended by the loop.
            context ??= new LoopContext(this.InnerAgent, session, initialMessages, response, options) { Feedback = feedbackLog.AsReadOnly() };

            context.Iteration = iteration;
            context.LastResponse = response;

            // Stop when the agent is waiting for a tool approval.
            if (HasPendingApprovalRequests(response))
            {
                yield break;
            }

            // Enforce the global safety cap regardless of what the evaluators want.
            if (iteration >= this._maxIterations)
            {
                this.LogMaxIterationsReached(iteration);
                yield break;
            }

            // Ask the evaluators whether to continue; stop when none of them request a re-invocation.
            LoopNextStep step = await this.EvaluateAndBuildNextAsync(context, feedbackLog, initialSessionSnapshot, cancellationToken).ConfigureAwait(false);
            if (!step.ShouldContinue)
            {
                yield break;
            }

            currentMessages = step.Messages;
            currentSurfaced = step.SurfacedMessages;
        }
    }

    /// <summary>
    /// Evaluates the evaluators in order and, for the first one that requests a re-invocation, builds the next input
    /// according to the loop's feedback and fresh-context policy.
    /// </summary>
    private async ValueTask<LoopNextStep> EvaluateAndBuildNextAsync(LoopContext context, List<string?> feedbackLog, JsonElement? initialSessionSnapshot, CancellationToken cancellationToken)
    {
        // Evaluate in order; the first evaluator that requests a re-invocation wins.
        LoopEvaluation? winner = null;
        foreach (LoopEvaluator evaluator in this._evaluators)
        {
            LoopEvaluation evaluation = await evaluator.EvaluateAsync(context, cancellationToken).ConfigureAwait(false);
            if (evaluation.ShouldReinvoke)
            {
                winner = evaluation;
                break;
            }
        }

        // Every evaluator asked to stop.
        if (winner is null)
        {
            return LoopNextStep.Stop();
        }

        // Start the next iteration from a fresh session when a fresh context is requested, so no prior conversation
        // history leaks across iterations. This applies regardless of how the next input is built (feedback or explicit
        // ContinueWithMessages): a caller-supplied session is cloned from the pristine start-of-run snapshot; a
        // loop-owned session is created anew.
        if (this._freshContextPerIteration)
        {
            context.Session = await this.CreateFreshIterationSessionAsync(context, initialSessionSnapshot, cancellationToken).ConfigureAwait(false);
        }

        // Record one feedback entry for this re-invoked iteration (null when none, including ContinueWithMessages
        // iterations which carry no feedback string) so the log stays aligned: one entry per re-invoked iteration, with
        // the last element always corresponding to the latest re-invoked iteration. Continue() normalizes whitespace to null.
        feedbackLog.Add(winner.Feedback);

        // An evaluator supplied explicit messages: send them verbatim, bypassing feedback/message construction (the
        // session is still reset above when a fresh context is requested). These are surfaced to the caller as-is (the
        // evaluator owns them, including any author name).
        if (winner.Messages is not null)
        {
            return LoopNextStep.Continue(winner.Messages, this.Surfaced(winner.Messages));
        }

        (List<ChatMessage> messages, List<ChatMessage> surfaced) = this.BuildNextMessages(context, feedbackLog);
        return LoopNextStep.Continue(messages, this.Surfaced(surfaced));
    }

    /// <summary>
    /// Returns the messages to surface to the caller, honoring <see cref="LoopAgentOptions.ExcludeOnBehalfOfMessages"/>.
    /// </summary>
    private IReadOnlyList<ChatMessage> Surfaced(IReadOnlyList<ChatMessage> surfaced)
        => this._excludeOnBehalfOfMessages ? [] : surfaced;

    /// <summary>
    /// Creates a streaming update for a surfaced on-behalf-of message, inheriting the driven iteration's
    /// <paramref name="responseId"/> so downstream mergers group it with that iteration, and ensuring a unique
    /// non-null <see cref="AgentResponseUpdate.MessageId"/>. The <see cref="AgentResponseUpdate.AgentId"/> is left
    /// unset because the message is synthesized by the loop, not produced by the wrapped agent.
    /// </summary>
    private static AgentResponseUpdate CreateOnBehalfOfUpdate(ChatMessage message, string? responseId)
        => new(message.Role, message.Contents)
        {
            AuthorName = message.AuthorName,
            MessageId = message.MessageId is { Length: > 0 } messageId ? messageId : System.Guid.NewGuid().ToString("N"),
            ResponseId = responseId,
        };

    /// <summary>
    /// Builds the messages sent to the wrapped agent for the next iteration along with the subset that should be
    /// surfaced to the caller (the loop-synthesized on-behalf-of feedback). Replayed caller input is excluded from the
    /// surfaced subset.
    /// </summary>
    private (List<ChatMessage> Messages, List<ChatMessage> Surfaced) BuildNextMessages(LoopContext context, List<string?> feedback)
    {
        var messages = new List<ChatMessage>();
        var surfaced = new List<ChatMessage>();

        if (this._freshContextPerIteration)
        {
            // Fresh context: re-send the original task plus an aggregated log of all feedback recorded so far. Only the
            // synthesized feedback message is surfaced; the replayed caller input messages are not.
            messages.AddRange(context.InitialMessages);

            ChatMessage? feedbackMessage = this.BuildAggregatedFeedbackMessage(feedback);
            if (feedbackMessage is not null)
            {
                messages.Add(feedbackMessage);
                surfaced.Add(feedbackMessage);
            }
        }
        else
        {
            // Reused session: send only the latest feedback verbatim (the session already retains earlier turns). When
            // the latest iteration produced no feedback, send no messages and let the agent continue from history.
            string? latest = feedback.Count > 0 ? feedback[feedback.Count - 1] : null;
            if (!string.IsNullOrWhiteSpace(latest))
            {
                var feedbackMessage = new ChatMessage(ChatRole.User, latest) { AuthorName = this._onBehalfOfAuthorName, MessageId = System.Guid.NewGuid().ToString("N") };
                messages.Add(feedbackMessage);
                surfaced.Add(feedbackMessage);
            }
        }

        return (messages, surfaced);
    }

    private ChatMessage? BuildAggregatedFeedbackMessage(IReadOnlyList<string?> feedback)
    {
        var body = new StringBuilder("## Feedback\n");
        bool any = false;
        foreach (string? entry in feedback)
        {
            if (!string.IsNullOrWhiteSpace(entry))
            {
                body.Append("\n- ").Append(entry);
                any = true;
            }
        }

        return any ? new ChatMessage(ChatRole.User, body.ToString()) { AuthorName = this._onBehalfOfAuthorName, MessageId = System.Guid.NewGuid().ToString("N") } : null;
    }

    /// <summary>
    /// Produces the non-streaming run result: either the final iteration's response (when configured) or an
    /// aggregated response carrying the full transcript with the final response's metadata.
    /// </summary>
    private AgentResponse BuildResult(AgentResponse lastResponse, List<ChatMessage> transcript)
    {
        if (this._nonStreamingReturnsLastResponseOnly)
        {
            return lastResponse;
        }

        return new AgentResponse(transcript)
        {
            AgentId = lastResponse.AgentId,
            ResponseId = lastResponse.ResponseId,
            CreatedAt = lastResponse.CreatedAt,
            FinishReason = lastResponse.FinishReason,
            Usage = lastResponse.Usage,
            AdditionalProperties = lastResponse.AdditionalProperties,
            ContinuationToken = lastResponse.ContinuationToken,
        };
    }

    private static bool HasPendingApprovalRequests(AgentResponse response)
    {
        foreach (ChatMessage message in response.Messages)
        {
            foreach (AIContent content in message.Contents)
            {
                if (content is ToolApprovalRequestContent)
                {
                    return true;
                }
            }
        }

        return false;
    }

    private void LogMaxIterationsReached(int iteration)
    {
        if (this._logger.IsEnabled(LogLevel.Information))
        {
            this._logger.LogInformation("LoopAgent reached the maximum of {MaxIterations} iterations and stopped.", iteration);
        }
    }

    /// <summary>
    /// Creates the session used for the next iteration when a fresh context is requested. A caller-supplied session is
    /// restored from the pristine start-of-run snapshot by deserializing a fresh clone; a loop-owned session (no
    /// snapshot) is created anew. The configured session-created callback is notified of the new session.
    /// </summary>
    private async ValueTask<AgentSession> CreateFreshIterationSessionAsync(LoopContext context, JsonElement? initialSessionSnapshot, CancellationToken cancellationToken)
    {
        AgentSession session = initialSessionSnapshot is { } snapshot
            ? await this.InnerAgent.DeserializeSessionAsync(snapshot, cancellationToken: cancellationToken).ConfigureAwait(false)
            : await context.Agent.CreateSessionAsync(cancellationToken).ConfigureAwait(false);

        await this.NotifyNewSessionAsync(session, cancellationToken).ConfigureAwait(false);
        return session;
    }

    /// <summary>
    /// Invokes the configured <see cref="LoopAgentOptions.SessionCreatedCallback"/> (if any) with a session the loop
    /// has just created, so the caller can observe the latest session.
    /// </summary>
    private async ValueTask NotifyNewSessionAsync(AgentSession session, CancellationToken cancellationToken)
    {
        if (this._sessionCreatedCallback is not null)
        {
            await this._sessionCreatedCallback(session, cancellationToken).ConfigureAwait(false);
        }
    }

    /// <summary>Represents the loop's decision for the next iteration: stop, or continue with a set of messages.</summary>
    private readonly struct LoopNextStep
    {
        private LoopNextStep(bool shouldContinue, IReadOnlyList<ChatMessage> messages, IReadOnlyList<ChatMessage> surfacedMessages)
        {
            this.ShouldContinue = shouldContinue;
            this.Messages = messages;
            this.SurfacedMessages = surfacedMessages;
        }

        public bool ShouldContinue { get; }

        /// <summary>Gets the full set of messages sent to the wrapped agent for the next iteration.</summary>
        public IReadOnlyList<ChatMessage> Messages { get; }

        /// <summary>
        /// Gets the subset of <see cref="Messages"/> the loop synthesized on the caller's behalf (feedback or
        /// evaluator-supplied messages) that should be surfaced to the caller. Replayed caller input is excluded.
        /// </summary>
        public IReadOnlyList<ChatMessage> SurfacedMessages { get; }

        public static LoopNextStep Stop() => new(shouldContinue: false, [], []);

        public static LoopNextStep Continue(IReadOnlyList<ChatMessage> messages, IReadOnlyList<ChatMessage> surfacedMessages)
            => new(shouldContinue: true, messages, surfacedMessages);
    }
}
