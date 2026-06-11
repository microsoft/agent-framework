// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Moq;

namespace Microsoft.Agents.AI.UnitTests;

/// <summary>
/// Unit tests for the <see cref="CompletionMarkerLoopEvaluator"/> class.
/// </summary>
public class CompletionMarkerLoopEvaluatorTests
{
    /// <summary>
    /// Verify that the constructor throws when the marker is null, empty, or whitespace.
    /// </summary>
    /// <param name="marker">The invalid marker value.</param>
    [Theory]
    [InlineData(null)]
    [InlineData("")]
    [InlineData("   ")]
    public void CompletionMarkerLoopEvaluator_InvalidMarker_Throws(string? marker)
    {
        // Act & Assert
        Assert.ThrowsAny<ArgumentException>(() => new CompletionMarkerLoopEvaluator(marker!));
    }

    /// <summary>
    /// Verify that the evaluator stops the loop when the marker appears in the latest response.
    /// </summary>
    [Fact]
    public async Task EvaluateAsync_MarkerPresent_StopsAsync()
    {
        // Arrange
        var evaluator = new CompletionMarkerLoopEvaluator("DONE");
        LoopContext context = CreateContext("all DONE here");

        // Act
        LoopEvaluation evaluation = await evaluator.EvaluateAsync(context);

        // Assert
        Assert.False(evaluation.ShouldReinvoke);
    }

    /// <summary>
    /// Verify that the evaluator continues with default feedback (containing the marker) when the marker is absent.
    /// </summary>
    [Fact]
    public async Task EvaluateAsync_MarkerAbsent_ContinuesWithDefaultFeedbackAsync()
    {
        // Arrange
        var evaluator = new CompletionMarkerLoopEvaluator("DONE");
        LoopContext context = CreateContext("still working");

        // Act
        LoopEvaluation evaluation = await evaluator.EvaluateAsync(context);

        // Assert
        Assert.True(evaluation.ShouldReinvoke);
        Assert.NotNull(evaluation.Feedback);
        Assert.Contains("DONE", evaluation.Feedback!);
        Assert.DoesNotContain(CompletionMarkerLoopEvaluator.CompletionMarkerPlaceholder, evaluation.Feedback!);
    }

    /// <summary>
    /// Verify that a custom feedback template is honored, with the completion marker substituted for the placeholder.
    /// </summary>
    [Fact]
    public async Task EvaluateAsync_MarkerAbsent_CustomTemplate_IsHonoredAsync()
    {
        // Arrange
        const string Template = "Keep going and finish with " + CompletionMarkerLoopEvaluator.CompletionMarkerPlaceholder + " when done.";
        var evaluator = new CompletionMarkerLoopEvaluator("FINISHED", new CompletionMarkerLoopEvaluatorOptions { FeedbackMessageTemplate = Template });
        LoopContext context = CreateContext("still working");

        // Act
        LoopEvaluation evaluation = await evaluator.EvaluateAsync(context);

        // Assert
        Assert.True(evaluation.ShouldReinvoke);
        Assert.Equal("Keep going and finish with FINISHED when done.", evaluation.Feedback);
    }

    /// <summary>
    /// Verify that a custom feedback template containing the last-response placeholder echoes the agent's latest
    /// response text, with no leftover placeholder.
    /// </summary>
    [Fact]
    public async Task EvaluateAsync_MarkerAbsent_CustomTemplate_SubstitutesLastResponseAsync()
    {
        // Arrange
        const string Template = "Your previous attempt was: '" + CompletionMarkerLoopEvaluator.LastResponsePlaceholder +
            "'. Improve it and finish with " + CompletionMarkerLoopEvaluator.CompletionMarkerPlaceholder + " when done.";
        var evaluator = new CompletionMarkerLoopEvaluator("FINISHED", new CompletionMarkerLoopEvaluatorOptions { FeedbackMessageTemplate = Template });
        LoopContext context = CreateContext("candidate name: NoteNest");

        // Act
        LoopEvaluation evaluation = await evaluator.EvaluateAsync(context);

        // Assert
        Assert.True(evaluation.ShouldReinvoke);
        Assert.Equal("Your previous attempt was: 'candidate name: NoteNest'. Improve it and finish with FINISHED when done.", evaluation.Feedback);
        Assert.DoesNotContain(CompletionMarkerLoopEvaluator.LastResponsePlaceholder, evaluation.Feedback!);
    }

    /// <summary>
    /// Verify that the default feedback template does not include the agent's latest response text (the last-response
    /// placeholder is opt-in via a custom template).
    /// </summary>
    [Fact]
    public async Task EvaluateAsync_MarkerAbsent_DefaultTemplate_DoesNotIncludeLastResponseAsync()
    {
        // Arrange
        var evaluator = new CompletionMarkerLoopEvaluator("DONE");
        LoopContext context = CreateContext("candidate name: NoteNest");

        // Act
        LoopEvaluation evaluation = await evaluator.EvaluateAsync(context);

        // Assert
        Assert.True(evaluation.ShouldReinvoke);
        Assert.Equal(CompletionMarkerLoopEvaluator.DefaultFeedbackMessageTemplate.Replace(CompletionMarkerLoopEvaluator.CompletionMarkerPlaceholder, "DONE"), evaluation.Feedback);
        Assert.DoesNotContain("NoteNest", evaluation.Feedback!);
    }

    /// <summary>
    /// Verify that EvaluateAsync throws when the context is null.
    /// </summary>
    [Fact]
    public async Task EvaluateAsync_NullContext_ThrowsAsync()
    {
        // Arrange
        var evaluator = new CompletionMarkerLoopEvaluator("DONE");

        // Act & Assert
        await Assert.ThrowsAsync<ArgumentNullException>("context", async () => await evaluator.EvaluateAsync(null!));
    }

    private static LoopContext CreateContext(string responseText) => new(
        new Mock<AIAgent>().Object,
        new ChatClientAgentSession(),
        [new ChatMessage(ChatRole.User, "go")],
        new AgentResponse([new ChatMessage(ChatRole.Assistant, responseText)]));
}
