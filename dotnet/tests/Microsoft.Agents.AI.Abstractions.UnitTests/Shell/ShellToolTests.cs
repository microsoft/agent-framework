// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI;
using Moq;

namespace Microsoft.Agents.AI.Abstractions.UnitTests;

/// <summary>
/// Unit tests for <see cref="ShellTool"/>.
/// </summary>
public class ShellToolTests
{
    private static readonly string[] s_rmRfCommand = ["rm -rf /"];
    private static readonly string[] s_curlCommand = ["curl http://example.com"];
    private static readonly string[] s_gitStatusCommand = ["git status"];
    private static readonly string[] s_rmFileCommand = ["rm file.txt"];
    private static readonly string[] s_sudoAptInstallCommand = ["sudo apt install"];
    private static readonly string[] s_echoHelloCommand = ["echo hello"];
    private static readonly string[] s_testCommand = ["test"];
    private static readonly string[] s_mixedCommands = ["safe command", "dangerous command"];

    private readonly Mock<ShellExecutor> _executorMock;

    public ShellToolTests()
    {
        _executorMock = new Mock<ShellExecutor>();
        _executorMock
            .Setup(e => e.ExecuteAsync(
                It.IsAny<IReadOnlyList<string>>(),
                It.IsAny<ShellToolOptions>(),
                It.IsAny<CancellationToken>()))
            .ReturnsAsync(new List<ShellExecutorOutput>
            {
                new() { Command = "test", StandardOutput = "output", ExitCode = 0 }
            });
    }

    [Fact]
    public void Constructor_WithNullExecutor_ThrowsArgumentNullException()
    {
        // Act & Assert
        Assert.Throws<ArgumentNullException>(() => new ShellTool(null!));
    }

    [Fact]
    public void Name_WhenAccessed_ReturnsShell()
    {
        // Arrange
        var tool = new ShellTool(_executorMock.Object);

        // Assert
        Assert.Equal("shell", tool.Name);
    }

    [Fact]
    public void Description_WhenAccessed_ReturnsNonEmptyString()
    {
        // Arrange
        var tool = new ShellTool(_executorMock.Object);

        // Assert
        Assert.False(string.IsNullOrWhiteSpace(tool.Description));
    }

    [Fact]
    public async Task ExecuteAsync_WithNullCallContent_ThrowsArgumentNullException()
    {
        // Arrange
        var tool = new ShellTool(_executorMock.Object);

        // Act & Assert
        await Assert.ThrowsAsync<ArgumentNullException>(() =>
            tool.ExecuteAsync(null!));
    }

    [Fact]
    public async Task ExecuteAsync_WithCommandMatchingDenylist_ThrowsInvalidOperationException()
    {
        // Arrange
        var options = new ShellToolOptions
        {
            DeniedCommands = new List<string> { @"rm\s+-rf" }
        };
        var tool = new ShellTool(_executorMock.Object, options);
        var callContent = new ShellCallContent("call-1", s_rmRfCommand);

        // Act & Assert
        var ex = await Assert.ThrowsAsync<InvalidOperationException>(() =>
            tool.ExecuteAsync(callContent));
        Assert.Contains("DENYLIST", ex.Message.ToUpperInvariant());
    }

    [Fact]
    public async Task ExecuteAsync_WithCommandNotMatchingAllowlist_ThrowsInvalidOperationException()
    {
        // Arrange
        var options = new ShellToolOptions
        {
            AllowedCommands = new List<string> { "^git\\s", "^npm\\s" }
        };
        var tool = new ShellTool(_executorMock.Object, options);
        var callContent = new ShellCallContent("call-1", s_curlCommand);

        // Act & Assert
        var ex = await Assert.ThrowsAsync<InvalidOperationException>(() =>
            tool.ExecuteAsync(callContent));
        Assert.Contains("ALLOWLIST", ex.Message.ToUpperInvariant());
    }

    [Fact]
    public async Task ExecuteAsync_WithCommandMatchingAllowlist_ReturnsResult()
    {
        // Arrange
        var options = new ShellToolOptions
        {
            AllowedCommands = new List<string> { "^git\\s" }
        };
        var tool = new ShellTool(_executorMock.Object, options);
        var callContent = new ShellCallContent("call-1", s_gitStatusCommand);

        // Act
        var result = await tool.ExecuteAsync(callContent);

        // Assert
        Assert.NotNull(result);
        Assert.Equal("call-1", result.CallId);
    }

    [Fact]
    public async Task ExecuteAsync_WithCommandMatchingBothLists_PrioritizesDenylist()
    {
        // Arrange - Command matches both allowlist and denylist
        var options = new ShellToolOptions
        {
            AllowedCommands = new List<string> { ".*" }, // Allow everything
            DeniedCommands = new List<string> { "rm" }   // But deny rm
        };
        var tool = new ShellTool(_executorMock.Object, options);
        var callContent = new ShellCallContent("call-1", s_rmFileCommand);

        // Act & Assert - Denylist should win
        var ex = await Assert.ThrowsAsync<InvalidOperationException>(() =>
            tool.ExecuteAsync(callContent));
        Assert.Contains("DENYLIST", ex.Message.ToUpperInvariant());
    }

    [Theory]
    [InlineData("sudo apt install")]
    [InlineData("SUDO apt install")]
    [InlineData("  sudo apt install")]
    [InlineData("su -")]
    [InlineData("runas /user:admin cmd")]
    [InlineData("doas command")]
    [InlineData("pkexec command")]
    public async Task ExecuteAsync_WithPrivilegeEscalationCommand_ThrowsInvalidOperationException(string command)
    {
        // Arrange
        var tool = new ShellTool(_executorMock.Object);
        var callContent = new ShellCallContent("call-1", new[] { command });

        // Act & Assert
        var ex = await Assert.ThrowsAsync<InvalidOperationException>(() =>
            tool.ExecuteAsync(callContent));
        Assert.Contains("PRIVILEGE ESCALATION", ex.Message.ToUpperInvariant());
    }

    [Fact]
    public async Task ExecuteAsync_WithPrivilegeEscalationDisabled_AllowsSudoCommands()
    {
        // Arrange
        var options = new ShellToolOptions
        {
            BlockPrivilegeEscalation = false
        };
        var tool = new ShellTool(_executorMock.Object, options);
        var callContent = new ShellCallContent("call-1", s_sudoAptInstallCommand);

        // Act
        var result = await tool.ExecuteAsync(callContent);

        // Assert
        Assert.NotNull(result);
    }

    [Theory]
    [InlineData("sudoku game")]
    [InlineData("resume.txt")]
    [InlineData("dosomething")]
    public async Task ExecuteAsync_WithSimilarButSafeCommands_ReturnsResult(string command)
    {
        // Arrange
        var tool = new ShellTool(_executorMock.Object);
        var callContent = new ShellCallContent("call-1", new[] { command });

        // Act
        var result = await tool.ExecuteAsync(callContent);

        // Assert
        Assert.NotNull(result);
    }

    [Fact]
    public async Task ExecuteAsync_WithValidCommand_ReturnsCorrectOutput()
    {
        // Arrange
        var expectedOutput = new List<ShellExecutorOutput>
        {
            new() { Command = "echo hello", StandardOutput = "hello\n", ExitCode = 0 }
        };
        _executorMock
            .Setup(e => e.ExecuteAsync(
                It.IsAny<IReadOnlyList<string>>(),
                It.IsAny<ShellToolOptions>(),
                It.IsAny<CancellationToken>()))
            .ReturnsAsync(expectedOutput);

        var tool = new ShellTool(_executorMock.Object);
        var callContent = new ShellCallContent("call-1", s_echoHelloCommand);

        // Act
        var result = await tool.ExecuteAsync(callContent);

        // Assert
        Assert.Equal("call-1", result.CallId);
        Assert.Single(result.Output);
        Assert.Equal("echo hello", result.Output[0].Command);
        Assert.Equal("hello\n", result.Output[0].StandardOutput);
        Assert.Equal(0, result.Output[0].ExitCode);
    }

    [Fact]
    public async Task ExecuteAsync_WithTimeoutOverride_AppliesOverrideValue()
    {
        // Arrange
        var baseOptions = new ShellToolOptions
        {
            TimeoutInMilliseconds = 60000
        };
        ShellToolOptions? capturedOptions = null;
        _executorMock
            .Setup(e => e.ExecuteAsync(
                It.IsAny<IReadOnlyList<string>>(),
                It.IsAny<ShellToolOptions>(),
                It.IsAny<CancellationToken>()))
            .Callback<IReadOnlyList<string>, ShellToolOptions, CancellationToken>((_, opts, _) =>
                capturedOptions = opts)
            .ReturnsAsync(new List<ShellExecutorOutput>());

        var tool = new ShellTool(_executorMock.Object, baseOptions);
        var callContent = new ShellCallContent("call-1", s_testCommand)
        {
            TimeoutInMilliseconds = 30000
        };

        // Act
        await tool.ExecuteAsync(callContent);

        // Assert
        Assert.NotNull(capturedOptions);
        Assert.Equal(30000, capturedOptions.TimeoutInMilliseconds);
    }

    [Fact]
    public async Task ExecuteAsync_WithMaxOutputLengthOverride_AppliesOverrideValue()
    {
        // Arrange
        var baseOptions = new ShellToolOptions
        {
            MaxOutputLength = 51200
        };
        ShellToolOptions? capturedOptions = null;
        _executorMock
            .Setup(e => e.ExecuteAsync(
                It.IsAny<IReadOnlyList<string>>(),
                It.IsAny<ShellToolOptions>(),
                It.IsAny<CancellationToken>()))
            .Callback<IReadOnlyList<string>, ShellToolOptions, CancellationToken>((_, opts, _) =>
                capturedOptions = opts)
            .ReturnsAsync(new List<ShellExecutorOutput>());

        var tool = new ShellTool(_executorMock.Object, baseOptions);
        var callContent = new ShellCallContent("call-1", s_testCommand)
        {
            MaxOutputLength = 10240
        };

        // Act
        await tool.ExecuteAsync(callContent);

        // Assert
        Assert.NotNull(capturedOptions);
        Assert.Equal(10240, capturedOptions.MaxOutputLength);
    }

    [Fact]
    public async Task ExecuteAsync_WithMultipleCommands_ValidatesAllBeforeExecution()
    {
        // Arrange
        var options = new ShellToolOptions
        {
            DeniedCommands = new List<string> { "dangerous" }
        };
        var tool = new ShellTool(_executorMock.Object, options);
        var callContent = new ShellCallContent("call-1", s_mixedCommands);

        // Act & Assert - Should fail on second command before executing any
        await Assert.ThrowsAsync<InvalidOperationException>(() =>
            tool.ExecuteAsync(callContent));

        // Verify executor was never called
        _executorMock.Verify(
            e => e.ExecuteAsync(
                It.IsAny<IReadOnlyList<string>>(),
                It.IsAny<ShellToolOptions>(),
                It.IsAny<CancellationToken>()),
            Times.Never);
    }
}
