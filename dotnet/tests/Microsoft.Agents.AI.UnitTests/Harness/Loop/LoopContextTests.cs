// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Moq;

namespace Microsoft.Agents.AI.UnitTests;

/// <summary>
/// Unit tests for the <see cref="LoopContext"/> class, including its public constructor used to test custom evaluators.
/// </summary>
public class LoopContextTests
{
    /// <summary>
    /// Verify that the constructor throws when the agent is null.
    /// </summary>
    [Fact]
    public void Constructor_NullAgent_Throws()
    {
        // Act & Assert
        Assert.Throws<ArgumentNullException>("agent", () => new LoopContext(
            null!, new ChatClientAgentSession(), [], CreateResponse()));
    }

    /// <summary>
    /// Verify that the constructor throws when the session is null.
    /// </summary>
    [Fact]
    public void Constructor_NullSession_Throws()
    {
        // Act & Assert
        Assert.Throws<ArgumentNullException>("session", () => new LoopContext(
            new Mock<AIAgent>().Object, null!, [], CreateResponse()));
    }

    /// <summary>
    /// Verify that the constructor throws when the initial messages are null.
    /// </summary>
    [Fact]
    public void Constructor_NullInitialMessages_Throws()
    {
        // Act & Assert
        Assert.Throws<ArgumentNullException>("initialMessages", () => new LoopContext(
            new Mock<AIAgent>().Object, new ChatClientAgentSession(), null!, CreateResponse()));
    }

    /// <summary>
    /// Verify that the constructor throws when the last response is null.
    /// </summary>
    [Fact]
    public void Constructor_NullLastResponse_Throws()
    {
        // Act & Assert
        Assert.Throws<ArgumentNullException>("lastResponse", () => new LoopContext(
            new Mock<AIAgent>().Object, new ChatClientAgentSession(), [], null!));
    }

    /// <summary>
    /// Verify that the constructor populates the properties and that LastResponse is never null.
    /// </summary>
    [Fact]
    public void Constructor_ValidArguments_SetsProperties()
    {
        // Arrange
        var agent = new Mock<AIAgent>().Object;
        var session = new ChatClientAgentSession();
        ChatMessage[] initialMessages = [new ChatMessage(ChatRole.User, "go")];
        var response = CreateResponse("done");

        // Act
        var context = new LoopContext(agent, session, initialMessages, response);

        // Assert
        Assert.Same(agent, context.Agent);
        Assert.Same(session, context.Session);
        Assert.Same(initialMessages, context.InitialMessages);
        Assert.Same(response, context.LastResponse);
        Assert.Null(context.RunOptions);
        Assert.NotNull(context.AdditionalProperties);
        Assert.Equal(0, context.Iteration);
        Assert.Empty(context.Feedback);
    }

    /// <summary>
    /// Verify that the session can be replaced through the internal setter (used by the loop for fresh contexts).
    /// </summary>
    [Fact]
    public void Session_IsInternallySettable()
    {
        // Arrange
        var context = new LoopContext(
            new Mock<AIAgent>().Object, new ChatClientAgentSession(), [], CreateResponse());
        var newSession = new ChatClientAgentSession();

        // Act
        context.Session = newSession;

        // Assert
        Assert.Same(newSession, context.Session);
    }

    /// <summary>
    /// Verify that <see cref="LoopContext.Feedback"/> can be assigned through its internal setter.
    /// </summary>
    [Fact]
    public void Feedback_IsInternallySettable()
    {
        // Arrange
        var context = new LoopContext(
            new Mock<AIAgent>().Object, new ChatClientAgentSession(), [], CreateResponse());

        // Act
        context.Feedback = ["first", null];

        // Assert
        Assert.Equal(["first", null], context.Feedback);
    }

    /// <summary>
    /// Verify that an evaluator can be evaluated against a publicly-constructed context (the scenario the public
    /// constructor exists to support).
    /// </summary>
    [Fact]
    public async Task PubliclyConstructedContext_CanEvaluateEvaluatorAsync()
    {
        // Arrange
        var context = new LoopContext(
            new Mock<AIAgent>().Object,
            new ChatClientAgentSession(),
            [new ChatMessage(ChatRole.User, "go")],
            CreateResponse("done"));
        var evaluator = new DelegateLoopEvaluator((ctx, _) =>
            new ValueTask<LoopEvaluation>(
                ctx.LastResponse.Text == "done" ? LoopEvaluation.Stop() : LoopEvaluation.Continue()));

        // Act
        LoopEvaluation evaluation = await evaluator.EvaluateAsync(context);

        // Assert
        Assert.False(evaluation.ShouldReinvoke);
    }

    private static AgentResponse CreateResponse(string text = "response") =>
        new([new ChatMessage(ChatRole.Assistant, text)]);
}
