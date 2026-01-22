// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI.Abstractions.UnitTests;

/// <summary>
/// Unit tests for <see cref="ShellToolOptions"/>.
/// </summary>
public class ShellToolOptionsTests
{
    [Fact]
    public void Constructor_WithDefaults_HasExpectedValues()
    {
        // Arrange & Act
        var options = new ShellToolOptions();

        // Assert
        Assert.Null(options.WorkingDirectory);
        Assert.Equal(60000, options.TimeoutInMilliseconds);
        Assert.Equal(51200, options.MaxOutputLength);
        Assert.Null(options.AllowedCommands);
        Assert.Null(options.DeniedCommands);
        Assert.True(options.BlockPrivilegeEscalation);
        Assert.True(options.BlockCommandChaining);
        Assert.True(options.BlockDangerousPatterns);
        Assert.Null(options.BlockedPaths);
        Assert.Null(options.AllowedPaths);
        Assert.Null(options.Shell);
    }

    [Fact]
    public void BlockCommandChaining_CanBeDisabled()
    {
        // Arrange
        var options = new ShellToolOptions
        {
            BlockCommandChaining = false
        };

        // Assert
        Assert.False(options.BlockCommandChaining);
    }

    [Fact]
    public void BlockDangerousPatterns_CanBeDisabled()
    {
        // Arrange
        var options = new ShellToolOptions
        {
            BlockDangerousPatterns = false
        };

        // Assert
        Assert.False(options.BlockDangerousPatterns);
    }

    [Fact]
    public void BlockedPaths_CanBeConfigured()
    {
        // Arrange
        var options = new ShellToolOptions
        {
            BlockedPaths = ["/etc", "/var/log"]
        };

        // Assert
        Assert.NotNull(options.BlockedPaths);
        Assert.Equal(2, options.BlockedPaths.Count);
        Assert.Contains("/etc", options.BlockedPaths);
        Assert.Contains("/var/log", options.BlockedPaths);
    }

    [Fact]
    public void AllowedPaths_CanBeConfigured()
    {
        // Arrange
        var options = new ShellToolOptions
        {
            AllowedPaths = ["/tmp", "/home/user"]
        };

        // Assert
        Assert.NotNull(options.AllowedPaths);
        Assert.Equal(2, options.AllowedPaths.Count);
        Assert.Contains("/tmp", options.AllowedPaths);
        Assert.Contains("/home/user", options.AllowedPaths);
    }
}
