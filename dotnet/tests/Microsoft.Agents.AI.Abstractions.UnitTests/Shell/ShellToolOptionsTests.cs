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
    public void AllowedCommands_WithValidRegexPatterns_CompilesSuccessfully()
    {
        // Arrange
        var options = new ShellToolOptions
        {
            AllowedCommands = ["^git\\s", "^npm\\s", "^dotnet\\s"]
        };

        // Assert
        Assert.NotNull(options.CompiledAllowedPatterns);
        Assert.Equal(3, options.CompiledAllowedPatterns.Count);
    }

    [Fact]
    public void AllowedCommands_WithInvalidRegex_TreatsAsLiteralString()
    {
        // Arrange - "[" is an invalid regex pattern
        var options = new ShellToolOptions
        {
            AllowedCommands = ["[invalid"]
        };

        // Assert - Should not throw, should treat as literal
        Assert.NotNull(options.CompiledAllowedPatterns);
        Assert.Single(options.CompiledAllowedPatterns);

        // The literal "[invalid" should be escaped and match exactly
        Assert.Matches(options.CompiledAllowedPatterns[0], "[invalid");
        Assert.DoesNotMatch(options.CompiledAllowedPatterns[0], "invalid");
    }

    [Fact]
    public void DeniedCommands_WithValidRegexPatterns_CompilesSuccessfully()
    {
        // Arrange
        var options = new ShellToolOptions
        {
            DeniedCommands = [@"rm\s+-rf", "chmod", "chown"]
        };

        // Assert
        Assert.NotNull(options.CompiledDeniedPatterns);
        Assert.Equal(3, options.CompiledDeniedPatterns.Count);
    }

    [Fact]
    public void CompiledPatterns_WithMixedCaseInput_MatchesCaseInsensitively()
    {
        // Arrange
        var options = new ShellToolOptions
        {
            AllowedCommands = ["^GIT"]
        };

        // Assert
        Assert.NotNull(options.CompiledAllowedPatterns);
        Assert.Matches(options.CompiledAllowedPatterns[0], "git status");
        Assert.Matches(options.CompiledAllowedPatterns[0], "GIT status");
        Assert.Matches(options.CompiledAllowedPatterns[0], "Git status");
    }

    [Fact]
    public void CompiledAllowedPatterns_WithEmptyList_ReturnsNull()
    {
        // Arrange
        var options = new ShellToolOptions
        {
            AllowedCommands = []
        };

        // Assert
        Assert.Null(options.CompiledAllowedPatterns);
    }

    [Fact]
    public void CompiledAllowedPatterns_WithNullList_ReturnsNull()
    {
        // Arrange
        var options = new ShellToolOptions
        {
            AllowedCommands = null
        };

        // Assert
        Assert.Null(options.CompiledAllowedPatterns);
    }

    [Fact]
    public void AllowedCommands_WhenUpdated_RecompilesPatterns()
    {
        // Arrange
        var options = new ShellToolOptions
        {
            AllowedCommands = ["^git"]
        };

        // Assert initial state
        Assert.NotNull(options.CompiledAllowedPatterns);
        Assert.Single(options.CompiledAllowedPatterns);

        // Act - Update the list
        options.AllowedCommands = ["^npm", "^yarn"];

        // Assert - Patterns should be updated
        Assert.NotNull(options.CompiledAllowedPatterns);
        Assert.Equal(2, options.CompiledAllowedPatterns.Count);
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
