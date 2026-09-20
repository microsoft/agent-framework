// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.Logging;
using Moq;

using static Microsoft.Agents.AI.UnitTests.LoopTestHelpers;

namespace Microsoft.Agents.AI.UnitTests;

/// <summary>
/// Unit tests for the <see cref="DecisionLoopEvaluator"/> class.
/// </summary>
public class DecisionLoopEvaluatorTests
{
    #region Constructor

    /// <summary>
    /// Verify that the constructor throws when the decision client is null.
    /// </summary>
    [Fact]
    public void Constructor_NullClient_Throws()
    {
        // Act & Assert
        Assert.Throws<ArgumentNullException>("decisionClient", () => new DecisionLoopEvaluator(null!));
    }

    /// <summary>
    /// Verify that the constructor rejects a completion threshold outside the 0..1 range.
    /// </summary>
    [Theory]
    [InlineData(-0.01)]
    [InlineData(1.01)]
    [InlineData(double.NaN)]
    public void Constructor_InvalidThreshold_Throws(double threshold)
    {
        // Act & Assert
        Assert.Throws<ArgumentOutOfRangeException>("options", () => new DecisionLoopEvaluator(Always(0.5), new() { CompletionThreshold = threshold }));
    }

    /// <summary>
    /// Verify that the constructor rejects a blank completion question.
    /// </summary>
    [Theory]
    [InlineData("")]
    [InlineData("   ")]
    public void Constructor_BlankQuestion_Throws(string question)
    {
        // Act & Assert
        Assert.Throws<ArgumentException>("options", () => new DecisionLoopEvaluator(Always(0.5), new() { CompletionQuestion = question }));
    }

    /// <summary>
    /// Verify that a null completion question falls back to the default question.
    /// </summary>
    [Fact]
    public async Task Constructor_NullQuestion_UsesDefaultAsync()
    {
        // Arrange
        var client = new FakeDecisionClient(1.0);
        var evaluator = new DecisionLoopEvaluator(client, new() { CompletionQuestion = null! });

        // Act
        await evaluator.EvaluateAsync(CreateContext());

        // Assert
        Assert.Equal(DecisionLoopEvaluator.DefaultCompletionQuestion, client.LastQuestion!.Instructions);
    }

    /// <summary>
    /// Verify that the boundary thresholds 0 and 1 are accepted.
    /// </summary>
    [Theory]
    [InlineData(0.0)]
    [InlineData(1.0)]
    public void Constructor_BoundaryThreshold_Accepted(double threshold)
    {
        // Act
        var evaluator = new DecisionLoopEvaluator(Always(0.5), new() { CompletionThreshold = threshold });

        // Assert
        Assert.NotNull(evaluator);
    }

    #endregion

    #region Threshold behavior

    /// <summary>
    /// Verify that a probability at or above the threshold stops (does not request continuation).
    /// </summary>
    [Theory]
    [InlineData(0.90, 0.90)]
    [InlineData(0.90, 0.95)]
    [InlineData(0.90, 1.0)]
    [InlineData(0.0, 0.0)]
    public async Task EvaluateAsync_AtOrAboveThreshold_StopsAsync(double threshold, double probability)
    {
        // Arrange
        var evaluator = new DecisionLoopEvaluator(Always(probability), new() { CompletionThreshold = threshold });

        // Act
        LoopEvaluation evaluation = await evaluator.EvaluateAsync(CreateContext());

        // Assert
        Assert.False(evaluation.ShouldReinvoke);
    }

    /// <summary>
    /// Verify that a probability below the threshold continues with the default feedback message.
    /// </summary>
    [Theory]
    [InlineData(0.90, 0.89)]
    [InlineData(0.90, 0.0)]
    [InlineData(1.0, 0.999)]
    public async Task EvaluateAsync_BelowThreshold_ContinuesWithDefaultFeedbackAsync(double threshold, double probability)
    {
        // Arrange
        var evaluator = new DecisionLoopEvaluator(Always(probability), new() { CompletionThreshold = threshold });

        // Act
        LoopEvaluation evaluation = await evaluator.EvaluateAsync(CreateContext());

        // Assert
        Assert.True(evaluation.ShouldReinvoke);
        Assert.Equal(DecisionLoopEvaluator.DefaultContinueFeedbackMessage, evaluation.Feedback);
    }

    /// <summary>
    /// Verify that the default threshold is applied when no options are supplied.
    /// </summary>
    [Fact]
    public async Task EvaluateAsync_DefaultOptions_UsesDefaultThresholdAsync()
    {
        // Arrange
        var below = new DecisionLoopEvaluator(Always(DecisionLoopEvaluator.DefaultCompletionThreshold - 0.01));
        var at = new DecisionLoopEvaluator(Always(DecisionLoopEvaluator.DefaultCompletionThreshold));

        // Act & Assert
        Assert.True((await below.EvaluateAsync(CreateContext())).ShouldReinvoke);
        Assert.False((await at.EvaluateAsync(CreateContext())).ShouldReinvoke);
    }

    #endregion

    #region Feedback

    /// <summary>
    /// Verify that a custom continuation message is returned as feedback.
    /// </summary>
    [Fact]
    public async Task EvaluateAsync_CustomFeedback_IsReturnedAsync()
    {
        // Arrange
        var evaluator = new DecisionLoopEvaluator(Always(0.1), new() { ContinueFeedbackMessage = "Keep going." });

        // Act
        LoopEvaluation evaluation = await evaluator.EvaluateAsync(CreateContext());

        // Assert
        Assert.True(evaluation.ShouldReinvoke);
        Assert.Equal("Keep going.", evaluation.Feedback);
    }

    /// <summary>
    /// Verify that a null or whitespace continuation message yields a continuation without feedback.
    /// </summary>
    [Theory]
    [InlineData(null)]
    [InlineData("")]
    [InlineData("  ")]
    public async Task EvaluateAsync_NullFeedback_ContinuesWithoutFeedbackAsync(string? feedback)
    {
        // Arrange
        var evaluator = new DecisionLoopEvaluator(Always(0.1), new() { ContinueFeedbackMessage = feedback });

        // Act
        LoopEvaluation evaluation = await evaluator.EvaluateAsync(CreateContext());

        // Assert
        Assert.True(evaluation.ShouldReinvoke);
        Assert.Null(evaluation.Feedback);
    }

    #endregion

    #region Request and state projection

    /// <summary>
    /// Verify the request sent to the client: one binary question with the default text, criteria, and id, and the
    /// default text-only state.
    /// </summary>
    [Fact]
    public async Task EvaluateAsync_DefaultProjection_SendsExpectedRequestAsync()
    {
        // Arrange
        var client = new FakeDecisionClient(1.0);
        var evaluator = new DecisionLoopEvaluator(client);
        LoopContext context = CreateContext(
            [new ChatMessage(ChatRole.System, "be brief"), new ChatMessage(ChatRole.User, "original question")],
            "partial answer");
        context.Iteration = 3;

        // Act
        await evaluator.EvaluateAsync(context);

        // Assert
        DecisionRequest request = client.LastRequest!;
        BinaryDecisionQuestion question = Assert.IsType<BinaryDecisionQuestion>(Assert.Single(request.Questions));
        Assert.Equal(DecisionLoopEvaluator.CompletionQuestionId, question.Id);
        Assert.Equal(DecisionLoopEvaluator.DefaultCompletionQuestion, question.Instructions);
        Assert.NotNull(question.Criteria);
        Assert.Equal(DecisionLoopEvaluator.DefaultCompletedDescription, question.Criteria!.TrueDescription);
        Assert.Equal(DecisionLoopEvaluator.DefaultIncompleteDescription, question.Criteria.FalseDescription);
        Assert.Null(client.LastOptions);

        JsonElement state = request.State;
        Assert.Equal(JsonValueKind.Object, state.ValueKind);
        Assert.Equal("partial answer", state.GetProperty("latestResponse").GetString());
        Assert.Equal(3, state.GetProperty("iteration").GetInt32());

        JsonElement messages = state.GetProperty("originalRequest");
        Assert.Equal(2, messages.GetArrayLength());
        Assert.Equal("system", messages[0].GetProperty("role").GetString());
        Assert.Equal("be brief", messages[0].GetProperty("text").GetString());
        Assert.Equal("user", messages[1].GetProperty("role").GetString());
        Assert.Equal("original question", messages[1].GetProperty("text").GetString());
    }

    /// <summary>
    /// Verify that custom question text and descriptions flow into the request.
    /// </summary>
    [Fact]
    public async Task EvaluateAsync_CustomQuestion_FlowsIntoRequestAsync()
    {
        // Arrange
        var client = new FakeDecisionClient(1.0);
        var evaluator = new DecisionLoopEvaluator(client, new()
        {
            CompletionQuestion = "Is the report finished?",
            CompletedDescription = null,
            IncompleteDescription = "Sections are missing.",
        });

        // Act
        await evaluator.EvaluateAsync(CreateContext());

        // Assert
        BinaryDecisionQuestion question = client.LastQuestion!;
        Assert.Equal("Is the report finished?", question.Instructions);
        Assert.Null(question.Criteria!.TrueDescription);
        Assert.Equal("Sections are missing.", question.Criteria.FalseDescription);
    }

    /// <summary>
    /// Verify that when both descriptions are null no criteria object is sent.
    /// </summary>
    [Fact]
    public async Task EvaluateAsync_NoDescriptions_OmitsCriteriaAsync()
    {
        // Arrange
        var client = new FakeDecisionClient(1.0);
        var evaluator = new DecisionLoopEvaluator(client, new() { CompletedDescription = null, IncompleteDescription = null });

        // Act
        await evaluator.EvaluateAsync(CreateContext());

        // Assert
        Assert.Null(client.LastQuestion!.Criteria);
    }

    /// <summary>
    /// Verify that non-text content in the original request is rejected by the default projection rather than dropped.
    /// </summary>
    [Fact]
    public async Task EvaluateAsync_NonTextContent_ThrowsAsync()
    {
        // Arrange
        var client = new FakeDecisionClient(1.0);
        var evaluator = new DecisionLoopEvaluator(client);
        LoopContext context = CreateContext(
            [new ChatMessage(ChatRole.User, [new TextContent("describe this"), new DataContent(new byte[] { 1, 2, 3 }, "image/png")])],
            "an answer");

        // Act & Assert
        InvalidOperationException ex = await Assert.ThrowsAsync<InvalidOperationException>(async () => await evaluator.EvaluateAsync(context));
        Assert.Contains(nameof(DataContent), ex.Message);
        Assert.Contains(nameof(DecisionLoopEvaluatorOptions.StateFactory), ex.Message);
        Assert.Null(client.LastRequest);
    }

    /// <summary>
    /// Verify that the non-text rejection is not subject to the failure policy: it is a configuration error.
    /// </summary>
    [Fact]
    public async Task EvaluateAsync_NonTextContent_IgnoresFailureBehaviorAsync()
    {
        // Arrange
        var evaluator = new DecisionLoopEvaluator(Always(1.0), new() { FailureBehavior = DecisionLoopFailureBehavior.Continue });
        LoopContext context = CreateContext(
            [new ChatMessage(ChatRole.User, [new DataContent(new byte[] { 1 }, "image/png")])],
            "an answer");

        // Act & Assert
        await Assert.ThrowsAsync<InvalidOperationException>(async () => await evaluator.EvaluateAsync(context));
    }

    /// <summary>
    /// Verify that a custom state factory replaces the default projection and can carry non-text requests.
    /// </summary>
    [Fact]
    public async Task EvaluateAsync_StateFactory_ReplacesDefaultProjectionAsync()
    {
        // Arrange
        var client = new FakeDecisionClient(1.0);
        LoopContext? factoryContext = null;
        var evaluator = new DecisionLoopEvaluator(client, new()
        {
            StateFactory = context =>
            {
                factoryContext = context;
                using JsonDocument document = JsonDocument.Parse("\"custom state\"");
                return document.RootElement.Clone();
            },
        });
        LoopContext context = CreateContext(
            [new ChatMessage(ChatRole.User, [new DataContent(new byte[] { 1 }, "image/png")])],
            "an answer");

        // Act
        await evaluator.EvaluateAsync(context);

        // Assert
        Assert.Same(context, factoryContext);
        Assert.Equal(JsonValueKind.String, client.LastRequest!.State.ValueKind);
        Assert.Equal("custom state", client.LastRequest.State.GetString());
    }

    /// <summary>
    /// Verify that the evaluator does not mutate the loop context, session, or feedback log.
    /// </summary>
    [Fact]
    public async Task EvaluateAsync_DoesNotMutateContextAsync()
    {
        // Arrange
        var evaluator = new DecisionLoopEvaluator(Always(0.2));
        LoopContext context = CreateContext();
        AgentSession session = context.Session;
        AgentResponse response = context.LastResponse;

        // Act
        await evaluator.EvaluateAsync(context);

        // Assert
        Assert.Same(session, context.Session);
        Assert.Same(response, context.LastResponse);
        Assert.Empty(context.Feedback);
        Assert.Empty(context.AdditionalProperties);
    }

    #endregion

    #region Failure behavior

    /// <summary>
    /// Verify that a client exception propagates by default.
    /// </summary>
    [Fact]
    public async Task EvaluateAsync_ClientThrows_DefaultPropagatesAsync()
    {
        // Arrange
        var evaluator = new DecisionLoopEvaluator(Throwing(new DecisionClientException(DecisionFailureKind.ProviderUnavailable, "provider down")));

        // Act & Assert
        DecisionClientException ex = await Assert.ThrowsAsync<DecisionClientException>(async () => await evaluator.EvaluateAsync(CreateContext()));
        Assert.Equal("provider down", ex.Message);
    }

    /// <summary>
    /// Verify that with the Continue policy a client exception requests another iteration with the configured feedback.
    /// </summary>
    [Fact]
    public async Task EvaluateAsync_ClientThrows_ContinuePolicy_ContinuesAsync()
    {
        // Arrange
        var evaluator = new DecisionLoopEvaluator(
            Throwing(new DecisionClientException(DecisionFailureKind.RateLimited, "slow down")),
            new() { FailureBehavior = DecisionLoopFailureBehavior.Continue, ContinueFeedbackMessage = "retry" });

        // Act
        LoopEvaluation evaluation = await evaluator.EvaluateAsync(CreateContext());

        // Assert
        Assert.True(evaluation.ShouldReinvoke);
        Assert.Equal("retry", evaluation.Feedback);
    }

    /// <summary>
    /// Verify that with the DeferToNextEvaluator policy a client exception yields Stop.
    /// </summary>
    [Fact]
    public async Task EvaluateAsync_ClientThrows_DeferPolicy_StopsAsync()
    {
        // Arrange
        var evaluator = new DecisionLoopEvaluator(
            Throwing(new InvalidOperationException("provider down")),
            new() { FailureBehavior = DecisionLoopFailureBehavior.DeferToNextEvaluator });

        // Act
        LoopEvaluation evaluation = await evaluator.EvaluateAsync(CreateContext());

        // Assert
        Assert.False(evaluation.ShouldReinvoke);
    }

    /// <summary>
    /// Verify that a response without a binary answer for the completion question is an operational failure under every policy.
    /// </summary>
    [Theory]
    [InlineData(DecisionLoopFailureBehavior.Throw)]
    [InlineData(DecisionLoopFailureBehavior.Continue)]
    [InlineData(DecisionLoopFailureBehavior.DeferToNextEvaluator)]
    public async Task EvaluateAsync_MissingOrWrongAnswer_IsOperationalFailureAsync(DecisionLoopFailureBehavior behavior)
    {
        // Arrange: the client answers a different question id, and with a choice answer.
        var client = new FakeDecisionClient(_ => new DecisionResponse(new Dictionary<string, DecisionAnswer>
        {
            ["other"] = new ChoiceDecisionAnswer("a", new Dictionary<string, double> { ["a"] = 1.0 }),
        }));
        var evaluator = new DecisionLoopEvaluator(client, new() { FailureBehavior = behavior });

        // Act & Assert
        switch (behavior)
        {
            case DecisionLoopFailureBehavior.Throw:
                InvalidOperationException ex = await Assert.ThrowsAsync<InvalidOperationException>(async () => await evaluator.EvaluateAsync(CreateContext()));
                Assert.Contains(DecisionLoopEvaluator.CompletionQuestionId, ex.Message);
                break;
            case DecisionLoopFailureBehavior.Continue:
                Assert.True((await evaluator.EvaluateAsync(CreateContext())).ShouldReinvoke);
                break;
            default:
                Assert.False((await evaluator.EvaluateAsync(CreateContext())).ShouldReinvoke);
                break;
        }
    }

    /// <summary>
    /// Verify that caller-requested cancellation always propagates, regardless of the failure policy.
    /// </summary>
    [Theory]
    [InlineData(DecisionLoopFailureBehavior.Throw)]
    [InlineData(DecisionLoopFailureBehavior.Continue)]
    [InlineData(DecisionLoopFailureBehavior.DeferToNextEvaluator)]
    public async Task EvaluateAsync_Cancelled_PropagatesCancellationAsync(DecisionLoopFailureBehavior behavior)
    {
        // Arrange
        using var cts = new CancellationTokenSource();
        CancellationToken observed = default;
        var client = new FakeDecisionClient((_, cancellationToken) =>
        {
            observed = cancellationToken;
            cts.Cancel();
            cancellationToken.ThrowIfCancellationRequested();
            return Task.FromResult(Binary(1.0));
        });
        var evaluator = new DecisionLoopEvaluator(client, new() { FailureBehavior = behavior });

        // Act & Assert
        await Assert.ThrowsAnyAsync<OperationCanceledException>(async () => await evaluator.EvaluateAsync(CreateContext(), cts.Token));
        Assert.Equal(cts.Token, observed);
    }

    /// <summary>
    /// Verify that an <see cref="OperationCanceledException"/> thrown by the client without a caller cancellation request
    /// is treated as an ordinary operational failure (for example a provider-side timeout) and follows the policy.
    /// </summary>
    [Fact]
    public async Task EvaluateAsync_ProviderTimeout_FollowsFailurePolicyAsync()
    {
        // Arrange
        var evaluator = new DecisionLoopEvaluator(
            Throwing(new OperationCanceledException("provider timeout")),
            new() { FailureBehavior = DecisionLoopFailureBehavior.Continue });

        // Act
        LoopEvaluation evaluation = await evaluator.EvaluateAsync(CreateContext());

        // Assert
        Assert.True(evaluation.ShouldReinvoke);
    }

    #endregion

    #region Transient failures and logging

    /// <summary>
    /// Verify that a transient client failure follows the transient policy while a permanent one follows the general policy.
    /// </summary>
    [Fact]
    public async Task EvaluateAsync_TransientFailure_FollowsTransientPolicy_PermanentStillThrowsAsync()
    {
        // Arrange
        var options = new DecisionLoopEvaluatorOptions
        {
            FailureBehavior = DecisionLoopFailureBehavior.Throw,
            TransientFailureBehavior = DecisionLoopFailureBehavior.DeferToNextEvaluator,
        };
        var transient = new DecisionLoopEvaluator(Throwing(new DecisionClientException(DecisionFailureKind.RateLimited, "slow down")), options);
        var permanent = new DecisionLoopEvaluator(Throwing(new DecisionClientException(DecisionFailureKind.Authentication, "bad key")), options);
        var unclassified = new DecisionLoopEvaluator(Throwing(new InvalidOperationException("boom")), options);

        // Act & Assert
        Assert.False((await transient.EvaluateAsync(CreateContext())).ShouldReinvoke);
        await Assert.ThrowsAsync<DecisionClientException>(async () => await permanent.EvaluateAsync(CreateContext()));
        await Assert.ThrowsAsync<InvalidOperationException>(async () => await unclassified.EvaluateAsync(CreateContext()));
    }

    /// <summary>
    /// Verify that without a transient policy, a transient failure follows the general failure behavior.
    /// </summary>
    [Theory]
    [InlineData(DecisionLoopFailureBehavior.Throw)]
    [InlineData(DecisionLoopFailureBehavior.Continue)]
    [InlineData(DecisionLoopFailureBehavior.DeferToNextEvaluator)]
    public async Task EvaluateAsync_TransientFailure_NoTransientPolicy_FollowsFailureBehaviorAsync(DecisionLoopFailureBehavior behavior)
    {
        // Arrange
        var evaluator = new DecisionLoopEvaluator(
            Throwing(new DecisionClientException(DecisionFailureKind.Overloaded, "busy")),
            new() { FailureBehavior = behavior, TransientFailureBehavior = null });

        // Act & Assert
        switch (behavior)
        {
            case DecisionLoopFailureBehavior.Throw:
                await Assert.ThrowsAsync<DecisionClientException>(async () => await evaluator.EvaluateAsync(CreateContext()));
                break;
            case DecisionLoopFailureBehavior.Continue:
                Assert.True((await evaluator.EvaluateAsync(CreateContext())).ShouldReinvoke);
                break;
            default:
                Assert.False((await evaluator.EvaluateAsync(CreateContext())).ShouldReinvoke);
                break;
        }
    }

    /// <summary>
    /// Verify that a transient policy of Continue keeps the loop going with feedback while the transient exception is not surfaced.
    /// </summary>
    [Fact]
    public async Task EvaluateAsync_TransientFailure_ContinuePolicy_ContinuesWithFeedbackAsync()
    {
        // Arrange
        var evaluator = new DecisionLoopEvaluator(
            Throwing(new DecisionClientException(DecisionFailureKind.ProviderUnavailable, "down")),
            new() { TransientFailureBehavior = DecisionLoopFailureBehavior.Continue, ContinueFeedbackMessage = "try again" });

        // Act
        LoopEvaluation evaluation = await evaluator.EvaluateAsync(CreateContext());

        // Assert
        Assert.True(evaluation.ShouldReinvoke);
        Assert.Equal("try again", evaluation.Feedback);
    }

    /// <summary>
    /// Verify that each evaluation logs the iteration, probability, threshold, and outcome at debug level, without the state.
    /// </summary>
    [Fact]
    public async Task EvaluateAsync_LogsDecisionWithoutStateAsync()
    {
        // Arrange
        var logs = new CapturingLoggerFactory();
        var evaluator = new DecisionLoopEvaluator(Always(0.42), new() { CompletionThreshold = 0.9 }, logs);
        LoopContext context = CreateContext([new ChatMessage(ChatRole.User, "SECRET-REQUEST")], "SECRET-RESPONSE");
        context.Iteration = 2;

        // Act
        await evaluator.EvaluateAsync(context);

        // Assert
        (LogLevel level, string message, Exception? exception) entry = Assert.Single(logs.Entries);
        Assert.Equal(LogLevel.Debug, entry.level);
        Assert.Null(entry.exception);
        Assert.Contains("iteration 2", entry.message);
        Assert.Contains("0.420", entry.message);
        Assert.Contains("0.90", entry.message);
        Assert.Contains("continue", entry.message);
        Assert.DoesNotContain("SECRET", entry.message);
    }

    /// <summary>
    /// Verify that applying a failure policy logs a warning carrying the exception, its kind, and transience.
    /// </summary>
    [Fact]
    public async Task EvaluateAsync_FailurePolicyApplied_LogsWarningAsync()
    {
        // Arrange
        var logs = new CapturingLoggerFactory();
        var exception = new DecisionClientException(DecisionFailureKind.RateLimited, "slow down");
        var evaluator = new DecisionLoopEvaluator(Throwing(exception), new() { TransientFailureBehavior = DecisionLoopFailureBehavior.DeferToNextEvaluator }, logs);

        // Act
        await evaluator.EvaluateAsync(CreateContext());

        // Assert
        (LogLevel level, string message, Exception? loggedException) entry = Assert.Single(logs.Entries);
        Assert.Equal(LogLevel.Warning, entry.level);
        Assert.Same(exception, entry.loggedException);
        Assert.Contains("RateLimited", entry.message);
        Assert.Contains("transient: True", entry.message);
        Assert.Contains(nameof(DecisionLoopFailureBehavior.DeferToNextEvaluator), entry.message);
    }

    /// <summary>
    /// Verify that a propagated failure is not logged as a handled policy (the caller sees the exception instead).
    /// </summary>
    [Fact]
    public async Task EvaluateAsync_ThrowPolicy_DoesNotLogWarningAsync()
    {
        // Arrange
        var logs = new CapturingLoggerFactory();
        var evaluator = new DecisionLoopEvaluator(Throwing(new DecisionClientException(DecisionFailureKind.Authentication, "bad key")), loggerFactory: logs);

        // Act & Assert
        await Assert.ThrowsAsync<DecisionClientException>(async () => await evaluator.EvaluateAsync(CreateContext()));
        Assert.Empty(logs.Entries);
    }

    #endregion

    #region Concurrency

    /// <summary>
    /// Verify that a single evaluator instance can be shared across concurrent evaluations with independent contexts.
    /// </summary>
    [Fact]
    public async Task EvaluateAsync_SharedInstance_IsSafeAcrossConcurrentRunsAsync()
    {
        // Arrange: the probability is derived from the request state so each run has its own expected outcome.
        var client = new FakeDecisionClient(async (request, _) =>
        {
            await Task.Yield();
            return Binary(request.State.GetProperty("latestResponse").GetString() == "done" ? 1.0 : 0.0);
        });
        var evaluator = new DecisionLoopEvaluator(client);

        // Act
        Task<LoopEvaluation>[] runs = Enumerable.Range(0, 50)
            .Select(i => evaluator.EvaluateAsync(CreateContext(response: i % 2 == 0 ? "done" : "not yet")).AsTask())
            .ToArray();
        LoopEvaluation[] results = await Task.WhenAll(runs);

        // Assert
        for (int i = 0; i < results.Length; i++)
        {
            Assert.Equal(i % 2 != 0, results[i].ShouldReinvoke);
        }
    }

    #endregion

    #region LoopAgent composition (cheap decision + strong judge cascade)

    /// <summary>
    /// Verify that when the decision evaluator continues, a later AI judge is not invoked and the agent runs again.
    /// </summary>
    [Fact]
    public async Task LoopAgent_DecisionContinues_SkipsLaterJudgeAsync()
    {
        // Arrange
        int judgeCalls = 0;
        var judge = new DelegateLoopEvaluator((_, _) =>
        {
            judgeCalls++;
            return new ValueTask<LoopEvaluation>(LoopEvaluation.Stop());
        });
        var inner = new InnerAgentCapture(call => new AgentResponse([new ChatMessage(ChatRole.Assistant, $"response {call}")]));
        var loop = new LoopAgent(inner.Agent, [new DecisionLoopEvaluator(Always(0.2)), judge], new LoopAgentOptions { MaxIterations = 3 });

        // Act
        await loop.RunAsync([new ChatMessage(ChatRole.User, "task")], new ChatClientAgentSession());

        // Assert
        Assert.Equal(3, inner.CallCount);
        Assert.Equal(0, judgeCalls);
        Assert.Equal(DecisionLoopEvaluator.DefaultContinueFeedbackMessage, inner.MessagesPerCall[1].Single().Text);
    }

    /// <summary>
    /// Verify that when the decision evaluator stops, the later judge runs and can still request continuation.
    /// </summary>
    [Fact]
    public async Task LoopAgent_DecisionStops_LaterJudgeDecidesAsync()
    {
        // Arrange
        int judgeCalls = 0;
        var judge = new DelegateLoopEvaluator((_, _) =>
        {
            judgeCalls++;
            return new ValueTask<LoopEvaluation>(judgeCalls == 1 ? LoopEvaluation.Continue("gap: missing summary") : LoopEvaluation.Stop());
        });
        var inner = new InnerAgentCapture(call => new AgentResponse([new ChatMessage(ChatRole.Assistant, $"response {call}")]));
        var loop = new LoopAgent(inner.Agent, [new DecisionLoopEvaluator(Always(0.99)), judge], new LoopAgentOptions { MaxIterations = 5 });

        // Act
        await loop.RunAsync([new ChatMessage(ChatRole.User, "task")], new ChatClientAgentSession());

        // Assert: iteration 1 -> decision stop, judge continue; iteration 2 -> decision stop, judge stop -> loop ends.
        Assert.Equal(2, inner.CallCount);
        Assert.Equal(2, judgeCalls);
        Assert.Equal("gap: missing summary", inner.MessagesPerCall[1].Single().Text);
    }

    /// <summary>
    /// Verify that when both evaluators stop the loop terminates after a single iteration.
    /// </summary>
    [Fact]
    public async Task LoopAgent_BothStop_TerminatesAsync()
    {
        // Arrange
        var inner = new InnerAgentCapture(_ => new AgentResponse([new ChatMessage(ChatRole.Assistant, "done")]));
        var loop = new LoopAgent(inner.Agent, [new DecisionLoopEvaluator(Always(1.0)), While(static _ => false)], new LoopAgentOptions { MaxIterations = 5 });

        // Act
        await loop.RunAsync([new ChatMessage(ChatRole.User, "task")], new ChatClientAgentSession());

        // Assert
        Assert.Equal(1, inner.CallCount);
    }

    /// <summary>
    /// Verify that with DeferToNextEvaluator a provider failure lets the later evaluator decide.
    /// </summary>
    [Fact]
    public async Task LoopAgent_DecisionFailsWithDefer_LaterJudgeRunsAsync()
    {
        // Arrange
        int judgeCalls = 0;
        var judge = new DelegateLoopEvaluator((_, _) =>
        {
            judgeCalls++;
            return new ValueTask<LoopEvaluation>(judgeCalls == 1 ? LoopEvaluation.Continue("judge says more") : LoopEvaluation.Stop());
        });
        var decision = new DecisionLoopEvaluator(
            Throwing(new DecisionClientException(DecisionFailureKind.Overloaded, "provider down")),
            new() { FailureBehavior = DecisionLoopFailureBehavior.DeferToNextEvaluator });
        var inner = new InnerAgentCapture(call => new AgentResponse([new ChatMessage(ChatRole.Assistant, $"response {call}")]));
        var loop = new LoopAgent(inner.Agent, [decision, judge], new LoopAgentOptions { MaxIterations = 5 });

        // Act
        await loop.RunAsync([new ChatMessage(ChatRole.User, "task")], new ChatClientAgentSession());

        // Assert
        Assert.Equal(2, inner.CallCount);
        Assert.Equal(2, judgeCalls);
    }

    /// <summary>
    /// Verify that with DeferToNextEvaluator and no later evaluator, a provider failure ends the loop.
    /// </summary>
    [Fact]
    public async Task LoopAgent_DecisionFailsWithDefer_OnlyEvaluator_StopsLoopAsync()
    {
        // Arrange
        var decision = new DecisionLoopEvaluator(
            Throwing(new DecisionClientException(DecisionFailureKind.Overloaded, "provider down")),
            new() { FailureBehavior = DecisionLoopFailureBehavior.DeferToNextEvaluator });
        var inner = new InnerAgentCapture(_ => new AgentResponse([new ChatMessage(ChatRole.Assistant, "response")]));
        var loop = new LoopAgent(inner.Agent, decision, new LoopAgentOptions { MaxIterations = 5 });

        // Act
        await loop.RunAsync([new ChatMessage(ChatRole.User, "task")], new ChatClientAgentSession());

        // Assert
        Assert.Equal(1, inner.CallCount);
    }

    /// <summary>
    /// Verify that with the default Throw policy a provider failure surfaces from the loop run.
    /// </summary>
    [Fact]
    public async Task LoopAgent_DecisionFailsWithThrow_PropagatesAsync()
    {
        // Arrange
        var decision = new DecisionLoopEvaluator(Throwing(new DecisionClientException(DecisionFailureKind.Authentication, "bad key")));
        var inner = new InnerAgentCapture(_ => new AgentResponse([new ChatMessage(ChatRole.Assistant, "response")]));
        var loop = new LoopAgent(inner.Agent, decision, new LoopAgentOptions { MaxIterations = 5 });

        // Act & Assert
        await Assert.ThrowsAsync<DecisionClientException>(() => loop.RunAsync([new ChatMessage(ChatRole.User, "task")], new ChatClientAgentSession()));
    }

    #endregion

    #region Helpers

    private static DecisionResponse Binary(double probability) =>
        new(new Dictionary<string, DecisionAnswer> { [DecisionLoopEvaluator.CompletionQuestionId] = new BinaryDecisionAnswer(probability) });

    private static FakeDecisionClient Always(double probability) => new(probability);

    private static FakeDecisionClient Throwing(Exception exception) => new((_, _) => throw exception);

    private static LoopContext CreateContext(IReadOnlyList<ChatMessage>? initialMessages = null, string response = "partial answer") => new(
        new Mock<AIAgent>().Object,
        new ChatClientAgentSession(),
        initialMessages ?? [new ChatMessage(ChatRole.User, "original question")],
        new AgentResponse([new ChatMessage(ChatRole.Assistant, response)]));

    /// <summary>A minimal <see cref="IDecisionClient"/> that answers from a callback and records the last request.</summary>
    private sealed class FakeDecisionClient : IDecisionClient
    {
        private readonly Func<DecisionRequest, CancellationToken, Task<DecisionResponse>> _respond;

        public FakeDecisionClient(double probability)
            : this((_, _) => Task.FromResult(Binary(probability)))
        {
        }

        public FakeDecisionClient(Func<DecisionRequest, DecisionResponse> respond)
            : this((request, _) => Task.FromResult(respond(request)))
        {
        }

        public FakeDecisionClient(Func<DecisionRequest, CancellationToken, Task<DecisionResponse>> respond)
        {
            this._respond = respond;
        }

        public DecisionRequest? LastRequest { get; private set; }

        public DecisionOptions? LastOptions { get; private set; }

        public BinaryDecisionQuestion? LastQuestion => this.LastRequest?.Questions.OfType<BinaryDecisionQuestion>().FirstOrDefault();

        public Task<DecisionResponse> GetResponseAsync(DecisionRequest request, DecisionOptions? options = null, CancellationToken cancellationToken = default)
        {
            this.LastRequest = request;
            this.LastOptions = options;
            return this._respond(request, cancellationToken);
        }

        public object? GetService(Type serviceType, object? serviceKey = null) => null;

        public void Dispose()
        {
        }
    }

    /// <summary>A logger factory that records every log entry for assertions.</summary>
    private sealed class CapturingLoggerFactory : ILoggerFactory
    {
        public List<(LogLevel Level, string Message, Exception? Exception)> Entries { get; } = [];

        public ILogger CreateLogger(string categoryName) => new CapturingLogger(this);

        public void AddProvider(ILoggerProvider provider)
        {
        }

        public void Dispose()
        {
        }

        private sealed class CapturingLogger(CapturingLoggerFactory owner) : ILogger
        {
            public IDisposable? BeginScope<TState>(TState state)
                where TState : notnull => null;

            public bool IsEnabled(LogLevel logLevel) => true;

            public void Log<TState>(LogLevel logLevel, EventId eventId, TState state, Exception? exception, Func<TState, Exception?, string> formatter) =>
                owner.Entries.Add((logLevel, formatter(state, exception), exception));
        }
    }

    #endregion
}
