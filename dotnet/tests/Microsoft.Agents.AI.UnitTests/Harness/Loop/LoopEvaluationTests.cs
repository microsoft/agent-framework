// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI.UnitTests;

/// <summary>
/// Unit tests for the <see cref="LoopEvaluation"/> class.
/// </summary>
public class LoopEvaluationTests
{
    /// <summary>
    /// Verify that Stop produces an evaluation that does not re-invoke and carries no feedback.
    /// </summary>
    [Fact]
    public void Stop_DoesNotReinvoke_AndHasNoFeedback()
    {
        // Act
        var evaluation = LoopEvaluation.Stop();

        // Assert
        Assert.False(evaluation.ShouldReinvoke);
        Assert.Null(evaluation.Feedback);
    }

    /// <summary>
    /// Verify that Continue with no argument re-invokes and carries no feedback.
    /// </summary>
    [Fact]
    public void Continue_NoFeedback_ReinvokesWithNullFeedback()
    {
        // Act
        var evaluation = LoopEvaluation.Continue();

        // Assert
        Assert.True(evaluation.ShouldReinvoke);
        Assert.Null(evaluation.Feedback);
    }

    /// <summary>
    /// Verify that Continue with whitespace-only feedback normalizes the feedback to null, matching the documented
    /// "null, empty, or whitespace is treated as no feedback" semantics.
    /// </summary>
    [Theory]
    [InlineData("")]
    [InlineData("   ")]
    [InlineData("\t\n")]
    public void Continue_WhitespaceFeedback_NormalizesToNull(string feedback)
    {
        // Act
        var evaluation = LoopEvaluation.Continue(feedback);

        // Assert
        Assert.True(evaluation.ShouldReinvoke);
        Assert.Null(evaluation.Feedback);
    }
}
