// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
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
/// A <see cref="LoopEvaluator"/> that asks an <see cref="IDecisionClient"/> for the model-reported probability that the
/// user's original request has been fully addressed, and stops requesting iterations once that probability reaches a
/// configured completion threshold.
/// </summary>
/// <remarks>
/// <para>
/// This evaluator targets decision-oriented inference: models that evaluate application state against a bounded yes/no
/// question and return a probability directly, rather than generating text. It complements
/// <see cref="AIJudgeLoopEvaluator"/>, which uses a generative <see cref="IChatClient"/> judge and can therefore also
/// produce a free-form gap analysis. A decision model reports only a probability, so when this evaluator continues the
/// loop it carries the deterministic <see cref="DecisionLoopEvaluatorOptions.ContinueFeedbackMessage"/> as feedback
/// instead of model-generated text.
/// </para>
/// <para>
/// After each iteration the evaluator sends the client one <see cref="BinaryDecisionQuestion"/> (identifier
/// <see cref="CompletionQuestionId"/>, text <see cref="DecisionLoopEvaluatorOptions.CompletionQuestion"/>) against the
/// projected loop state and reads the <see cref="BinaryDecisionAnswer.TrueProbability"/>. The evaluator, not the client,
/// applies <see cref="DecisionLoopEvaluatorOptions.CompletionThreshold"/>: a probability at or above the threshold
/// yields <see cref="LoopEvaluation.Stop"/>, anything below yields <see cref="LoopEvaluation.Continue(string)"/>.
/// </para>
/// <para>
/// Because <see cref="LoopAgent"/> evaluates its evaluators in order and stops only when all of them return
/// <see cref="LoopEvaluation.Stop"/>, placing this evaluator before an <see cref="AIJudgeLoopEvaluator"/> yields a
/// cheap-then-strong cascade: when the decision model judges the work incomplete the expensive judge is skipped and the
/// agent runs again, and when it judges the work complete the strong judge verifies before the loop ends.
/// </para>
/// <para>
/// By default the state sent to the client is a minimal text projection: the role and text of each original request
/// message, the latest response text, and the iteration number. Like <see cref="AIJudgeLoopEvaluator"/>, it judges the
/// latest response; agents that build an answer incrementally across turns need a
/// <see cref="DecisionLoopEvaluatorOptions.StateFactory"/> that accumulates. Because the projection cannot faithfully
/// represent non-text content, the evaluator throws rather than silently judging an incomplete representation when the
/// original request contains content other than <see cref="TextContent"/>; supply a state factory to judge such requests.
/// </para>
/// <para>
/// Operational failures of the client (a <see cref="DecisionClientException"/> or any other exception, or a missing or
/// mismatched answer) are not treated as "incomplete". They are handled according to
/// <see cref="DecisionLoopEvaluatorOptions.FailureBehavior"/>, which defaults to propagating the exception; a failure the
/// client reports as transient (<see cref="DecisionClientException.IsTransient"/>) follows
/// <see cref="DecisionLoopEvaluatorOptions.TransientFailureBehavior"/> when one is configured. Cancellation requested
/// through the supplied token always propagates.
/// </para>
/// <para>
/// When a logger factory is supplied, the evaluator logs one line per evaluation (iteration, model-reported probability,
/// threshold, and outcome) at debug level, and a warning when a failure policy other than throwing is applied. The
/// warning carries only the exception type, failure kind, status code, and transience, never the exception message or
/// the projected state.
/// </para>
/// <para>
/// <strong>Security considerations:</strong> Using this evaluator is an explicit opt-in. The decision client is an
/// additional external inference boundary: on every iteration it receives the projected original request and the
/// agent's latest response, both of which may contain sensitive or untrusted content. Only configure a client you trust
/// as much as the primary model, and keep the state projection minimal. The probability is a model-reported value, not
/// a calibrated guarantee; it must not be used as an authorization or approval signal.
/// </para>
/// </remarks>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public sealed class DecisionLoopEvaluator : LoopEvaluator
{
    /// <summary>The default value of <see cref="DecisionLoopEvaluatorOptions.CompletionThreshold"/>.</summary>
    public const double DefaultCompletionThreshold = 0.90;

    /// <summary>The default value of <see cref="DecisionLoopEvaluatorOptions.CompletionQuestion"/>.</summary>
    public const string DefaultCompletionQuestion = "Has the agent fully addressed the user's original request?";

    /// <summary>The default value of <see cref="DecisionLoopEvaluatorOptions.CompletedDescription"/>.</summary>
    public const string DefaultCompletedDescription = "The original request has been fully addressed and no material requested work remains.";

    /// <summary>The default value of <see cref="DecisionLoopEvaluatorOptions.IncompleteDescription"/>.</summary>
    public const string DefaultIncompleteDescription = "Material requested work remains incomplete or missing.";

    /// <summary>The default value of <see cref="DecisionLoopEvaluatorOptions.ContinueFeedbackMessage"/>.</summary>
    public const string DefaultContinueFeedbackMessage = "The original request is not yet fully addressed. Continue working on it.";

    /// <summary>The <see cref="DecisionQuestion.Id"/> of the completion question sent to the client.</summary>
    public const string CompletionQuestionId = "task_completed";

    private readonly IDecisionClient _decisionClient;
    private readonly double _completionThreshold;
    private readonly string _completionQuestion;
    private readonly BinaryDecisionCriteria? _criteria;
    private readonly string? _continueFeedbackMessage;
    private readonly Func<LoopContext, JsonElement>? _stateFactory;
    private readonly DecisionLoopFailureBehavior _failureBehavior;
    private readonly DecisionLoopFailureBehavior? _transientFailureBehavior;
    private readonly ILogger _logger;

    /// <summary>
    /// Initializes a new instance of the <see cref="DecisionLoopEvaluator"/> class.
    /// </summary>
    /// <param name="decisionClient">
    /// The decision client that answers the completion question. <strong>Security:</strong> the client is sent the
    /// projected original request and the agent's latest response on every iteration, so only configure a client that
    /// points at a service you trust as much as the primary model — see the type-level security considerations.
    /// </param>
    /// <param name="options">Optional configuration. When <see langword="null"/>, defaults are used.</param>
    /// <param name="loggerFactory">Optional factory used to create the evaluator's logger.</param>
    /// <exception cref="ArgumentNullException"><paramref name="decisionClient"/> is <see langword="null"/>.</exception>
    /// <exception cref="ArgumentOutOfRangeException"><see cref="DecisionLoopEvaluatorOptions.CompletionThreshold"/> is not between 0 and 1 inclusive.</exception>
    /// <exception cref="ArgumentException"><see cref="DecisionLoopEvaluatorOptions.CompletionQuestion"/> is empty or whitespace.</exception>
    public DecisionLoopEvaluator(IDecisionClient decisionClient, DecisionLoopEvaluatorOptions? options = null, ILoggerFactory? loggerFactory = null)
    {
        this._decisionClient = Throw.IfNull(decisionClient);

        double threshold = options?.CompletionThreshold ?? DefaultCompletionThreshold;
        if (double.IsNaN(threshold) || threshold < 0 || threshold > 1)
        {
            throw new ArgumentOutOfRangeException(nameof(options), threshold, $"{nameof(DecisionLoopEvaluatorOptions.CompletionThreshold)} must be between 0 and 1 inclusive.");
        }

        string question = options?.CompletionQuestion ?? DefaultCompletionQuestion;
        if (string.IsNullOrWhiteSpace(question))
        {
            throw new ArgumentException($"{nameof(DecisionLoopEvaluatorOptions.CompletionQuestion)} must not be empty.", nameof(options));
        }

        string? completed = options is null ? DefaultCompletedDescription : options.CompletedDescription;
        string? incomplete = options is null ? DefaultIncompleteDescription : options.IncompleteDescription;

        this._completionThreshold = threshold;
        this._completionQuestion = question;
        this._criteria = completed is null && incomplete is null
            ? null
            : new BinaryDecisionCriteria { TrueDescription = completed, FalseDescription = incomplete };
        this._continueFeedbackMessage = options is null ? DefaultContinueFeedbackMessage : options.ContinueFeedbackMessage;
        this._stateFactory = options?.StateFactory;
        this._failureBehavior = options?.FailureBehavior ?? DecisionLoopFailureBehavior.Throw;
        this._transientFailureBehavior = options?.TransientFailureBehavior;
        this._logger = (loggerFactory ?? NullLoggerFactory.Instance).CreateLogger<DecisionLoopEvaluator>();
    }

    /// <inheritdoc />
    public override async ValueTask<LoopEvaluation> EvaluateAsync(LoopContext context, CancellationToken cancellationToken = default)
    {
        _ = Throw.IfNull(context);

        // State projection errors (including rejected non-text content) are configuration problems and always propagate;
        // the failure policy applies only to the decision client itself.
        JsonElement state = this._stateFactory is not null
            ? this._stateFactory(context)
            : CreateDefaultState(context);

        var question = new BinaryDecisionQuestion(CompletionQuestionId, this._completionQuestion) { Criteria = this._criteria };
        var request = new DecisionRequest(state, [question]);

        double probability;
        try
        {
            DecisionResponse response = await this._decisionClient.GetResponseAsync(request, options: null, cancellationToken).ConfigureAwait(false);

            if (!response.Answers.TryGetValue(CompletionQuestionId, out DecisionAnswer? rawAnswer) || rawAnswer is not BinaryDecisionAnswer answer)
            {
                throw new InvalidOperationException($"The decision client did not return a binary answer for question '{CompletionQuestionId}'.");
            }

            probability = answer.TrueProbability;
        }
        catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
        {
            throw;
        }
        catch (Exception ex) when (this.ResolveFailureBehavior(ex) == DecisionLoopFailureBehavior.Continue)
        {
            this.LogFailurePolicyApplied(ex, context.Iteration, DecisionLoopFailureBehavior.Continue);
            return LoopEvaluation.Continue(this._continueFeedbackMessage);
        }
        catch (Exception ex) when (this.ResolveFailureBehavior(ex) == DecisionLoopFailureBehavior.DeferToNextEvaluator)
        {
            this.LogFailurePolicyApplied(ex, context.Iteration, DecisionLoopFailureBehavior.DeferToNextEvaluator);
            return LoopEvaluation.Stop();
        }

        // At or above the threshold this evaluator does not request another iteration. Later evaluators (if any) are
        // still consulted by the LoopAgent, which is what enables the cheap-then-strong cascade.
        bool complete = probability >= this._completionThreshold;

        if (this._logger.IsEnabled(LogLevel.Debug))
        {
            this._logger.LogDebug(
                "DecisionLoopEvaluator iteration {Iteration}: model-reported P(complete) = {Probability:F3}, threshold {Threshold:F2}, outcome {Outcome}.",
                context.Iteration,
                probability,
                this._completionThreshold,
                complete ? "no-continuation" : "continue");
        }

        return complete
            ? LoopEvaluation.Stop()
            : LoopEvaluation.Continue(this._continueFeedbackMessage);
    }

    /// <summary>
    /// Selects the failure behavior for <paramref name="exception"/>: the transient behavior, when one is configured and
    /// the client reports the failure as transient; otherwise the general failure behavior.
    /// </summary>
    private DecisionLoopFailureBehavior ResolveFailureBehavior(Exception exception) =>
        this._transientFailureBehavior is { } transient && exception is DecisionClientException { IsTransient: true }
            ? transient
            : this._failureBehavior;

    private void LogFailurePolicyApplied(Exception exception, int iteration, DecisionLoopFailureBehavior behavior)
    {
        if (this._logger.IsEnabled(LogLevel.Warning))
        {
            // Only classification fields are logged. The exception object is deliberately not attached: a provider
            // error body excerpted into its message could echo request data, and this evaluator never logs the state.
            this._logger.LogWarning(
                "DecisionLoopEvaluator iteration {Iteration}: the decision client failed ({ExceptionType}, kind {FailureKind}, status {StatusCode}, transient: {IsTransient}); applying {FailureBehavior}.",
                iteration,
                exception.GetType().Name,
                exception is DecisionClientException dce ? dce.Kind.ToString() : "n/a",
                exception is DecisionClientException { StatusCode: { } status } ? status.ToString(System.Globalization.CultureInfo.InvariantCulture) : "n/a",
                exception is DecisionClientException { IsTransient: true },
                behavior);
        }
    }

    /// <summary>
    /// Builds the default, minimal text-only state: the role and text of each original request message, the latest
    /// response text, and the iteration number. Throws when the original request carries non-text content, because a
    /// text projection would silently misrepresent it.
    /// </summary>
    private static JsonElement CreateDefaultState(LoopContext context)
    {
        var originalRequest = new List<DecisionLoopMessage>(context.InitialMessages.Count);
        foreach (ChatMessage message in context.InitialMessages)
        {
            foreach (AIContent content in message.Contents)
            {
                if (content is not TextContent)
                {
                    throw new InvalidOperationException(
                        $"The original request contains non-text content ({content.GetType().Name}) that the default state projection cannot represent. " +
                        $"Supply {nameof(DecisionLoopEvaluatorOptions)}.{nameof(DecisionLoopEvaluatorOptions.StateFactory)} to judge this request.");
                }
            }

            originalRequest.Add(new DecisionLoopMessage { Role = message.Role.Value, Text = message.Text });
        }

        var state = new DecisionLoopState
        {
            OriginalRequest = originalRequest,
            LatestResponse = context.LastResponse.Text,
            Iteration = context.Iteration,
        };

        return JsonSerializer.SerializeToElement(state, LoopJsonContext.Default.DecisionLoopState);
    }
}
