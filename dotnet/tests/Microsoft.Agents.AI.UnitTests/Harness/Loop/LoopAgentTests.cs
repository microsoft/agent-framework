// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Moq;
using Moq.Protected;

using static Microsoft.Agents.AI.UnitTests.LoopTestHelpers;

namespace Microsoft.Agents.AI.UnitTests;

/// <summary>
/// Unit tests for the <see cref="LoopAgent"/> class.
/// </summary>
public class LoopAgentTests
{
    #region Constructor

    /// <summary>
    /// Verify that the constructor throws when innerAgent is null.
    /// </summary>
    [Fact]
    public void Constructor_NullInnerAgent_Throws()
    {
        // Arrange
        var evaluator = While(static _ => false);

        // Act & Assert
        Assert.Throws<ArgumentNullException>("innerAgent", () => new LoopAgent(null!, evaluator));
    }

    /// <summary>
    /// Verify that the constructor throws when the evaluator is null.
    /// </summary>
    [Fact]
    public void Constructor_NullEvaluator_Throws()
    {
        // Arrange
        var innerAgent = new Mock<AIAgent>().Object;

        // Act & Assert
        Assert.Throws<ArgumentNullException>("evaluator", () => new LoopAgent(innerAgent, (LoopEvaluator)null!));
    }

    /// <summary>
    /// Verify that the constructor throws when the evaluators collection is null.
    /// </summary>
    [Fact]
    public void Constructor_NullEvaluators_Throws()
    {
        // Arrange
        var innerAgent = new Mock<AIAgent>().Object;

        // Act & Assert
        Assert.Throws<ArgumentNullException>("evaluators", () => new LoopAgent(innerAgent, (IEnumerable<LoopEvaluator>)null!));
    }

    /// <summary>
    /// Verify that the constructor throws when the evaluators collection is empty.
    /// </summary>
    [Fact]
    public void Constructor_EmptyEvaluators_Throws()
    {
        // Arrange
        var innerAgent = new Mock<AIAgent>().Object;

        // Act & Assert
        Assert.Throws<ArgumentException>("evaluators", () => new LoopAgent(innerAgent, Array.Empty<LoopEvaluator>()));
    }

    /// <summary>
    /// Verify that the constructor throws when the evaluators collection contains a null element.
    /// </summary>
    [Fact]
    public void Constructor_NullEvaluatorElement_Throws()
    {
        // Arrange
        var innerAgent = new Mock<AIAgent>().Object;

        // Act & Assert
        Assert.Throws<ArgumentNullException>("evaluators", () => new LoopAgent(innerAgent, new LoopEvaluator[] { null! }));
    }

    /// <summary>
    /// Verify that the constructor throws when MaxIterations is less than 1.
    /// </summary>
    [Fact]
    public void Constructor_InvalidMaxIterations_Throws()
    {
        // Arrange
        var innerAgent = new Mock<AIAgent>().Object;
        var evaluator = While(static _ => false);
        var options = new LoopAgentOptions { MaxIterations = 0 };

        // Act & Assert
        Assert.Throws<ArgumentOutOfRangeException>(() => new LoopAgent(innerAgent, evaluator, options));
    }

    /// <summary>
    /// Verify that the constructor creates a valid instance with default options.
    /// </summary>
    [Fact]
    public void Constructor_ValidArguments_CreatesInstance()
    {
        // Arrange
        var innerAgent = new Mock<AIAgent>().Object;
        var evaluator = While(static _ => false);

        // Act
        var agent = new LoopAgent(innerAgent, evaluator);

        // Assert
        Assert.NotNull(agent);
    }

    #endregion

    #region RunAsync - core loop behavior

    /// <summary>
    /// Verify that when the evaluator stops immediately the inner agent is invoked exactly once.
    /// </summary>
    [Fact]
    public async Task RunAsync_EvaluatorStopsImmediately_InvokesOnceAsync()
    {
        // Arrange
        var capture = new InnerAgentCapture(_ => new AgentResponse([new ChatMessage(ChatRole.Assistant, "done")]));
        var evaluator = While(static _ => false);
        var agent = new LoopAgent(capture.Agent, evaluator);

        // Act
        var response = await agent.RunAsync([new ChatMessage(ChatRole.User, "go")], new ChatClientAgentSession());

        // Assert
        Assert.Equal("done", response.Text);
        Assert.Equal(1, capture.CallCount);
    }

    /// <summary>
    /// Verify that the loop re-invokes while the predicate returns true and the aggregated response contains every
    /// iteration's messages in order.
    /// </summary>
    [Fact]
    public async Task RunAsync_PredicateLoopsUntilFalse_AggregatesAllIterationsAsync()
    {
        // Arrange
        var capture = new InnerAgentCapture(call =>
            new AgentResponse([new ChatMessage(ChatRole.Assistant, $"iteration {call}")]));

        // Continue while the latest response is not "iteration 3".
        var evaluator = While(ctx => ctx.LastResponse.Text != "iteration 3");
        var agent = new LoopAgent(capture.Agent, evaluator);

        // Act
        var response = await agent.RunAsync([new ChatMessage(ChatRole.User, "go")], new ChatClientAgentSession());

        // Assert
        Assert.Equal(3, capture.CallCount);
        Assert.Equal(["iteration 1", "iteration 2", "iteration 3"], response.Messages.Select(static m => m.Text));
    }

    /// <summary>
    /// Verify that <see cref="LoopAgentOptions.NonStreamingReturnsLastResponseOnly"/> returns only the final
    /// iteration's response instead of the aggregated transcript.
    /// </summary>
    [Fact]
    public async Task RunAsync_LastResponseOnly_ReturnsFinalResponseAsync()
    {
        // Arrange
        var capture = new InnerAgentCapture(call =>
            new AgentResponse([new ChatMessage(ChatRole.Assistant, $"iteration {call}")]));
        var evaluator = While(ctx => ctx.LastResponse.Text != "iteration 3");
        var options = new LoopAgentOptions { NonStreamingReturnsLastResponseOnly = true };
        var agent = new LoopAgent(capture.Agent, evaluator, options);

        // Act
        var response = await agent.RunAsync([new ChatMessage(ChatRole.User, "go")], new ChatClientAgentSession());

        // Assert
        Assert.Equal(3, capture.CallCount);
        Assert.Equal("iteration 3", response.Text);
        Assert.Single(response.Messages);
    }

    /// <summary>
    /// Verify that the caller's initial messages are sent once and a re-invocation without feedback sends none.
    /// </summary>
    [Fact]
    public async Task RunAsync_ContinueWithoutFeedback_SendsInitialOnceThenNoneAsync()
    {
        // Arrange
        var capture = new InnerAgentCapture(_ => new AgentResponse([new ChatMessage(ChatRole.Assistant, "ack")]));
        var evaluator = new DelegateLoopEvaluator((ctx, _) =>
            new ValueTask<LoopEvaluation>(
                ctx.Iteration < 2 ? LoopEvaluation.Continue() : LoopEvaluation.Stop()));
        var agent = new LoopAgent(capture.Agent, evaluator);

        // Act
        await agent.RunAsync([new ChatMessage(ChatRole.User, "original")], new ChatClientAgentSession());

        // Assert
        Assert.Equal(2, capture.CallCount);
        Assert.Equal("original", capture.MessagesPerCall[0].Single().Text);
        Assert.Empty(capture.MessagesPerCall[1]);
    }

    /// <summary>
    /// Verify that feedback supplied by the evaluator is injected verbatim on re-invocation (non-fresh mode).
    /// </summary>
    [Fact]
    public async Task RunAsync_EvaluatorSuppliesFeedback_InjectsItVerbatimAsync()
    {
        // Arrange
        var capture = new InnerAgentCapture(_ => new AgentResponse([new ChatMessage(ChatRole.Assistant, "ack")]));
        var evaluator = new DelegateLoopEvaluator((ctx, _) =>
            new ValueTask<LoopEvaluation>(
                ctx.Iteration < 2 ? LoopEvaluation.Continue("custom follow-up") : LoopEvaluation.Stop()));
        var agent = new LoopAgent(capture.Agent, evaluator);

        // Act
        await agent.RunAsync([new ChatMessage(ChatRole.User, "original")], new ChatClientAgentSession());

        // Assert
        Assert.Equal(2, capture.CallCount);
        Assert.Equal("custom follow-up", capture.MessagesPerCall[1].Single().Text);
    }

    /// <summary>
    /// Verify that an evaluator using <see cref="LoopEvaluation.ContinueWithMessages"/> sends the messages verbatim and
    /// records an aligned <see langword="null"/> feedback entry (it carries no feedback string).
    /// </summary>
    [Fact]
    public async Task RunAsync_ContinueWithMessages_SendsMessagesVerbatimAndRecordsNullFeedbackAsync()
    {
        // Arrange
        var capture = new InnerAgentCapture(_ => new AgentResponse([new ChatMessage(ChatRole.Assistant, "ack")]));
        IReadOnlyList<string?>? feedbackSnapshot = null;
        var evaluator = new DelegateLoopEvaluator((ctx, _) =>
        {
            if (ctx.Iteration < 2)
            {
                return new ValueTask<LoopEvaluation>(LoopEvaluation.ContinueWithMessages(
                    [new ChatMessage(ChatRole.System, "sys"), new ChatMessage(ChatRole.User, "explicit")]));
            }

            feedbackSnapshot = ctx.Feedback.ToList();
            return new ValueTask<LoopEvaluation>(LoopEvaluation.Stop());
        });
        var agent = new LoopAgent(capture.Agent, evaluator);

        // Act
        await agent.RunAsync([new ChatMessage(ChatRole.User, "original")], new ChatClientAgentSession());

        // Assert
        Assert.Equal(2, capture.CallCount);
        Assert.Equal(["sys", "explicit"], capture.MessagesPerCall[1].Select(static m => m.Text));
        Assert.NotNull(feedbackSnapshot);
        // One aligned entry for the single re-invoked iteration; null because ContinueWithMessages carries no feedback string.
        Assert.Equal([null], feedbackSnapshot!);
    }

    /// <summary>
    /// Verify that the global safety cap stops the loop even when the evaluator always continues.
    /// </summary>
    [Fact]
    public async Task RunAsync_AlwaysContinue_StopsAtGlobalCapAsync()
    {
        // Arrange
        var capture = new InnerAgentCapture(_ => new AgentResponse([new ChatMessage(ChatRole.Assistant, "working")]));
        var evaluator = While(static _ => true);
        var options = new LoopAgentOptions { MaxIterations = 3 };
        var agent = new LoopAgent(capture.Agent, evaluator, options);

        // Act
        var response = await agent.RunAsync([new ChatMessage(ChatRole.User, "go")], new ChatClientAgentSession());

        // Assert
        Assert.Equal(3, capture.CallCount);
        Assert.Equal(["working", "working", "working"], response.Messages.Select(static m => m.Text));
    }

    /// <summary>
    /// Verify that a pending tool-approval request terminates the loop and returns that response.
    /// </summary>
    [Fact]
    public async Task RunAsync_PendingApprovalRequest_StopsLoopAsync()
    {
        // Arrange
        var approvalRequest = new ToolApprovalRequestContent("req1", new FunctionCallContent("call1", "MyTool"));
        var capture = new InnerAgentCapture(_ => new AgentResponse([new ChatMessage(ChatRole.Assistant, [approvalRequest])]));
        var evaluator = While(static _ => true);
        var agent = new LoopAgent(capture.Agent, evaluator);

        // Act
        var response = await agent.RunAsync([new ChatMessage(ChatRole.User, "go")], new ChatClientAgentSession());

        // Assert
        Assert.Equal(1, capture.CallCount);
        Assert.Contains(response.Messages.SelectMany(static m => m.Contents), static c => c is ToolApprovalRequestContent);
    }

    /// <summary>
    /// Verify that when no session is supplied the loop creates one and invokes the agent.
    /// </summary>
    [Fact]
    public async Task RunAsync_NoSessionSupplied_CreatesSessionAsync()
    {
        // Arrange
        var capture = new InnerAgentCapture(_ => new AgentResponse([new ChatMessage(ChatRole.Assistant, "done")]));
        capture.Mock
            .Protected()
            .Setup<ValueTask<AgentSession>>("CreateSessionCoreAsync", ItExpr.IsAny<CancellationToken>())
            .Returns(new ValueTask<AgentSession>(new ChatClientAgentSession()));
        var evaluator = While(static _ => false);
        var agent = new LoopAgent(capture.Agent, evaluator);

        // Act
        var response = await agent.RunAsync([new ChatMessage(ChatRole.User, "go")]);

        // Assert
        Assert.Equal("done", response.Text);
        capture.Mock.Protected().Verify("CreateSessionCoreAsync", Times.Once(), ItExpr.IsAny<CancellationToken>());
    }

    #endregion

    #region RunAsync - feedback log

    /// <summary>
    /// Verify that in the default (non-fresh) mode the latest feedback is injected verbatim as the next input.
    /// </summary>
    [Fact]
    public async Task RunAsync_NonFresh_InjectsLatestFeedbackVerbatimAsync()
    {
        // Arrange
        var capture = new InnerAgentCapture(_ => new AgentResponse([new ChatMessage(ChatRole.Assistant, "partial")]));
        var evaluator = new DelegateLoopEvaluator((_, _) => new ValueTask<LoopEvaluation>(LoopEvaluation.Continue("fix it")));
        var options = new LoopAgentOptions { MaxIterations = 2 };
        var agent = new LoopAgent(capture.Agent, evaluator, options);

        // Act
        await agent.RunAsync([new ChatMessage(ChatRole.User, "original")], new ChatClientAgentSession());

        // Assert
        Assert.Equal(2, capture.CallCount);
        Assert.Equal("fix it", capture.MessagesPerCall[1].Single().Text);
    }

    /// <summary>
    /// Verify that when the latest iteration produces no feedback, no stale earlier feedback is re-injected (non-fresh).
    /// </summary>
    [Fact]
    public async Task RunAsync_NonFresh_LatestEmpty_DoesNotReinjectStaleFeedbackAsync()
    {
        // Arrange
        var capture = new InnerAgentCapture(_ => new AgentResponse([new ChatMessage(ChatRole.Assistant, "partial")]));

        // Provide feedback only on the first iteration; the second records nothing.
        var evaluator = new DelegateLoopEvaluator((ctx, _) =>
            new ValueTask<LoopEvaluation>(LoopEvaluation.Continue(ctx.Iteration == 1 ? "feedback 1" : null)));
        var options = new LoopAgentOptions { MaxIterations = 3 };
        var agent = new LoopAgent(capture.Agent, evaluator, options);

        // Act
        await agent.RunAsync([new ChatMessage(ChatRole.User, "original")], new ChatClientAgentSession());

        // Assert
        Assert.Equal(3, capture.CallCount);
        Assert.Equal("feedback 1", capture.MessagesPerCall[1].Single().Text);
        Assert.Empty(capture.MessagesPerCall[2]);
    }

    /// <summary>
    /// Verify that the accumulated feedback log is exposed read-only and shared across all evaluators in a run.
    /// </summary>
    [Fact]
    public async Task RunAsync_FeedbackLog_IsSharedAcrossEvaluatorsAsync()
    {
        // Arrange
        var capture = new InnerAgentCapture(_ => new AgentResponse([new ChatMessage(ChatRole.Assistant, "partial")]));
        var observed = new List<int>();
        var producer = new DelegateLoopEvaluator((ctx, _) =>
            new ValueTask<LoopEvaluation>(
                ctx.Iteration < 3 ? LoopEvaluation.Continue($"fb {ctx.Iteration}") : LoopEvaluation.Stop()));
        var observer = new DelegateLoopEvaluator((ctx, _) =>
        {
            // The observer runs only when the producer stops; it sees the full feedback log.
            observed.Add(ctx.Feedback.Count);
            return new ValueTask<LoopEvaluation>(LoopEvaluation.Stop());
        });
        var options = new LoopAgentOptions { MaxIterations = 5 };
        var agent = new LoopAgent(capture.Agent, new LoopEvaluator[] { producer, observer }, options);

        // Act
        await agent.RunAsync([new ChatMessage(ChatRole.User, "go")], new ChatClientAgentSession());

        // Assert
        Assert.Equal(3, capture.CallCount);
        // On the third iteration the producer stops, the observer runs and sees two recorded feedback entries.
        Assert.Equal([2], observed);
    }

    /// <summary>
    /// Verify that iterations driven by <see cref="LoopEvaluation.ContinueWithMessages"/> still record an (aligned)
    /// entry in the feedback log, so the log stays one-entry-per-re-invoked-iteration. The explicit-messages iteration
    /// contributes a <see langword="null"/> entry since it carries no feedback string.
    /// </summary>
    [Fact]
    public async Task RunAsync_ContinueWithMessages_RecordsNullFeedbackEntryAsync()
    {
        // Arrange
        var capture = new InnerAgentCapture(_ => new AgentResponse([new ChatMessage(ChatRole.Assistant, "partial")]));
        List<string?>? finalLog = null;
        var evaluator = new DelegateLoopEvaluator((ctx, _) =>
        {
            // Capture the log on the final evaluation, after both re-invocations have been recorded.
            if (ctx.Iteration >= 3)
            {
                finalLog = ctx.Feedback.ToList();
                return new ValueTask<LoopEvaluation>(LoopEvaluation.Stop());
            }

            // Iteration 1 drives a feedback-string re-invocation; iteration 2 drives an explicit-messages one.
            return new ValueTask<LoopEvaluation>(ctx.Iteration == 1
                ? LoopEvaluation.Continue("needs work")
                : LoopEvaluation.ContinueWithMessages([new ChatMessage(ChatRole.User, "explicit")]));
        });
        var options = new LoopAgentOptions { MaxIterations = 5 };
        var agent = new LoopAgent(capture.Agent, evaluator, options);

        // Act
        await agent.RunAsync([new ChatMessage(ChatRole.User, "go")], new ChatClientAgentSession());

        // Assert
        Assert.NotNull(finalLog);
        // One entry per re-invoked iteration: the feedback string, then null for the ContinueWithMessages iteration.
        Assert.Equal(["needs work", null], finalLog!);
    }

    #endregion

    #region RunAsync - fresh context

    /// <summary>
    /// Verify that without fresh context the loop reuses a single session across all iterations.
    /// </summary>
    [Fact]
    public async Task RunAsync_NonFresh_ReusesSameSessionAcrossIterationsAsync()
    {
        // Arrange
        var loopSession = new ChatClientAgentSession();
        var capture = new InnerAgentCapture(_ => new AgentResponse([new ChatMessage(ChatRole.Assistant, "x")]));
        capture.Mock
            .Protected()
            .Setup<ValueTask<AgentSession>>("CreateSessionCoreAsync", ItExpr.IsAny<CancellationToken>())
            .Returns(new ValueTask<AgentSession>(loopSession));
        var evaluator = new DelegateLoopEvaluator((_, _) => new ValueTask<LoopEvaluation>(LoopEvaluation.Continue("more")));
        var options = new LoopAgentOptions { MaxIterations = 3 };
        var agent = new LoopAgent(capture.Agent, evaluator, options);

        // Act (no session supplied by caller)
        await agent.RunAsync([new ChatMessage(ChatRole.User, "go")]);

        // Assert
        Assert.Equal(3, capture.CallCount);
        Assert.Same(loopSession, capture.SessionsPerCall[0]);
        Assert.Same(loopSession, capture.SessionsPerCall[1]);
        Assert.Same(loopSession, capture.SessionsPerCall[2]);
    }

    /// <summary>
    /// Verify that with fresh context each iteration is rebuilt from the original messages plus the aggregated feedback log.
    /// </summary>
    [Fact]
    public async Task RunAsync_Fresh_RebuildsFromInitialMessagesAndAggregatedFeedbackAsync()
    {
        // Arrange
        var capture = new InnerAgentCapture(_ => new AgentResponse([new ChatMessage(ChatRole.Assistant, "partial")]));
        capture.Mock
            .Protected()
            .Setup<ValueTask<AgentSession>>("CreateSessionCoreAsync", ItExpr.IsAny<CancellationToken>())
            .Returns(() => new ValueTask<AgentSession>(new ChatClientAgentSession()));
        var evaluator = new DelegateLoopEvaluator((ctx, _) => new ValueTask<LoopEvaluation>(LoopEvaluation.Continue($"fb {ctx.Iteration}")));
        var options = new LoopAgentOptions { MaxIterations = 3, FreshContextPerIteration = true };
        var agent = new LoopAgent(capture.Agent, evaluator, options);

        // Act (no session supplied by caller)
        await agent.RunAsync([new ChatMessage(ChatRole.User, "original task")]);

        // Assert
        Assert.Equal(3, capture.CallCount);
        var secondCall = capture.MessagesPerCall[1];
        Assert.Contains(secondCall, static m => m.Text == "original task");
        Assert.Contains(secondCall, static m => m.Text.Contains("## Feedback") && m.Text.Contains("fb 1"));
        var thirdCall = capture.MessagesPerCall[2];
        Assert.Contains(thirdCall, static m => m.Text == "original task");
        Assert.Contains(thirdCall, static m => m.Text.Contains("fb 1") && m.Text.Contains("fb 2"));
    }

    /// <summary>
    /// Verify that with fresh context and a loop-owned session, a new session is created for each iteration.
    /// </summary>
    [Fact]
    public async Task RunAsync_Fresh_RecreatesSessionEachIterationAsync()
    {
        // Arrange
        var capture = new InnerAgentCapture(_ => new AgentResponse([new ChatMessage(ChatRole.Assistant, "x")]));
        capture.Mock
            .Protected()
            .Setup<ValueTask<AgentSession>>("CreateSessionCoreAsync", ItExpr.IsAny<CancellationToken>())
            .Returns(() => new ValueTask<AgentSession>(new ChatClientAgentSession()));
        var evaluator = new DelegateLoopEvaluator((_, _) => new ValueTask<LoopEvaluation>(LoopEvaluation.Continue("more")));
        var options = new LoopAgentOptions { MaxIterations = 3, FreshContextPerIteration = true };
        var agent = new LoopAgent(capture.Agent, evaluator, options);

        // Act (no session supplied by caller)
        await agent.RunAsync([new ChatMessage(ChatRole.User, "go")]);

        // Assert
        Assert.Equal(3, capture.CallCount);
        Assert.NotSame(capture.SessionsPerCall[0], capture.SessionsPerCall[1]);
        Assert.NotSame(capture.SessionsPerCall[1], capture.SessionsPerCall[2]);
    }

    /// <summary>
    /// Verify that with fresh context and a caller-supplied session, the caller's session is used for the first
    /// iteration, then each re-invocation runs against a fresh clone restored from a snapshot taken at the start of
    /// the run. The session is serialized once and deserialized once per re-invocation.
    /// </summary>
    [Fact]
    public async Task RunAsync_Fresh_WithCallerSession_ClonesFromSerializedSnapshotAsync()
    {
        // Arrange
        var callerSession = new ChatClientAgentSession();
        var capture = new InnerAgentCapture(_ => new AgentResponse([new ChatMessage(ChatRole.Assistant, "x")]));
        using var snapshotDoc = JsonDocument.Parse("{}");
        JsonElement snapshot = snapshotDoc.RootElement;

        int serializeCount = 0;
        capture.Mock
            .Protected()
            .Setup<ValueTask<JsonElement>>("SerializeSessionCoreAsync", ItExpr.IsAny<AgentSession>(), ItExpr.IsAny<JsonSerializerOptions?>(), ItExpr.IsAny<CancellationToken>())
            .Returns(() => { serializeCount++; return new ValueTask<JsonElement>(snapshot); });

        int deserializeCount = 0;
        capture.Mock
            .Protected()
            .Setup<ValueTask<AgentSession>>("DeserializeSessionCoreAsync", ItExpr.IsAny<JsonElement>(), ItExpr.IsAny<JsonSerializerOptions?>(), ItExpr.IsAny<CancellationToken>())
            .Returns(() => { deserializeCount++; return new ValueTask<AgentSession>(new ChatClientAgentSession()); });

        var evaluator = new DelegateLoopEvaluator((_, _) => new ValueTask<LoopEvaluation>(LoopEvaluation.Continue("more")));
        var options = new LoopAgentOptions { MaxIterations = 3, FreshContextPerIteration = true };
        var agent = new LoopAgent(capture.Agent, evaluator, options);

        // Act
        await agent.RunAsync([new ChatMessage(ChatRole.User, "go")], callerSession);

        // Assert
        Assert.Equal(3, capture.CallCount);

        // The pristine session is snapshotted exactly once, before the first iteration mutates it.
        Assert.Equal(1, serializeCount);

        // Re-invocations (iterations 2 and 3) each restore a fresh clone from the snapshot.
        Assert.Equal(2, deserializeCount);

        // The first iteration runs against the caller's supplied session; later iterations use distinct clones.
        Assert.Same(callerSession, capture.SessionsPerCall[0]);
        Assert.NotSame(callerSession, capture.SessionsPerCall[1]);
        Assert.NotSame(callerSession, capture.SessionsPerCall[2]);
        Assert.NotSame(capture.SessionsPerCall[1], capture.SessionsPerCall[2]);

        // The loop never creates a new session for a caller-supplied one; it clones instead.
        capture.Mock.Protected().Verify("CreateSessionCoreAsync", Times.Never(), ItExpr.IsAny<CancellationToken>());
    }

    /// <summary>
    /// Verify that with fresh context and a loop-owned session, the session is reset for each iteration even when the
    /// evaluator drives re-invocation via <see cref="LoopEvaluation.ContinueWithMessages"/>: the explicit messages are
    /// still sent verbatim, but each iteration runs against a new session.
    /// </summary>
    [Fact]
    public async Task RunAsync_Fresh_WithContinueWithMessages_RecreatesSessionAsync()
    {
        // Arrange
        var capture = new InnerAgentCapture(_ => new AgentResponse([new ChatMessage(ChatRole.Assistant, "x")]));
        capture.Mock
            .Protected()
            .Setup<ValueTask<AgentSession>>("CreateSessionCoreAsync", ItExpr.IsAny<CancellationToken>())
            .Returns(() => new ValueTask<AgentSession>(new ChatClientAgentSession()));
        var evaluator = new DelegateLoopEvaluator((_, _) =>
            new ValueTask<LoopEvaluation>(LoopEvaluation.ContinueWithMessages([new ChatMessage(ChatRole.User, "explicit")])));
        var options = new LoopAgentOptions { MaxIterations = 3, FreshContextPerIteration = true };
        var agent = new LoopAgent(capture.Agent, evaluator, options);

        // Act (no session supplied by caller)
        await agent.RunAsync([new ChatMessage(ChatRole.User, "go")]);

        // Assert
        Assert.Equal(3, capture.CallCount);

        // The explicit messages are sent verbatim on each re-invocation.
        Assert.Equal(["explicit"], capture.MessagesPerCall[1].Select(static m => m.Text));
        Assert.Equal(["explicit"], capture.MessagesPerCall[2].Select(static m => m.Text));

        // The session is still reset for each iteration despite using ContinueWithMessages.
        Assert.NotSame(capture.SessionsPerCall[0], capture.SessionsPerCall[1]);
        Assert.NotSame(capture.SessionsPerCall[1], capture.SessionsPerCall[2]);
    }

    /// <summary>
    /// Verify that with fresh context and a caller-supplied session, the session is cloned from the start-of-run
    /// snapshot for each re-invocation even when the evaluator drives re-invocation via
    /// <see cref="LoopEvaluation.ContinueWithMessages"/>.
    /// </summary>
    [Fact]
    public async Task RunAsync_Fresh_WithCallerSession_AndContinueWithMessages_ClonesFromSnapshotAsync()
    {
        // Arrange
        var callerSession = new ChatClientAgentSession();
        var capture = new InnerAgentCapture(_ => new AgentResponse([new ChatMessage(ChatRole.Assistant, "x")]));
        using var snapshotDoc = JsonDocument.Parse("{}");
        JsonElement snapshot = snapshotDoc.RootElement;

        int serializeCount = 0;
        capture.Mock
            .Protected()
            .Setup<ValueTask<JsonElement>>("SerializeSessionCoreAsync", ItExpr.IsAny<AgentSession>(), ItExpr.IsAny<JsonSerializerOptions?>(), ItExpr.IsAny<CancellationToken>())
            .Returns(() => { serializeCount++; return new ValueTask<JsonElement>(snapshot); });

        int deserializeCount = 0;
        capture.Mock
            .Protected()
            .Setup<ValueTask<AgentSession>>("DeserializeSessionCoreAsync", ItExpr.IsAny<JsonElement>(), ItExpr.IsAny<JsonSerializerOptions?>(), ItExpr.IsAny<CancellationToken>())
            .Returns(() => { deserializeCount++; return new ValueTask<AgentSession>(new ChatClientAgentSession()); });

        var evaluator = new DelegateLoopEvaluator((_, _) =>
            new ValueTask<LoopEvaluation>(LoopEvaluation.ContinueWithMessages([new ChatMessage(ChatRole.User, "explicit")])));
        var options = new LoopAgentOptions { MaxIterations = 3, FreshContextPerIteration = true };
        var agent = new LoopAgent(capture.Agent, evaluator, options);

        // Act
        await agent.RunAsync([new ChatMessage(ChatRole.User, "go")], callerSession);

        // Assert
        Assert.Equal(3, capture.CallCount);
        Assert.Equal(1, serializeCount);
        Assert.Equal(2, deserializeCount);

        // First iteration uses the caller session; later iterations use distinct clones from the snapshot.
        Assert.Same(callerSession, capture.SessionsPerCall[0]);
        Assert.NotSame(callerSession, capture.SessionsPerCall[1]);
        Assert.NotSame(capture.SessionsPerCall[1], capture.SessionsPerCall[2]);
        capture.Mock.Protected().Verify("CreateSessionCoreAsync", Times.Never(), ItExpr.IsAny<CancellationToken>());
    }

    /// <summary>
    /// Verify that the configured <see cref="LoopAgentOptions.SessionCreatedCallback"/> is invoked with the loop-owned
    /// session the loop creates when the caller does not supply one, even without fresh context.
    /// </summary>
    [Fact]
    public async Task RunAsync_SessionCreatedCallback_NotifiesLoopOwnedSessionAsync()
    {
        // Arrange
        var created = new ChatClientAgentSession();
        var capture = new InnerAgentCapture(_ => new AgentResponse([new ChatMessage(ChatRole.Assistant, "x")]));
        capture.Mock
            .Protected()
            .Setup<ValueTask<AgentSession>>("CreateSessionCoreAsync", ItExpr.IsAny<CancellationToken>())
            .Returns(() => new ValueTask<AgentSession>(created));
        var observed = new List<AgentSession>();
        var options = new LoopAgentOptions
        {
            SessionCreatedCallback = (s, _) => { observed.Add(s); return default; },
        };
        var agent = new LoopAgent(capture.Agent, While(static _ => false), options);

        // Act (no session supplied by caller)
        await agent.RunAsync([new ChatMessage(ChatRole.User, "go")]);

        // Assert
        Assert.Equal(1, capture.CallCount);
        Assert.Same(created, Assert.Single(observed));
        Assert.Same(created, capture.SessionsPerCall[0]);
    }

    /// <summary>
    /// Verify that the <see cref="LoopAgentOptions.SessionCreatedCallback"/> is not invoked when the caller supplies a
    /// session and no fresh context is requested (no new session is created).
    /// </summary>
    [Fact]
    public async Task RunAsync_SessionCreatedCallback_NotInvokedForCallerSessionAsync()
    {
        // Arrange
        var callerSession = new ChatClientAgentSession();
        var capture = new InnerAgentCapture(_ => new AgentResponse([new ChatMessage(ChatRole.Assistant, "x")]));
        var observed = new List<AgentSession>();
        var options = new LoopAgentOptions
        {
            MaxIterations = 3,
            SessionCreatedCallback = (s, _) => { observed.Add(s); return default; },
        };
        var evaluator = new DelegateLoopEvaluator((_, _) => new ValueTask<LoopEvaluation>(LoopEvaluation.Continue("more")));
        var agent = new LoopAgent(capture.Agent, evaluator, options);

        // Act
        await agent.RunAsync([new ChatMessage(ChatRole.User, "go")], callerSession);

        // Assert
        Assert.Equal(3, capture.CallCount);
        Assert.Empty(observed);
    }

    /// <summary>
    /// Verify that with fresh context and a loop-owned session, the <see cref="LoopAgentOptions.SessionCreatedCallback"/>
    /// is invoked for the initial session and for each session created for a re-invocation, in order.
    /// </summary>
    [Fact]
    public async Task RunAsync_Fresh_SessionCreatedCallback_NotifiesEachCreatedSessionAsync()
    {
        // Arrange
        var capture = new InnerAgentCapture(_ => new AgentResponse([new ChatMessage(ChatRole.Assistant, "x")]));
        capture.Mock
            .Protected()
            .Setup<ValueTask<AgentSession>>("CreateSessionCoreAsync", ItExpr.IsAny<CancellationToken>())
            .Returns(() => new ValueTask<AgentSession>(new ChatClientAgentSession()));
        var observed = new List<AgentSession>();
        var options = new LoopAgentOptions
        {
            MaxIterations = 3,
            FreshContextPerIteration = true,
            SessionCreatedCallback = (s, _) => { observed.Add(s); return default; },
        };
        var evaluator = new DelegateLoopEvaluator((_, _) => new ValueTask<LoopEvaluation>(LoopEvaluation.Continue("more")));
        var agent = new LoopAgent(capture.Agent, evaluator, options);

        // Act (no session supplied by caller)
        await agent.RunAsync([new ChatMessage(ChatRole.User, "go")]);

        // Assert: one notification for the initial session plus one per re-invocation (iterations 2 and 3).
        Assert.Equal(3, capture.CallCount);
        Assert.Equal(3, observed.Count);
        Assert.Equal<AgentSession?>(capture.SessionsPerCall, observed);
    }

    /// <summary>
    /// Verify that with fresh context and a caller-supplied session, the
    /// <see cref="LoopAgentOptions.SessionCreatedCallback"/> is invoked only for the cloned sessions created for
    /// re-invocations, not for the caller's own session.
    /// </summary>
    [Fact]
    public async Task RunAsync_Fresh_WithCallerSession_SessionCreatedCallback_NotifiesClonesOnlyAsync()
    {
        // Arrange
        var callerSession = new ChatClientAgentSession();
        var capture = new InnerAgentCapture(_ => new AgentResponse([new ChatMessage(ChatRole.Assistant, "x")]));
        using var snapshotDoc = JsonDocument.Parse("{}");
        JsonElement snapshot = snapshotDoc.RootElement;
        capture.Mock
            .Protected()
            .Setup<ValueTask<JsonElement>>("SerializeSessionCoreAsync", ItExpr.IsAny<AgentSession>(), ItExpr.IsAny<JsonSerializerOptions?>(), ItExpr.IsAny<CancellationToken>())
            .Returns(() => new ValueTask<JsonElement>(snapshot));
        capture.Mock
            .Protected()
            .Setup<ValueTask<AgentSession>>("DeserializeSessionCoreAsync", ItExpr.IsAny<JsonElement>(), ItExpr.IsAny<JsonSerializerOptions?>(), ItExpr.IsAny<CancellationToken>())
            .Returns(() => new ValueTask<AgentSession>(new ChatClientAgentSession()));
        var observed = new List<AgentSession>();
        var options = new LoopAgentOptions
        {
            MaxIterations = 3,
            FreshContextPerIteration = true,
            SessionCreatedCallback = (s, _) => { observed.Add(s); return default; },
        };
        var evaluator = new DelegateLoopEvaluator((_, _) => new ValueTask<LoopEvaluation>(LoopEvaluation.Continue("more")));
        var agent = new LoopAgent(capture.Agent, evaluator, options);

        // Act
        await agent.RunAsync([new ChatMessage(ChatRole.User, "go")], callerSession);

        // Assert: the caller session is never reported; only the two clones used for re-invocations are.
        Assert.Equal(3, capture.CallCount);
        Assert.DoesNotContain(callerSession, observed);
        Assert.Equal([capture.SessionsPerCall[1]!, capture.SessionsPerCall[2]!], observed);
    }
    [Fact]
    public async Task RunAsync_MultipleEvaluators_FirstReinvokeWinsAndShortCircuitsAsync()
    {
        // Arrange
        var capture = new InnerAgentCapture(_ => new AgentResponse([new ChatMessage(ChatRole.Assistant, "ack")]));

        var firstEvaluated = 0;
        var secondEvaluated = 0;
        var first = new DelegateLoopEvaluator((ctx, _) =>
        {
            firstEvaluated++;
            return new ValueTask<LoopEvaluation>(
                ctx.Iteration < 2 ? LoopEvaluation.Continue("from first") : LoopEvaluation.Stop());
        });
        var second = new DelegateLoopEvaluator((_, _) =>
        {
            secondEvaluated++;
            return new ValueTask<LoopEvaluation>(LoopEvaluation.Stop());
        });
        var agent = new LoopAgent(capture.Agent, new LoopEvaluator[] { first, second });

        // Act
        await agent.RunAsync([new ChatMessage(ChatRole.User, "go")], new ChatClientAgentSession());

        // Assert
        Assert.Equal(2, capture.CallCount);
        Assert.Equal("from first", capture.MessagesPerCall[1].Single().Text);
        Assert.Equal(2, firstEvaluated);
        // The second evaluator is only evaluated on the iteration where the first one stops.
        Assert.Equal(1, secondEvaluated);
    }

    /// <summary>
    /// Verify that a later evaluator can cause re-invocation when an earlier evaluator asks to stop, confirming that
    /// <see cref="LoopEvaluation.Stop"/> is not a veto.
    /// </summary>
    [Fact]
    public async Task RunAsync_MultipleEvaluators_LaterEvaluatorCanContinueAsync()
    {
        // Arrange
        var capture = new InnerAgentCapture(_ => new AgentResponse([new ChatMessage(ChatRole.Assistant, "ack")]));
        var alwaysStop = While(static _ => false);
        var continueOnce = new DelegateLoopEvaluator((ctx, _) =>
            new ValueTask<LoopEvaluation>(
                ctx.Iteration < 2 ? LoopEvaluation.Continue("from second") : LoopEvaluation.Stop()));
        var agent = new LoopAgent(capture.Agent, new LoopEvaluator[] { alwaysStop, continueOnce });

        // Act
        await agent.RunAsync([new ChatMessage(ChatRole.User, "go")], new ChatClientAgentSession());

        // Assert
        Assert.Equal(2, capture.CallCount);
        Assert.Equal("from second", capture.MessagesPerCall[1].Single().Text);
    }

    /// <summary>
    /// Verify that the loop stops when every evaluator asks to stop.
    /// </summary>
    [Fact]
    public async Task RunAsync_MultipleEvaluators_AllStop_StopsAsync()
    {
        // Arrange
        var capture = new InnerAgentCapture(_ => new AgentResponse([new ChatMessage(ChatRole.Assistant, "done")]));
        var first = While(static _ => false);
        var second = While(static _ => false);
        var agent = new LoopAgent(capture.Agent, new LoopEvaluator[] { first, second });

        // Act
        await agent.RunAsync([new ChatMessage(ChatRole.User, "go")], new ChatClientAgentSession());

        // Assert
        Assert.Equal(1, capture.CallCount);
    }

    #endregion

    #region RunAsync - AIJudge evaluator integration

    /// <summary>
    /// Verify that an <see cref="AIJudgeLoopEvaluator"/> (non-fresh) injects its templated feedback message verbatim
    /// on re-invocation.
    /// </summary>
    [Fact]
    public async Task RunAsync_WithAIJudgeEvaluator_NonFresh_InjectsTemplatedFeedbackMessageAsync()
    {
        // Arrange
        var capture = new InnerAgentCapture(_ => new AgentResponse([new ChatMessage(ChatRole.Assistant, "partial")]));
        var judgeClient = CreateJudgeClient("{\"answered\":false,\"gapAnalysis\":\"the cost estimate is missing\"}");
        var evaluator = new AIJudgeLoopEvaluator(judgeClient);
        var options = new LoopAgentOptions { MaxIterations = 2 };
        var agent = new LoopAgent(capture.Agent, evaluator, options);
        string expected = AIJudgeLoopEvaluator.DefaultFeedbackMessageTemplate
            .Replace(AIJudgeLoopEvaluator.GapAnalysisPlaceholder, "the cost estimate is missing");

        // Act
        await agent.RunAsync([new ChatMessage(ChatRole.User, "question")], new ChatClientAgentSession());

        // Assert
        Assert.Equal(2, capture.CallCount);
        Assert.Equal(expected, capture.MessagesPerCall[1].Single().Text);
    }

    #endregion

    #region RunAsync - response shaping

    /// <summary>
    /// Verify that a non-streaming run aggregates each iteration's on-behalf-of feedback message and response messages
    /// in order, stamping the configured author name on the synthesized feedback while never echoing caller input.
    /// </summary>
    [Fact]
    public async Task RunAsync_Aggregates_OnBehalfOfFeedbackAndResponsesAsync()
    {
        // Arrange
        var capture = new InnerAgentCapture(_ => new AgentResponse([new ChatMessage(ChatRole.Assistant, "ack")]));
        var evaluator = new DelegateLoopEvaluator((ctx, _) =>
            new ValueTask<LoopEvaluation>(
                ctx.Iteration < 2 ? LoopEvaluation.Continue("fix it") : LoopEvaluation.Stop()));
        var options = new LoopAgentOptions { OnBehalfOfAuthorName = "loop" };
        var agent = new LoopAgent(capture.Agent, evaluator, options);

        // Act
        var response = await agent.RunAsync([new ChatMessage(ChatRole.User, "original")], new ChatClientAgentSession());

        // Assert
        Assert.Equal(["ack", "fix it", "ack"], response.Messages.Select(static m => m.Text));
        ChatMessage feedbackMessage = response.Messages[1];
        Assert.Equal(ChatRole.User, feedbackMessage.Role);
        Assert.Equal("loop", feedbackMessage.AuthorName);

        // The on-behalf-of author name is also stamped on the message actually sent to the wrapped agent.
        Assert.Equal("loop", capture.MessagesPerCall[1].Single().AuthorName);
    }

    /// <summary>
    /// Verify that evaluator-supplied messages are surfaced verbatim and their author name is not overwritten by the
    /// loop's on-behalf-of author name.
    /// </summary>
    [Fact]
    public async Task RunAsync_ContinueWithMessages_AreSurfacedWithoutAuthorNameOverrideAsync()
    {
        // Arrange
        var capture = new InnerAgentCapture(_ => new AgentResponse([new ChatMessage(ChatRole.Assistant, "ack")]));
        var evaluator = new DelegateLoopEvaluator((ctx, _) =>
            new ValueTask<LoopEvaluation>(
                ctx.Iteration < 2
                    ? LoopEvaluation.ContinueWithMessages([new ChatMessage(ChatRole.User, "explicit") { AuthorName = "evaluator" }])
                    : LoopEvaluation.Stop()));
        var options = new LoopAgentOptions { OnBehalfOfAuthorName = "loop" };
        var agent = new LoopAgent(capture.Agent, evaluator, options);

        // Act
        var response = await agent.RunAsync([new ChatMessage(ChatRole.User, "original")], new ChatClientAgentSession());

        // Assert
        Assert.Equal(["ack", "explicit", "ack"], response.Messages.Select(static m => m.Text));
        Assert.Equal("evaluator", response.Messages[1].AuthorName);
    }

    /// <summary>
    /// Verify that in fresh-context mode only the synthesized aggregated feedback message is surfaced; the replayed
    /// caller input messages are not echoed.
    /// </summary>
    [Fact]
    public async Task RunAsync_FreshContext_SurfacesOnlyAggregatedFeedbackAsync()
    {
        // Arrange
        var capture = new InnerAgentCapture(_ => new AgentResponse([new ChatMessage(ChatRole.Assistant, "ack")]));
        capture.Mock
            .Protected()
            .Setup<ValueTask<AgentSession>>("CreateSessionCoreAsync", ItExpr.IsAny<CancellationToken>())
            .Returns(new ValueTask<AgentSession>(new ChatClientAgentSession()));
        var evaluator = new DelegateLoopEvaluator((ctx, _) =>
            new ValueTask<LoopEvaluation>(
                ctx.Iteration < 2 ? LoopEvaluation.Continue("fix it") : LoopEvaluation.Stop()));
        var options = new LoopAgentOptions { FreshContextPerIteration = true, OnBehalfOfAuthorName = "loop" };
        var agent = new LoopAgent(capture.Agent, evaluator, options);

        // Act (no caller session so the loop owns and recreates the session each iteration).
        var response = await agent.RunAsync([new ChatMessage(ChatRole.User, "original")]);

        // Assert
        Assert.Equal(3, response.Messages.Count);
        ChatMessage surfacedFeedback = response.Messages[1];
        Assert.Equal("loop", surfacedFeedback.AuthorName);
        Assert.Contains("fix it", surfacedFeedback.Text);

        // The replayed caller input ("original") is sent to the agent but is not surfaced in the response.
        Assert.DoesNotContain(response.Messages, static m => m.Text == "original");
        Assert.Equal(["original", surfacedFeedback.Text], capture.MessagesPerCall[1].Select(static m => m.Text));
    }

    /// <summary>
    /// Verify that <see cref="LoopAgentOptions.ExcludeOnBehalfOfMessages"/> omits the injected on-behalf-of messages
    /// from the aggregated non-streaming response while still sending them to the wrapped agent.
    /// </summary>
    [Fact]
    public async Task RunAsync_ExcludeOnBehalfOfMessages_OmitsThemFromResponseAsync()
    {
        // Arrange
        var capture = new InnerAgentCapture(_ => new AgentResponse([new ChatMessage(ChatRole.Assistant, "ack")]));
        var evaluator = new DelegateLoopEvaluator((ctx, _) =>
            new ValueTask<LoopEvaluation>(
                ctx.Iteration < 2 ? LoopEvaluation.Continue("fix it") : LoopEvaluation.Stop()));
        var options = new LoopAgentOptions { ExcludeOnBehalfOfMessages = true };
        var agent = new LoopAgent(capture.Agent, evaluator, options);

        // Act
        var response = await agent.RunAsync([new ChatMessage(ChatRole.User, "original")], new ChatClientAgentSession());

        // Assert
        Assert.Equal(["ack", "ack"], response.Messages.Select(static m => m.Text));

        // The feedback is still sent to the wrapped agent even though it is not surfaced.
        Assert.Equal("fix it", capture.MessagesPerCall[1].Single().Text);
    }

    #endregion

    #region RunStreamingAsync

    /// <summary>
    /// Verify that streaming surfaces updates from every iteration and stops when the evaluator stops.
    /// </summary>
    [Fact]
    public async Task RunStreamingAsync_MultipleIterations_StreamsAllUpdatesAsync()
    {
        // Arrange
        var capture = new InnerStreamingCapture(call =>
            [new AgentResponseUpdate(ChatRole.Assistant, $"chunk {call}")]);
        var evaluator = While(ctx => ctx.Iteration < 3);
        var agent = new LoopAgent(capture.Agent, evaluator);

        // Act
        var texts = new List<string>();
        await foreach (var update in agent.RunStreamingAsync([new ChatMessage(ChatRole.User, "go")], new ChatClientAgentSession()))
        {
            texts.Add(update.Text);
        }

        // Assert
        Assert.Equal(3, capture.CallCount);
        Assert.Equal(["chunk 1", "chunk 2", "chunk 3"], texts);
    }

    /// <summary>
    /// Verify that the streaming path enforces the global safety cap like the non-streaming path.
    /// </summary>
    [Fact]
    public async Task RunStreamingAsync_AlwaysContinue_StopsAtGlobalCapAsync()
    {
        // Arrange
        var capture = new InnerStreamingCapture(call => [new AgentResponseUpdate(ChatRole.Assistant, $"chunk {call}")]);
        var evaluator = While(static _ => true);
        var options = new LoopAgentOptions { MaxIterations = 4 };
        var agent = new LoopAgent(capture.Agent, evaluator, options);

        // Act
        await foreach (var _ in agent.RunStreamingAsync([new ChatMessage(ChatRole.User, "go")], new ChatClientAgentSession()))
        {
        }

        // Assert
        Assert.Equal(4, capture.CallCount);
    }

    /// <summary>
    /// Verify that the streaming path sends the initial messages once and no messages on a feedback-less re-invocation.
    /// </summary>
    [Fact]
    public async Task RunStreamingAsync_ContinueWithoutFeedback_SendsInitialOnceThenNoneAsync()
    {
        // Arrange
        var capture = new InnerStreamingCapture(_ => [new AgentResponseUpdate(ChatRole.Assistant, "ack")]);
        var evaluator = new DelegateLoopEvaluator((ctx, _) =>
            new ValueTask<LoopEvaluation>(
                ctx.Iteration < 2 ? LoopEvaluation.Continue() : LoopEvaluation.Stop()));
        var agent = new LoopAgent(capture.Agent, evaluator);

        // Act
        await foreach (var _ in agent.RunStreamingAsync([new ChatMessage(ChatRole.User, "original")], new ChatClientAgentSession()))
        {
        }

        // Assert
        Assert.Equal(2, capture.CallCount);
        Assert.Equal("original", capture.MessagesPerCall[0].Single().Text);
        Assert.Empty(capture.MessagesPerCall[1]);
    }

    /// <summary>
    /// Verify that the streaming path stops after the iteration that produces a pending approval request.
    /// </summary>
    [Fact]
    public async Task RunStreamingAsync_PendingApprovalRequest_StopsLoopAsync()
    {
        // Arrange
        var approvalRequest = new ToolApprovalRequestContent("req1", new FunctionCallContent("call1", "MyTool"));
        var capture = new InnerStreamingCapture(_ => [new AgentResponseUpdate(ChatRole.Assistant, [approvalRequest])]);
        var evaluator = While(static _ => true);
        var agent = new LoopAgent(capture.Agent, evaluator);

        // Act
        await foreach (var _ in agent.RunStreamingAsync([new ChatMessage(ChatRole.User, "go")], new ChatClientAgentSession()))
        {
        }

        // Assert
        Assert.Equal(1, capture.CallCount);
    }

    /// <summary>
    /// Verify that the streaming path emits the loop's on-behalf-of feedback as an update (with the configured author
    /// name) before streaming the re-invocation it drives.
    /// </summary>
    [Fact]
    public async Task RunStreamingAsync_SurfacesOnBehalfOfFeedbackBeforeReinvocationAsync()
    {
        // Arrange
        var capture = new InnerStreamingCapture(i =>
            [new AgentResponseUpdate(ChatRole.Assistant, "ack") { ResponseId = $"resp-{i}", AgentId = $"agent-{i}" }]);
        var evaluator = new DelegateLoopEvaluator((ctx, _) =>
            new ValueTask<LoopEvaluation>(
                ctx.Iteration < 2 ? LoopEvaluation.Continue("fix it") : LoopEvaluation.Stop()));
        var options = new LoopAgentOptions { OnBehalfOfAuthorName = "loop" };
        var agent = new LoopAgent(capture.Agent, evaluator, options);

        // Act
        var updates = new List<AgentResponseUpdate>();
        await foreach (var update in agent.RunStreamingAsync([new ChatMessage(ChatRole.User, "original")], new ChatClientAgentSession()))
        {
            updates.Add(update);
        }

        // Assert
        Assert.Equal(["ack", "fix it", "ack"], updates.Select(static u => u.Text));
        AgentResponseUpdate feedbackUpdate = updates[1];
        Assert.Equal(ChatRole.User, feedbackUpdate.Role);
        Assert.Equal("loop", feedbackUpdate.AuthorName);
        // The surfaced on-behalf-of update inherits the re-invocation iteration's ResponseId so downstream mergers
        // group it with the run it drives, and carries its own unique non-null MessageId. AgentId is left unset
        // because the message is synthesized by the loop, not produced by the wrapped agent.
        Assert.Equal("resp-2", feedbackUpdate.ResponseId);
        Assert.True(string.IsNullOrEmpty(feedbackUpdate.AgentId));
        Assert.False(string.IsNullOrEmpty(feedbackUpdate.MessageId));
    }

    /// <summary>
    /// Verify that <see cref="LoopAgentOptions.ExcludeOnBehalfOfMessages"/> omits the injected on-behalf-of updates
    /// from the streamed output while still sending the feedback to the wrapped agent.
    /// </summary>
    [Fact]
    public async Task RunStreamingAsync_ExcludeOnBehalfOfMessages_OmitsThemFromUpdatesAsync()
    {
        // Arrange
        var capture = new InnerStreamingCapture(_ => [new AgentResponseUpdate(ChatRole.Assistant, "ack")]);
        var evaluator = new DelegateLoopEvaluator((ctx, _) =>
            new ValueTask<LoopEvaluation>(
                ctx.Iteration < 2 ? LoopEvaluation.Continue("fix it") : LoopEvaluation.Stop()));
        var options = new LoopAgentOptions { ExcludeOnBehalfOfMessages = true };
        var agent = new LoopAgent(capture.Agent, evaluator, options);

        // Act
        var texts = new List<string>();
        await foreach (var update in agent.RunStreamingAsync([new ChatMessage(ChatRole.User, "original")], new ChatClientAgentSession()))
        {
            texts.Add(update.Text);
        }

        // Assert
        Assert.Equal(["ack", "ack"], texts);
        Assert.Equal("fix it", capture.MessagesPerCall[1].Single().Text);
    }

    /// <summary>
    /// Verify that a surfaced on-behalf-of streaming update is assigned a generated, unique <see cref="AgentResponseUpdate.MessageId"/>
    /// when the underlying evaluator-supplied message has none, inherits the driven iteration's ResponseId, and leaves AgentId unset.
    /// </summary>
    [Fact]
    public async Task RunStreamingAsync_ContinueWithMessages_GetsGeneratedMessageIdAndInheritsIdsAsync()
    {
        // Arrange
        var capture = new InnerStreamingCapture(i =>
            [new AgentResponseUpdate(ChatRole.Assistant, "ack") { ResponseId = $"resp-{i}", AgentId = $"agent-{i}" }]);
        var evaluator = new DelegateLoopEvaluator((ctx, _) =>
            new ValueTask<LoopEvaluation>(
                ctx.Iteration < 2
                    ? LoopEvaluation.ContinueWithMessages([new ChatMessage(ChatRole.User, "explicit") { AuthorName = "evaluator" }])
                    : LoopEvaluation.Stop()));
        var agent = new LoopAgent(capture.Agent, evaluator);

        // Act
        var updates = new List<AgentResponseUpdate>();
        await foreach (var update in agent.RunStreamingAsync([new ChatMessage(ChatRole.User, "original")], new ChatClientAgentSession()))
        {
            updates.Add(update);
        }

        // Assert
        Assert.Equal(["ack", "explicit", "ack"], updates.Select(static u => u.Text));
        AgentResponseUpdate surfaced = updates[1];
        Assert.Equal("evaluator", surfaced.AuthorName);
        Assert.False(string.IsNullOrEmpty(surfaced.MessageId));
        Assert.Equal("resp-2", surfaced.ResponseId);
        Assert.True(string.IsNullOrEmpty(surfaced.AgentId));
    }

    /// <summary>
    /// Verify that when the wrapped agent produces no updates for an iteration, the surfaced on-behalf-of update is
    /// still assigned a generated (non-null) ResponseId so it can be grouped downstream.
    /// </summary>
    [Fact]
    public async Task RunStreamingAsync_NoInnerUpdates_GeneratesResponseIdForOnBehalfOfAsync()
    {
        // Arrange (the re-invocation iteration produces no updates, so its surfaced feedback has no inner ResponseId
        // to inherit and must fall back to a generated one).
        var capture = new InnerStreamingCapture(i =>
            i < 2 ? [new AgentResponseUpdate(ChatRole.Assistant, "ack")] : []);
        var evaluator = new DelegateLoopEvaluator((ctx, _) =>
            new ValueTask<LoopEvaluation>(
                ctx.Iteration < 2 ? LoopEvaluation.Continue("fix it") : LoopEvaluation.Stop()));
        var options = new LoopAgentOptions { OnBehalfOfAuthorName = "loop" };
        var agent = new LoopAgent(capture.Agent, evaluator, options);

        // Act
        var updates = new List<AgentResponseUpdate>();
        await foreach (var update in agent.RunStreamingAsync([new ChatMessage(ChatRole.User, "original")], new ChatClientAgentSession()))
        {
            updates.Add(update);
        }

        // Assert (the first iteration's "ack" and then the surfaced feedback whose iteration produced no updates).
        Assert.Equal(["ack", "fix it"], updates.Select(static u => u.Text));
        AgentResponseUpdate feedbackUpdate = updates[1];
        Assert.Equal("loop", feedbackUpdate.AuthorName);
        Assert.False(string.IsNullOrEmpty(feedbackUpdate.ResponseId));
        Assert.True(string.IsNullOrEmpty(feedbackUpdate.AgentId));
        Assert.False(string.IsNullOrEmpty(feedbackUpdate.MessageId));
    }

    #endregion
}
