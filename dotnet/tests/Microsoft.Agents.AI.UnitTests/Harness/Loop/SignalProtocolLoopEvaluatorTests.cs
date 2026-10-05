// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Moq;

namespace Microsoft.Agents.AI.UnitTests;

/// <summary>
/// Unit tests for the <see cref="SignalProtocolLoopEvaluator"/> class.
/// </summary>
public class SignalProtocolLoopEvaluatorTests
{
    /// <summary>
    /// Verify that the evaluator stops when TASK_COMPLETE: is present.
    /// </summary>
    [Fact]
    public async Task EvaluateAsync_TaskCompletePresent_StopsAsync()
    {
        // Arrange
        var evaluator = new SignalProtocolLoopEvaluator();
        LoopContext context = CreateContext("TASK_COMPLETE: all done");

        // Act
        LoopEvaluation evaluation = await evaluator.EvaluateAsync(context);

        // Assert
        Assert.False(evaluation.ShouldReinvoke);
    }

    /// <summary>
    /// Verify that the evaluator stops when NEED_INPUT: is present.
    /// </summary>
    [Fact]
    public async Task EvaluateAsync_NeedInputPresent_StopsAsync()
    {
        // Arrange
        var evaluator = new SignalProtocolLoopEvaluator();
        LoopContext context = CreateContext("NEED_INPUT: which file?");

        // Act
        LoopEvaluation evaluation = await evaluator.EvaluateAsync(context);

        // Assert
        Assert.False(evaluation.ShouldReinvoke);
    }

    /// <summary>
    /// Verify that the evaluator continues with feedback when no signal is present.
    /// </summary>
    [Fact]
    public async Task EvaluateAsync_NoSignal_ContinuesWithFeedbackAsync()
    {
        // Arrange
        var evaluator = new SignalProtocolLoopEvaluator();
        LoopContext context = CreateContext("still working");

        // Act
        LoopEvaluation evaluation = await evaluator.EvaluateAsync(context);

        // Assert
        Assert.True(evaluation.ShouldReinvoke);
        Assert.NotNull(evaluation.Feedback);
    }

    /// <summary>
    /// Verify that TASK_COMPLETE: takes priority over NEED_INPUT: when both are present.
    /// </summary>
    [Fact]
    public async Task EvaluateAsync_TaskCompleteWinsOverNeedInput_StopsAsync()
    {
        // Arrange
        var evaluator = new SignalProtocolLoopEvaluator();
        LoopContext context = CreateContext("NEED_INPUT: q? TASK_COMPLETE: done");

        // Act
        LoopEvaluation evaluation = await evaluator.EvaluateAsync(context);

        // Assert
        Assert.False(evaluation.ShouldReinvoke);
        Assert.Equal(LoopExitReason.Completed, context.AdditionalProperties[LoopExitReason.AdditionalPropertiesKey]);
    }

    /// <summary>
    /// Verify that TASK_COMPLETE: stamps the completed exit reason.
    /// </summary>
    [Fact]
    public async Task EvaluateAsync_TaskComplete_StampsCompletedReasonAsync()
    {
        // Arrange
        var evaluator = new SignalProtocolLoopEvaluator();
        LoopContext context = CreateContext("TASK_COMPLETE: done");

        // Act
        await evaluator.EvaluateAsync(context);

        // Assert
        Assert.Equal("completed", context.AdditionalProperties["loop_exit_reason"]);
    }

    /// <summary>
    /// Verify that NEED_INPUT: stamps the need_input exit reason.
    /// </summary>
    [Fact]
    public async Task EvaluateAsync_NeedInput_StampsNeedInputReasonAsync()
    {
        // Arrange
        var evaluator = new SignalProtocolLoopEvaluator();
        LoopContext context = CreateContext("NEED_INPUT: which file?");

        // Act
        await evaluator.EvaluateAsync(context);

        // Assert
        Assert.Equal("need_input", context.AdditionalProperties["loop_exit_reason"]);
    }

    /// <summary>
    /// Verify that no exit reason is stamped when no signal is present.
    /// </summary>
    [Fact]
    public async Task EvaluateAsync_NoSignal_DoesNotStampReasonAsync()
    {
        // Arrange
        var evaluator = new SignalProtocolLoopEvaluator();
        LoopContext context = CreateContext("still working");

        // Act
        await evaluator.EvaluateAsync(context);

        // Assert
        Assert.False(context.AdditionalProperties.ContainsKey("loop_exit_reason"));
    }

    /// <summary>
    /// Verify that a custom feedback message is used when no signal is present.
    /// </summary>
    [Fact]
    public async Task EvaluateAsync_CustomFeedback_UsedWhenNoSignalAsync()
    {
        // Arrange
        var evaluator = new SignalProtocolLoopEvaluator("keep going");
        LoopContext context = CreateContext("still working");

        // Act
        LoopEvaluation evaluation = await evaluator.EvaluateAsync(context);

        // Assert
        Assert.True(evaluation.ShouldReinvoke);
        Assert.Equal("keep going", evaluation.Feedback);
    }

    /// <summary>
    /// Verify that EvaluateAsync throws when the context is null.
    /// </summary>
    [Fact]
    public async Task EvaluateAsync_NullContext_ThrowsAsync()
    {
        // Arrange
        var evaluator = new SignalProtocolLoopEvaluator();

        // Act & Assert
        await Assert.ThrowsAsync<ArgumentNullException>("context", async () => await evaluator.EvaluateAsync(null!));
    }

    /// <summary>
    /// Verify the TASK_COMPLETE token constant value.
    /// </summary>
    [Fact]
    public void TaskCompleteToken_IsExpectedValue()
    {
        // Assert
        Assert.Equal("TASK_COMPLETE:", SignalProtocolLoopEvaluator.TaskCompleteToken);
    }

    /// <summary>
    /// Verify the NEED_INPUT token constant value.
    /// </summary>
    [Fact]
    public void NeedInputToken_IsExpectedValue()
    {
        // Assert
        Assert.Equal("NEED_INPUT:", SignalProtocolLoopEvaluator.NeedInputToken);
    }

    private static LoopContext CreateContext(string responseText) => new(
        new Mock<AIAgent>().Object,
        new ChatClientAgentSession(),
        [new ChatMessage(ChatRole.User, "go")],
        new AgentResponse([new ChatMessage(ChatRole.Assistant, responseText)]));
}
