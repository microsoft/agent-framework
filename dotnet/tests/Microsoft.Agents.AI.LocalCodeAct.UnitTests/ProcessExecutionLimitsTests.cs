// Copyright (c) Microsoft Corporation. All rights reserved.
// Licensed under the MIT License.

using Xunit;

namespace Microsoft.Agents.AI.LocalCodeAct.UnitTests;

/// <summary>
/// Tests for ProcessExecutionLimits record.
/// </summary>
public sealed class ProcessExecutionLimitsTests
{
    [Fact]
    public void DefaultValues_AreSet()
    {
        // Arrange & Act
        var limits = new ProcessExecutionLimits();

        // Assert
        Assert.Equal(30, limits.TimeoutSeconds);
        Assert.Equal(10 * 1024 * 1024, limits.MaxStdoutBytes);
        Assert.Equal(10 * 1024 * 1024, limits.MaxStderrBytes);
        Assert.Equal(1024 * 1024, limits.MaxFileBytesPerFile);
        Assert.Equal(10 * 1024 * 1024, limits.MaxFileBytesTotal);
    }

    [Fact]
    public void CustomValues_CanBeSet()
    {
        // Arrange & Act
        var limits = new ProcessExecutionLimits
        {
            TimeoutSeconds = 5,
            MaxStdoutBytes = 1024,
            MaxStderrBytes = 512,
            MaxFileBytesPerFile = 256,
            MaxFileBytesTotal = 2048,
        };

        // Assert
        Assert.Equal(5, limits.TimeoutSeconds);
        Assert.Equal(1024, limits.MaxStdoutBytes);
        Assert.Equal(512, limits.MaxStderrBytes);
        Assert.Equal(256, limits.MaxFileBytesPerFile);
        Assert.Equal(2048, limits.MaxFileBytesTotal);
    }
}
