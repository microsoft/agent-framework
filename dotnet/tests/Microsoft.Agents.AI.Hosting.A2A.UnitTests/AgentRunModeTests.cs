// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Agents.AI.Hosting.A2A.UnitTests;

/// <summary>
/// Unit tests for the <see cref="AgentRunMode"/> class.
/// </summary>
public sealed class AgentRunModeTests
{
    /// <summary>
    /// Verifies that ReturnTaskWhen throws ArgumentNullException for null delegate.
    /// </summary>
    [Fact]
    public void ReturnTaskWhen_NullDelegate_ThrowsArgumentNullException()
    {
        // Arrange & Act & Assert
        Assert.Throws<ArgumentNullException>(() =>
            AgentRunMode.ReturnTaskWhen(null!));
    }

    /// <summary>
    /// Verifies that ReturnMessage equals another ReturnMessage instance.
    /// </summary>
    [Fact]
    public void Equals_ReturnMessage_AreEqual()
    {
        // Arrange
        var mode1 = AgentRunMode.ReturnMessage;
        var mode2 = AgentRunMode.ReturnMessage;

        // Act & Assert
        Assert.True(mode1.Equals(mode2));
        Assert.True(mode1 == mode2);
        Assert.False(mode1 != mode2);
        Assert.Equal(mode1.GetHashCode(), mode2.GetHashCode());
    }

    /// <summary>
    /// Verifies that ReturnTask equals another ReturnTask instance.
    /// </summary>
    [Fact]
    public void Equals_ReturnTask_AreEqual()
    {
        // Arrange
        var mode1 = AgentRunMode.ReturnTask;
        var mode2 = AgentRunMode.ReturnTask;

        // Act & Assert
        Assert.True(mode1.Equals(mode2));
        Assert.True(mode1 == mode2);
    }

    /// <summary>
    /// Verifies that ReturnMessage and ReturnTask are not equal.
    /// </summary>
    [Fact]
    public void Equals_DifferentModes_AreNotEqual()
    {
        // Arrange
        var message = AgentRunMode.ReturnMessage;
        var task = AgentRunMode.ReturnTask;

        // Act & Assert
        Assert.False(message.Equals(task));
        Assert.False(message == task);
    }

    /// <summary>
    /// Verifies that Equals returns false for null.
    /// </summary>
    [Fact]
    public void Equals_Null_ReturnsFalse()
    {
        // Arrange
        var mode = AgentRunMode.ReturnMessage;

        // Act & Assert
        Assert.False(mode.Equals(null));
        Assert.False(mode.Equals((object?)null));
        Assert.False(mode == null);
        Assert.True(mode != null);
    }

    /// <summary>
    /// Verifies that two null AgentRunMode values are equal.
    /// </summary>
    [Fact]
    public void Equals_BothNull_AreEqual()
    {
        // Arrange
        AgentRunMode? mode1 = null;
        AgentRunMode? mode2 = null;

        // Act & Assert
        Assert.True(mode1 == mode2);
        Assert.False(mode1 != mode2);
    }

    /// <summary>
    /// Verifies that ToString returns expected values.
    /// </summary>
    [Fact]
    public void ToString_ReturnsExpectedValues()
    {
        // Act & Assert
        Assert.Equal("message", AgentRunMode.ReturnMessage.ToString());
        Assert.Equal("task", AgentRunMode.ReturnTask.ToString());
        Assert.Equal("dynamic", AgentRunMode.ReturnTaskWhen((_, _) => ValueTask.FromResult(true)).ToString());
    }

    /// <summary>
    /// Verifies that Equals works correctly with object parameter.
    /// </summary>
    [Fact]
    public void Equals_WithObjectParameter_WorksCorrectly()
    {
        // Arrange
        var mode = AgentRunMode.ReturnMessage;

        // Act & Assert
        Assert.True(mode.Equals((object)AgentRunMode.ReturnMessage));
        Assert.False(mode.Equals((object)AgentRunMode.ReturnTask));
        Assert.False(mode.Equals("not a run mode"));
    }

    /// <summary>
    /// Verifies that two ReturnTaskWhen instances with different delegates are not considered equal,
    /// because equality includes delegate identity for dynamic modes.
    /// </summary>
    [Fact]
    public void Equals_ReturnTaskWhen_DifferentDelegates_AreNotEqual()
    {
        // Arrange
        var mode1 = AgentRunMode.ReturnTaskWhen((_, _) => ValueTask.FromResult(true));
        var mode2 = AgentRunMode.ReturnTaskWhen((_, _) => ValueTask.FromResult(false));

        // Act & Assert
        Assert.False(mode1.Equals(mode2));
        Assert.True(mode1 != mode2);
    }

    /// <summary>
    /// Verifies that two ReturnTaskWhen instances with the same delegate are considered equal.
    /// </summary>
    [Fact]
    public void Equals_ReturnTaskWhen_SameDelegate_AreEqual()
    {
        // Arrange
        static ValueTask<bool> CallbackAsync(A2ARunDecisionContext _, CancellationToken __) => ValueTask.FromResult(true);
        var mode1 = AgentRunMode.ReturnTaskWhen(CallbackAsync);
        var mode2 = AgentRunMode.ReturnTaskWhen(CallbackAsync);

        // Act & Assert
        Assert.True(mode1.Equals(mode2));
        Assert.True(mode1 == mode2);
        Assert.Equal(mode1.GetHashCode(), mode2.GetHashCode());
    }
}
