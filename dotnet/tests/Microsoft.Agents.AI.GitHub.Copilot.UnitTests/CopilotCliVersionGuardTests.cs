// Copyright (c) Microsoft. All rights reserved.

using System;

namespace Microsoft.Agents.AI.GitHub.Copilot.UnitTests;

/// <summary>
/// Unit tests for the <see cref="CopilotCliVersionGuard"/> class.
/// </summary>
public sealed class CopilotCliVersionGuardTests
{
    [Theory]
    [InlineData("1.0.85")]
    [InlineData("1.0.85-3")]
    [InlineData("1.0.90-0.unstable.abc")]
    [InlineData("v1.0.106")]
    [InlineData("2.0.0")]
    public void EnsureSupported_WithSupportedVersion_DoesNotThrow(string version)
    {
        // Act & Assert
        CopilotCliVersionGuard.EnsureSupported(version);
    }

    [Theory]
    [InlineData("1.0.64")]
    [InlineData("1.0.84")]
    [InlineData("0.9.999")]
    [InlineData("dev")]
    [InlineData("")]
    [InlineData(null)]
    public void EnsureSupported_WithUnsupportedOrUnreadableVersion_Throws(string? version)
    {
        // Act
        InvalidOperationException exception = Assert.Throws<InvalidOperationException>(
            () => CopilotCliVersionGuard.EnsureSupported(version));

        // Assert
        Assert.Contains("1.0.85 or higher is required", exception.Message);
        Assert.Contains($"'{version}'", exception.Message);
    }

    [Fact]
    public void CreateUndeterminedVersionException_KeepsInnerException()
    {
        // Arrange
        Exception inner = new InvalidOperationException("not connected");

        // Act
        InvalidOperationException exception = CopilotCliVersionGuard.CreateUndeterminedVersionException(inner);

        // Assert
        Assert.Contains("version could not be determined", exception.Message);
        Assert.Same(inner, exception.InnerException);
    }
}
