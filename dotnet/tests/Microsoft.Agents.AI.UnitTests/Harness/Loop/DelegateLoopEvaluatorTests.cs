// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Moq;

namespace Microsoft.Agents.AI.UnitTests;

/// <summary>
/// Unit tests for the <see cref="DelegateLoopEvaluator"/> class.
/// </summary>
public class DelegateLoopEvaluatorTests
{
    /// <summary>
    /// Verify that the constructor throws when the evaluate delegate is null.
    /// </summary>
    [Fact]
    public void DelegateLoopEvaluator_NullDelegate_Throws()
    {
        // Act & Assert
        Assert.Throws<ArgumentNullException>("evaluate", () => new DelegateLoopEvaluator(null!));
    }

    /// <summary>
    /// Verify that EvaluateAsync throws when the context is null.
    /// </summary>
    [Fact]
    public async Task EvaluateAsync_NullContext_ThrowsAsync()
    {
        // Arrange
        var evaluator = new DelegateLoopEvaluator((_, _) => new ValueTask<LoopEvaluation>(LoopEvaluation.Stop()));

        // Act & Assert
        await Assert.ThrowsAsync<ArgumentNullException>("context", async () => await evaluator.EvaluateAsync(null!));
    }

    /// <summary>
    /// Verify that EvaluateAsync invokes the supplied delegate and returns the evaluation it produces.
    /// </summary>
    [Fact]
    public async Task EvaluateAsync_InvokesDelegate_AndReturnsItsEvaluationAsync()
    {
        // Arrange
        bool invoked = false;
        var expected = LoopEvaluation.Continue("feedback");
        var evaluator = new DelegateLoopEvaluator((_, _) =>
        {
            invoked = true;
            return new ValueTask<LoopEvaluation>(expected);
        });
        LoopContext context = CreateContext();

        // Act
        LoopEvaluation evaluation = await evaluator.EvaluateAsync(context);

        // Assert
        Assert.True(invoked);
        Assert.Same(expected, evaluation);
    }

    /// <summary>
    /// Verify that EvaluateAsync passes the same context instance to the delegate.
    /// </summary>
    [Fact]
    public async Task EvaluateAsync_PassesContextToDelegateAsync()
    {
        // Arrange
        LoopContext? received = null;
        var evaluator = new DelegateLoopEvaluator((ctx, _) =>
        {
            received = ctx;
            return new ValueTask<LoopEvaluation>(LoopEvaluation.Stop());
        });
        LoopContext context = CreateContext();

        // Act
        await evaluator.EvaluateAsync(context);

        // Assert
        Assert.Same(context, received);
    }

    /// <summary>
    /// Verify that EvaluateAsync forwards the cancellation token to the delegate.
    /// </summary>
    [Fact]
    public async Task EvaluateAsync_ForwardsCancellationTokenToDelegateAsync()
    {
        // Arrange
        using var cts = new CancellationTokenSource();
        CancellationToken received = default;
        var evaluator = new DelegateLoopEvaluator((_, ct) =>
        {
            received = ct;
            return new ValueTask<LoopEvaluation>(LoopEvaluation.Stop());
        });
        LoopContext context = CreateContext();

        // Act
        await evaluator.EvaluateAsync(context, cts.Token);

        // Assert
        Assert.Equal(cts.Token, received);
    }

    private static LoopContext CreateContext() => new(
        new Mock<AIAgent>().Object,
        new ChatClientAgentSession(),
        [new ChatMessage(ChatRole.User, "go")],
        new AgentResponse([new ChatMessage(ChatRole.Assistant, "response")]));
}
