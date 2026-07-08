// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Moq;

using static Microsoft.Agents.AI.UnitTests.LoopTestHelpers;

namespace Microsoft.Agents.AI.UnitTests;

/// <summary>
/// Unit tests for the <see cref="AIJudgeLoopEvaluator"/> class.
/// </summary>
public class AIJudgeLoopEvaluatorTests
{
    /// <summary>
    /// Verify that the evaluator stops when the judge reports the request was answered.
    /// </summary>
    [Fact]
    public async Task EvaluateAsync_Answered_StopsAsync()
    {
        // Arrange
        var judgeClient = CreateJudgeClient("{\"answered\":true}");
        var evaluator = new AIJudgeLoopEvaluator(judgeClient);
        LoopContext context = CreateContext();

        // Act
        LoopEvaluation evaluation = await evaluator.EvaluateAsync(context);

        // Assert
        Assert.False(evaluation.ShouldReinvoke);
    }

    /// <summary>
    /// Verify that when not answered the evaluator continues with feedback carrying the judge's gap analysis.
    /// </summary>
    [Fact]
    public async Task EvaluateAsync_NotAnswered_ContinuesWithGapAnalysisAsync()
    {
        // Arrange
        var judgeClient = CreateJudgeClient("{\"answered\":false,\"gapAnalysis\":\"the cost estimate is missing\"}");
        var evaluator = new AIJudgeLoopEvaluator(judgeClient);
        LoopContext context = CreateContext();

        // Act
        LoopEvaluation evaluation = await evaluator.EvaluateAsync(context);

        // Assert
        Assert.True(evaluation.ShouldReinvoke);
        Assert.NotNull(evaluation.Feedback);
        Assert.Contains("the cost estimate is missing", evaluation.Feedback!);
        Assert.DoesNotContain(AIJudgeLoopEvaluator.GapAnalysisPlaceholder, evaluation.Feedback!);
    }

    /// <summary>
    /// Verify that the evaluator falls back to text parsing and stops when the DONE verdict marker is present.
    /// </summary>
    [Fact]
    public async Task EvaluateAsync_TextFallback_StopsWhenAnsweredAsync()
    {
        // Arrange
        var judgeClient = CreateJudgeClient(AIJudgeLoopEvaluator.DoneVerdictMarker);
        var evaluator = new AIJudgeLoopEvaluator(judgeClient);
        LoopContext context = CreateContext();

        // Act
        LoopEvaluation evaluation = await evaluator.EvaluateAsync(context);

        // Assert
        Assert.False(evaluation.ShouldReinvoke);
    }

    /// <summary>
    /// Verify that the gap-analysis placeholder is filled with a fallback token when no structured output is produced.
    /// </summary>
    [Fact]
    public async Task EvaluateAsync_NotAnswered_TextFallback_InjectsUnknownGapAnalysisAsync()
    {
        // Arrange
        var judgeClient = CreateJudgeClient(AIJudgeLoopEvaluator.MoreVerdictMarker);
        var evaluator = new AIJudgeLoopEvaluator(judgeClient);
        LoopContext context = CreateContext();

        // Act
        LoopEvaluation evaluation = await evaluator.EvaluateAsync(context);

        // Assert
        Assert.True(evaluation.ShouldReinvoke);
        Assert.Contains("<unknown>", evaluation.Feedback!);
    }

    /// <summary>
    /// Verify that the text fallback keeps looping for replies that merely contain the substring "ANSWERED" (for
    /// example "UNANSWERED" or "NOT ANSWERED") rather than the explicit DONE verdict marker.
    /// </summary>
    [Theory]
    [InlineData("UNANSWERED")]
    [InlineData("NOT ANSWERED")]
    [InlineData("The request is not yet answered.")]
    public async Task EvaluateAsync_TextFallback_AmbiguousReply_ContinuesAsync(string reply)
    {
        // Arrange
        var judgeClient = CreateJudgeClient(reply);
        var evaluator = new AIJudgeLoopEvaluator(judgeClient);
        LoopContext context = CreateContext();

        // Act
        LoopEvaluation evaluation = await evaluator.EvaluateAsync(context);

        // Assert
        Assert.True(evaluation.ShouldReinvoke);
    }

    /// <summary>
    /// Verify that custom judge instructions from options are sent to the judge client.
    /// </summary>
    [Fact]
    public async Task EvaluateAsync_CustomInstructions_AreSentToJudgeAsync()
    {
        // Arrange
        List<ChatMessage>? judgeMessages = null;
        var judgeMock = new Mock<IChatClient>();
        judgeMock.Setup(c => c.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .Callback<IEnumerable<ChatMessage>, ChatOptions?, CancellationToken>((msgs, _, _) => judgeMessages = msgs.ToList())
            .ReturnsAsync(new ChatResponse(new ChatMessage(ChatRole.Assistant, "{\"answered\":true}")));
        var evaluator = new AIJudgeLoopEvaluator(judgeMock.Object, new AIJudgeLoopEvaluatorOptions { Instructions = "CUSTOM JUDGE PROMPT" });
        LoopContext context = CreateContext();

        // Act
        await evaluator.EvaluateAsync(context);

        // Assert
        Assert.NotNull(judgeMessages);
        Assert.Contains(judgeMessages!, m => m.Role == ChatRole.System && m.Text == "CUSTOM JUDGE PROMPT");
    }

    /// <summary>
    /// Verify that a custom feedback message template from options is honored.
    /// </summary>
    [Fact]
    public async Task EvaluateAsync_CustomFeedbackMessageTemplate_IsHonoredAsync()
    {
        // Arrange
        var judgeClient = CreateJudgeClient("{\"answered\":false,\"gapAnalysis\":\"add unit tests\"}");
        const string Template = "Please address: " + AIJudgeLoopEvaluator.GapAnalysisPlaceholder;
        var evaluator = new AIJudgeLoopEvaluator(judgeClient, new AIJudgeLoopEvaluatorOptions { FeedbackMessageTemplate = Template });
        LoopContext context = CreateContext();

        // Act
        LoopEvaluation evaluation = await evaluator.EvaluateAsync(context);

        // Assert
        Assert.Equal("Please address: add unit tests", evaluation.Feedback);
    }

    /// <summary>
    /// Verify that non-text content in the original request (for example an image) is forwarded to the judge
    /// rather than being silently dropped when flattening the request to text.
    /// </summary>
    [Fact]
    public async Task EvaluateAsync_NonTextRequestContent_IsForwardedToJudgeAsync()
    {
        // Arrange
        List<ChatMessage>? judgeMessages = null;
        var judgeMock = new Mock<IChatClient>();
        judgeMock.Setup(c => c.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .Callback<IEnumerable<ChatMessage>, ChatOptions?, CancellationToken>((msgs, _, _) => judgeMessages = msgs.ToList())
            .ReturnsAsync(new ChatResponse(new ChatMessage(ChatRole.Assistant, "{\"answered\":true}")));
        var evaluator = new AIJudgeLoopEvaluator(judgeMock.Object);
        var imageContent = new DataContent(new byte[] { 1, 2, 3, 4 }, "image/png");
        var context = new LoopContext(
            new Mock<AIAgent>().Object,
            new ChatClientAgentSession(),
            [new ChatMessage(ChatRole.User, [imageContent])],
            new AgentResponse([new ChatMessage(ChatRole.Assistant, "partial answer")]));

        // Act
        await evaluator.EvaluateAsync(context);

        // Assert
        Assert.NotNull(judgeMessages);
        ChatMessage userMessage = Assert.Single(judgeMessages!, m => m.Role == ChatRole.User);
        Assert.Contains(userMessage.Contents.OfType<DataContent>(), c => c.MediaType == "image/png");
    }

    /// <summary>
    /// Verify that the constructor throws when the judge client is null.
    /// </summary>
    [Fact]
    public void AIJudgeLoopEvaluator_NullClient_Throws()
    {
        // Act & Assert
        Assert.Throws<ArgumentNullException>("judgeClient", () => new AIJudgeLoopEvaluator(null!));
    }

    /// <summary>
    /// Verify that EvaluateAsync throws when the context is null.
    /// </summary>
    [Fact]
    public async Task EvaluateAsync_NullContext_ThrowsAsync()
    {
        // Arrange
        var evaluator = new AIJudgeLoopEvaluator(CreateJudgeClient("{\"answered\":true}"));

        // Act & Assert
        await Assert.ThrowsAsync<ArgumentNullException>("context", async () => await evaluator.EvaluateAsync(null!));
    }

    /// <summary>
    /// Verify that supplied criteria are rendered into the default judge instructions as a bullet list and the
    /// placeholder is consumed.
    /// </summary>
    [Fact]
    public async Task EvaluateAsync_Criteria_AreRenderedIntoDefaultInstructionsAsync()
    {
        // Arrange
        var judgeClient = CreateCapturingJudgeClient("{\"answered\":true}", out List<ChatMessage> judgeMessages);
        var options = new AIJudgeLoopEvaluatorOptions { Criteria = ["Must cite sources", "Must be under 200 words"] };
        var evaluator = new AIJudgeLoopEvaluator(judgeClient, options);
        LoopContext context = CreateContext();

        // Act
        await evaluator.EvaluateAsync(context);

        // Assert
        string system = judgeMessages.Single(static m => m.Role == ChatRole.System).Text;
        Assert.Contains("The response must satisfy all of the following criteria:", system);
        Assert.Contains("- Must cite sources", system);
        Assert.Contains("- Must be under 200 words", system);
        Assert.DoesNotContain(AIJudgeLoopEvaluator.CriteriaPlaceholder, system);
    }

    /// <summary>
    /// Verify that when no criteria are supplied the placeholder is removed and no criteria block is added to the
    /// default instructions.
    /// </summary>
    [Fact]
    public async Task EvaluateAsync_NoCriteria_LeavesDefaultInstructionsWithoutCriteriaBlockAsync()
    {
        // Arrange
        var judgeClient = CreateCapturingJudgeClient("{\"answered\":true}", out List<ChatMessage> judgeMessages);
        var evaluator = new AIJudgeLoopEvaluator(judgeClient);
        LoopContext context = CreateContext();

        // Act
        await evaluator.EvaluateAsync(context);

        // Assert
        string system = judgeMessages.Single(static m => m.Role == ChatRole.System).Text;
        Assert.DoesNotContain(AIJudgeLoopEvaluator.CriteriaPlaceholder, system);
        Assert.DoesNotContain("The response must satisfy all of the following criteria:", system);
    }

    /// <summary>
    /// Verify that criteria are injected at the placeholder location in custom instructions.
    /// </summary>
    [Fact]
    public async Task EvaluateAsync_CustomInstructionsWithPlaceholder_InjectsCriteriaAsync()
    {
        // Arrange
        var judgeClient = CreateCapturingJudgeClient("{\"answered\":true}", out List<ChatMessage> judgeMessages);
        const string Instructions = "Judge the answer." + AIJudgeLoopEvaluator.CriteriaPlaceholder + " Be strict.";
        var options = new AIJudgeLoopEvaluatorOptions { Instructions = Instructions, Criteria = ["Must include code"] };
        var evaluator = new AIJudgeLoopEvaluator(judgeClient, options);
        LoopContext context = CreateContext();

        // Act
        await evaluator.EvaluateAsync(context);

        // Assert
        string system = judgeMessages.Single(static m => m.Role == ChatRole.System).Text;
        Assert.StartsWith("Judge the answer.", system);
        Assert.EndsWith("Be strict.", system);
        Assert.Contains("- Must include code", system);
        Assert.DoesNotContain(AIJudgeLoopEvaluator.CriteriaPlaceholder, system);
    }

    /// <summary>
    /// Verify that custom instructions without the placeholder do not receive the criteria.
    /// </summary>
    [Fact]
    public async Task EvaluateAsync_CustomInstructionsWithoutPlaceholder_OmitsCriteriaAsync()
    {
        // Arrange
        var judgeClient = CreateCapturingJudgeClient("{\"answered\":true}", out List<ChatMessage> judgeMessages);
        const string Instructions = "Judge the answer and be strict.";
        var options = new AIJudgeLoopEvaluatorOptions { Instructions = Instructions, Criteria = ["Must include code"] };
        var evaluator = new AIJudgeLoopEvaluator(judgeClient, options);
        LoopContext context = CreateContext();

        // Act
        await evaluator.EvaluateAsync(context);

        // Assert
        string system = judgeMessages.Single(static m => m.Role == ChatRole.System).Text;
        Assert.Equal(Instructions, system);
    }

    private static LoopContext CreateContext() => new(
        new Mock<AIAgent>().Object,
        new ChatClientAgentSession(),
        [new ChatMessage(ChatRole.User, "original question")],
        new AgentResponse([new ChatMessage(ChatRole.Assistant, "partial answer")]));
}
