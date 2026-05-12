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
    /// Verifies that AllowBackgroundWhen throws ArgumentNullException for null delegate.
    /// </summary>
    [Fact]
    public void AllowBackgroundWhen_NullDelegate_ThrowsArgumentNullException()
    {
        // Arrange & Act & Assert
        Assert.Throws<ArgumentNullException>(() =>
            AgentRunMode.AllowBackgroundWhen(null!));
    }

    /// <summary>
    /// Verifies that DisallowBackground equals another DisallowBackground instance.
    /// </summary>
    [Fact]
    public void Equals_DisallowBackground_AreEqual()
    {
        // Arrange
        var mode1 = AgentRunMode.DisallowBackground;
        var mode2 = AgentRunMode.DisallowBackground;

        // Act & Assert
        Assert.True(mode1.Equals(mode2));
        Assert.True(mode1 == mode2);
        Assert.False(mode1 != mode2);
        Assert.Equal(mode1.GetHashCode(), mode2.GetHashCode());
    }

    /// <summary>
    /// Verifies that AllowBackgroundIfSupported equals another AllowBackgroundIfSupported instance.
    /// </summary>
    [Fact]
    public void Equals_AllowBackgroundIfSupported_AreEqual()
    {
        // Arrange
        var mode1 = AgentRunMode.AllowBackgroundIfSupported;
        var mode2 = AgentRunMode.AllowBackgroundIfSupported;

        // Act & Assert
        Assert.True(mode1.Equals(mode2));
        Assert.True(mode1 == mode2);
    }

    /// <summary>
    /// Verifies that DisallowBackground and AllowBackgroundIfSupported are not equal.
    /// </summary>
    [Fact]
    public void Equals_DifferentModes_AreNotEqual()
    {
        // Arrange
        var disallow = AgentRunMode.DisallowBackground;
        var allow = AgentRunMode.AllowBackgroundIfSupported;

        // Act & Assert
        Assert.False(disallow.Equals(allow));
        Assert.False(disallow == allow);
        Assert.True(disallow != allow);
    }

    /// <summary>
    /// Verifies that Equals returns false for null.
    /// </summary>
    [Fact]
    public void Equals_Null_ReturnsFalse()
    {
        // Arrange
        var mode = AgentRunMode.DisallowBackground;

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
        Assert.Equal("message", AgentRunMode.DisallowBackground.ToString());
        Assert.Equal("task", AgentRunMode.AllowBackgroundIfSupported.ToString());
        Assert.Equal("dynamic", AgentRunMode.AllowBackgroundWhen((_, _) => ValueTask.FromResult(true)).ToString());
    }

    /// <summary>
    /// Verifies that Equals works correctly with object parameter.
    /// </summary>
    [Fact]
    public void Equals_WithObjectParameter_WorksCorrectly()
    {
        // Arrange
        var mode = AgentRunMode.DisallowBackground;

        // Act & Assert
        Assert.True(mode.Equals((object)AgentRunMode.DisallowBackground));
        Assert.False(mode.Equals((object)AgentRunMode.AllowBackgroundIfSupported));
        Assert.False(mode.Equals("not a run mode"));
    }

    /// <summary>
    /// Verifies that two AllowBackgroundWhen instances with different delegates are not considered equal,
    /// because equality includes delegate identity for dynamic modes.
    /// </summary>
    [Fact]
    public void Equals_AllowBackgroundWhen_DifferentDelegates_AreNotEqual()
    {
        // Arrange
        var mode1 = AgentRunMode.AllowBackgroundWhen((_, _) => ValueTask.FromResult(true));
        var mode2 = AgentRunMode.AllowBackgroundWhen((_, _) => ValueTask.FromResult(false));

        // Act & Assert
        Assert.False(mode1.Equals(mode2));
        Assert.True(mode1 != mode2);
    }

    /// <summary>
    /// Verifies that two AllowBackgroundWhen instances with the same delegate are considered equal.
    /// </summary>
    [Fact]
    public void Equals_AllowBackgroundWhen_SameDelegate_AreEqual()
    {
        // Arrange
        static ValueTask<bool> CallbackAsync(A2ARunDecisionContext _, CancellationToken __) => ValueTask.FromResult(true);
        var mode1 = AgentRunMode.AllowBackgroundWhen(CallbackAsync);
        var mode2 = AgentRunMode.AllowBackgroundWhen(CallbackAsync);

        // Act & Assert
        Assert.True(mode1.Equals(mode2));
        Assert.True(mode1 == mode2);
        Assert.Equal(mode1.GetHashCode(), mode2.GetHashCode());
    }
}
