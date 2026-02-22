// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
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
    private static readonly string[] s_mixedCommands = ["safe command", "dangerous command"];

    // Command chaining test arrays
    private static readonly string[] s_echoHelloEchoWorldCommand = ["echo hello; echo world"];
    private static readonly string[] s_rmRfSlashCommand = ["rm -rf /"];

    // Path access control test arrays
    private static readonly string[] s_catEtcPasswdCommand = ["cat /etc/passwd"];
    private static readonly string[] s_catTmpFileCommand = ["cat /tmp/file.txt"];
    private static readonly string[] s_catHomeUserFileCommand = ["cat /home/user/file.txt"];
    private static readonly string[] s_catTmpSecretFileCommand = ["cat /tmp/secret/file.txt"];
    private static readonly string[] s_catAnyPathFileCommand = ["cat /any/path/file.txt"];

    // Shell wrapper test arrays
    private static readonly string[] s_nestedShellWrapperSudoCommand = ["sh -c \"bash -c 'sudo command'\""];

    private readonly Mock<ShellExecutor> _executorMock;

    public ShellToolTests()
    {
        this._executorMock = new Mock<ShellExecutor>();
        this._executorMock
            .Setup(e => e.ExecuteAsync(
                It.IsAny<IReadOnlyList<string>>(),
                It.IsAny<ShellToolOptions>(),
                It.IsAny<CancellationToken>()))
            .ReturnsAsync(
            [
                new() { Command = "test", StandardOutput = "output", ExitCode = 0 }
            ]);
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
        var tool = new ShellTool(this._executorMock.Object);

        // Assert
        Assert.Equal("shell", tool.Name);
    }

    [Fact]
    public void Description_WhenAccessed_ReturnsNonEmptyString()
    {
        // Arrange
        var tool = new ShellTool(this._executorMock.Object);

        // Assert
        Assert.False(string.IsNullOrWhiteSpace(tool.Description));
    }

    [Fact]
    public async Task ExecuteAsync_WithNullCallContent_ThrowsArgumentNullExceptionAsync()
    {
        // Arrange
        var tool = new ShellTool(this._executorMock.Object);

        // Act & Assert
        await Assert.ThrowsAsync<ArgumentNullException>(() =>
            tool.ExecuteAsync(null!));
    }

    [Fact]
    public async Task ExecuteAsync_WithCommandMatchingDenylist_ThrowsInvalidOperationExceptionAsync()
    {
        // Arrange
        var options = new ShellToolOptions
        {
            DeniedCommands = [@"rm\s+-rf"]
        };
        var tool = new ShellTool(this._executorMock.Object, options);
        var callContent = new ShellCallContent("call-1", s_rmRfCommand);

        // Act & Assert
        var ex = await Assert.ThrowsAsync<InvalidOperationException>(() =>
            tool.ExecuteAsync(callContent));
        Assert.Contains("DENYLIST", ex.Message.ToUpperInvariant());
    }

    [Fact]
    public async Task ExecuteAsync_WithCommandNotMatchingAllowlist_ThrowsInvalidOperationExceptionAsync()
    {
        // Arrange
        var options = new ShellToolOptions
        {
            AllowedCommands = ["^git\\s", "^npm\\s"]
        };
        var tool = new ShellTool(this._executorMock.Object, options);
        var callContent = new ShellCallContent("call-1", s_curlCommand);

        // Act & Assert
        var ex = await Assert.ThrowsAsync<InvalidOperationException>(() =>
            tool.ExecuteAsync(callContent));
        Assert.Contains("ALLOWLIST", ex.Message.ToUpperInvariant());
    }

    [Fact]
    public async Task ExecuteAsync_WithCommandMatchingAllowlist_ReturnsResultAsync()
    {
        // Arrange
        var options = new ShellToolOptions
        {
            AllowedCommands = ["^git\\s"]
        };
        var tool = new ShellTool(this._executorMock.Object, options);
        var callContent = new ShellCallContent("call-1", s_gitStatusCommand);

        // Act
        var result = await tool.ExecuteAsync(callContent);

        // Assert
        Assert.NotNull(result);
        Assert.Equal("call-1", result.CallId);
    }

    [Fact]
    public async Task ExecuteAsync_WithCommandMatchingBothLists_PrioritizesDenylistAsync()
    {
        // Arrange - Command matches both allowlist and denylist
        var options = new ShellToolOptions
        {
            AllowedCommands = [".*"], // Allow everything
            DeniedCommands = ["rm"]   // But deny rm
        };
        var tool = new ShellTool(this._executorMock.Object, options);
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
    public async Task ExecuteAsync_WithPrivilegeEscalationCommand_ThrowsInvalidOperationExceptionAsync(string command)
    {
        // Arrange
        var tool = new ShellTool(this._executorMock.Object);
        var callContent = new ShellCallContent("call-1", [command]);

        // Act & Assert
        var ex = await Assert.ThrowsAsync<InvalidOperationException>(() =>
            tool.ExecuteAsync(callContent));
        Assert.Contains("PRIVILEGE ESCALATION", ex.Message.ToUpperInvariant());
    }

    [Fact]
    public async Task ExecuteAsync_WithPrivilegeEscalationDisabled_AllowsSudoCommandsAsync()
    {
        // Arrange
        var options = new ShellToolOptions
        {
            BlockPrivilegeEscalation = false
        };
        var tool = new ShellTool(this._executorMock.Object, options);
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
    public async Task ExecuteAsync_WithSimilarButSafeCommands_ReturnsResultAsync(string command)
    {
        // Arrange
        var tool = new ShellTool(this._executorMock.Object);
        var callContent = new ShellCallContent("call-1", [command]);

        // Act
        var result = await tool.ExecuteAsync(callContent);

        // Assert
        Assert.NotNull(result);
    }

    [Fact]
    public async Task ExecuteAsync_WithValidCommand_ReturnsCorrectOutputAsync()
    {
        // Arrange
        var expectedOutput = new List<ShellExecutorOutput>
        {
            new() { Command = "echo hello", StandardOutput = "hello\n", ExitCode = 0 }
        };
        this._executorMock
            .Setup(e => e.ExecuteAsync(
                It.IsAny<IReadOnlyList<string>>(),
                It.IsAny<ShellToolOptions>(),
                It.IsAny<CancellationToken>()))
            .ReturnsAsync(expectedOutput);

        var tool = new ShellTool(this._executorMock.Object);
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
    public async Task ExecuteAsync_WithMultipleCommands_ValidatesAllBeforeExecutionAsync()
    {
        // Arrange
        var options = new ShellToolOptions
        {
            DeniedCommands = ["dangerous"]
        };
        var tool = new ShellTool(this._executorMock.Object, options);
        var callContent = new ShellCallContent("call-1", s_mixedCommands);

        // Act & Assert - Should fail on second command before executing any
        await Assert.ThrowsAsync<InvalidOperationException>(() =>
            tool.ExecuteAsync(callContent));

        // Verify executor was never called
        this._executorMock.Verify(
            e => e.ExecuteAsync(
                It.IsAny<IReadOnlyList<string>>(),
                It.IsAny<ShellToolOptions>(),
                It.IsAny<CancellationToken>()),
            Times.Never);
    }

    #region Command Chaining Tests

    [Theory]
    [InlineData("echo hello; echo world")]
    [InlineData("cat file | grep pattern")]
    [InlineData("test && echo success")]
    [InlineData("test || echo failure")]
    [InlineData("echo $(whoami)")]
    [InlineData("echo `whoami`")]
    public async Task ExecuteAsync_WithCommandChaining_ThrowsInvalidOperationExceptionAsync(string command)
    {
        // Arrange
        var tool = new ShellTool(this._executorMock.Object);
        var callContent = new ShellCallContent("call-1", [command]);

        // Act & Assert
        var ex = await Assert.ThrowsAsync<InvalidOperationException>(() =>
            tool.ExecuteAsync(callContent));
        Assert.Contains("CHAINING", ex.Message.ToUpperInvariant());
    }

    [Theory]
    [InlineData("echo \"semicolon; in quotes\"")]
    [InlineData("echo 'pipe | in single quotes'")]
    [InlineData("echo \"ampersand && in quotes\"")]
    [InlineData("echo \"dollar $(in quotes)\"")]
    public async Task ExecuteAsync_WithOperatorsInQuotes_ReturnsResultAsync(string command)
    {
        // Arrange
        var options = new ShellToolOptions
        {
            BlockDangerousPatterns = false // Allow dangerous patterns for this test
        };
        var tool = new ShellTool(this._executorMock.Object, options);
        var callContent = new ShellCallContent("call-1", [command]);

        // Act
        var result = await tool.ExecuteAsync(callContent);

        // Assert
        Assert.NotNull(result);
    }

    [Fact]
    public async Task ExecuteAsync_WithCommandChainingDisabled_AllowsChainingOperatorsAsync()
    {
        // Arrange
        var options = new ShellToolOptions
        {
            BlockCommandChaining = false,
            BlockDangerousPatterns = false
        };
        var tool = new ShellTool(this._executorMock.Object, options);
        var callContent = new ShellCallContent("call-1", s_echoHelloEchoWorldCommand);

        // Act
        var result = await tool.ExecuteAsync(callContent);

        // Assert
        Assert.NotNull(result);
    }

    #endregion

    #region Dangerous Patterns Tests

    [Theory]
    [InlineData(":(){ :|:& };:")]
    [InlineData("rm -rf /")]
    [InlineData("rm -rf /*")]
    [InlineData("rm -r /")]
    [InlineData("rm -f /")]
    [InlineData("mkfs.ext4 /dev/sda")]
    [InlineData("dd if=/dev/zero of=/dev/sda")]
    [InlineData("> /dev/sda")]
    [InlineData("chmod 777 /")]
    [InlineData("chmod -R 777 /")]
    public async Task ExecuteAsync_WithDangerousPattern_ThrowsInvalidOperationExceptionAsync(string command)
    {
        // Arrange
        var options = new ShellToolOptions
        {
            BlockCommandChaining = false // Disable chaining detection for these tests
        };
        var tool = new ShellTool(this._executorMock.Object, options);
        var callContent = new ShellCallContent("call-1", [command]);

        // Act & Assert
        var ex = await Assert.ThrowsAsync<InvalidOperationException>(() =>
            tool.ExecuteAsync(callContent));
        Assert.Contains("DANGEROUS", ex.Message.ToUpperInvariant());
    }

    [Fact]
    public async Task ExecuteAsync_WithDangerousPatternsDisabled_AllowsDangerousCommandsAsync()
    {
        // Arrange
        var options = new ShellToolOptions
        {
            BlockDangerousPatterns = false,
            BlockCommandChaining = false
        };
        var tool = new ShellTool(this._executorMock.Object, options);
        var callContent = new ShellCallContent("call-1", s_rmRfSlashCommand);

        // Act
        var result = await tool.ExecuteAsync(callContent);

        // Assert
        Assert.NotNull(result);
    }

    #endregion

    #region Token-Based Privilege Escalation Tests

    [Theory]
    [InlineData("/usr/bin/sudo apt install")]
    [InlineData("\"/usr/bin/sudo\" command")]
    [InlineData("C:\\Windows\\System32\\runas.exe /user:admin cmd")]
    public async Task ExecuteAsync_WithPrivilegeEscalationInPath_ThrowsInvalidOperationExceptionAsync(string command)
    {
        // Arrange
        var options = new ShellToolOptions
        {
            BlockCommandChaining = false
        };
        var tool = new ShellTool(this._executorMock.Object, options);
        var callContent = new ShellCallContent("call-1", [command]);

        // Act & Assert
        var ex = await Assert.ThrowsAsync<InvalidOperationException>(() =>
            tool.ExecuteAsync(callContent));
        Assert.Contains("PRIVILEGE ESCALATION", ex.Message.ToUpperInvariant());
    }

    [Theory]
    [InlineData("/usr/bin/mysudo command")]  // "mysudo" is not "sudo"
    [InlineData("sudo-like command")]         // Not the sudo command
    public async Task ExecuteAsync_WithSimilarToPrivilegeEscalation_ReturnsResultAsync(string command)
    {
        // Arrange
        var options = new ShellToolOptions
        {
            BlockCommandChaining = false
        };
        var tool = new ShellTool(this._executorMock.Object, options);
        var callContent = new ShellCallContent("call-1", [command]);

        // Act
        var result = await tool.ExecuteAsync(callContent);

        // Assert
        Assert.NotNull(result);
    }

    #endregion

    #region Shell Wrapper Privilege Escalation Tests

    [Theory]
    [InlineData("sh -c \"sudo apt install\"")]
    [InlineData("bash -c \"sudo apt update\"")]
    [InlineData("/bin/sh -c \"sudo command\"")]
    [InlineData("/usr/bin/bash -c \"doas command\"")]
    [InlineData("zsh -c \"pkexec command\"")]
    [InlineData("dash -c 'su -'")]
    public async Task ExecuteAsync_WithShellWrapperContainingPrivilegeEscalation_ThrowsInvalidOperationExceptionAsync(string command)
    {
        // Arrange
        var options = new ShellToolOptions
        {
            BlockCommandChaining = false // Disable chaining to test privilege escalation detection
        };
        var tool = new ShellTool(this._executorMock.Object, options);
        var callContent = new ShellCallContent("call-1", [command]);

        // Act & Assert
        var ex = await Assert.ThrowsAsync<InvalidOperationException>(() =>
            tool.ExecuteAsync(callContent));
        Assert.Contains("PRIVILEGE ESCALATION", ex.Message.ToUpperInvariant());
    }

    [Theory]
    [InlineData("sh -c \"echo hello\"")]
    [InlineData("bash -c \"ls -la\"")]
    [InlineData("/bin/sh -c \"cat file.txt\"")]
    public async Task ExecuteAsync_WithShellWrapperContainingSafeCommand_ReturnsResultAsync(string command)
    {
        // Arrange
        var options = new ShellToolOptions
        {
            BlockCommandChaining = false // Disable chaining to test shell wrappers
        };
        var tool = new ShellTool(this._executorMock.Object, options);
        var callContent = new ShellCallContent("call-1", [command]);

        // Act
        var result = await tool.ExecuteAsync(callContent);

        // Assert
        Assert.NotNull(result);
    }

    [Fact]
    public async Task ExecuteAsync_WithNestedShellWrapperContainingPrivilegeEscalation_ThrowsInvalidOperationExceptionAsync()
    {
        // Arrange - Nested shell wrapper with privilege escalation
        var options = new ShellToolOptions
        {
            BlockCommandChaining = false
        };
        var tool = new ShellTool(this._executorMock.Object, options);
        var callContent = new ShellCallContent("call-1", s_nestedShellWrapperSudoCommand);

        // Act & Assert
        var ex = await Assert.ThrowsAsync<InvalidOperationException>(() =>
            tool.ExecuteAsync(callContent));
        Assert.Contains("PRIVILEGE ESCALATION", ex.Message.ToUpperInvariant());
    }

    #endregion

    #region Path-Based Access Control Tests

    [Fact]
    public async Task ExecuteAsync_WithBlockedPath_ThrowsInvalidOperationExceptionAsync()
    {
        // Arrange
        var options = new ShellToolOptions
        {
            BlockedPaths = ["/etc"],
            BlockCommandChaining = false
        };
        var tool = new ShellTool(this._executorMock.Object, options);
        var callContent = new ShellCallContent("call-1", s_catEtcPasswdCommand);

        // Act & Assert
        var ex = await Assert.ThrowsAsync<InvalidOperationException>(() =>
            tool.ExecuteAsync(callContent));
        Assert.Contains("BLOCKED", ex.Message.ToUpperInvariant());
    }

    [Fact]
    public async Task ExecuteAsync_WithAllowedPath_ReturnsResultAsync()
    {
        // Arrange
        var options = new ShellToolOptions
        {
            AllowedPaths = ["/tmp"],
            BlockCommandChaining = false
        };
        var tool = new ShellTool(this._executorMock.Object, options);
        var callContent = new ShellCallContent("call-1", s_catTmpFileCommand);

        // Act
        var result = await tool.ExecuteAsync(callContent);

        // Assert
        Assert.NotNull(result);
    }

    [Fact]
    public async Task ExecuteAsync_WithPathNotInAllowedList_ThrowsInvalidOperationExceptionAsync()
    {
        // Arrange
        var options = new ShellToolOptions
        {
            AllowedPaths = ["/tmp"],
            BlockCommandChaining = false
        };
        var tool = new ShellTool(this._executorMock.Object, options);
        var callContent = new ShellCallContent("call-1", s_catHomeUserFileCommand);

        // Act & Assert
        var ex = await Assert.ThrowsAsync<InvalidOperationException>(() =>
            tool.ExecuteAsync(callContent));
        Assert.Contains("NOT ALLOWED", ex.Message.ToUpperInvariant());
    }

    [Fact]
    public async Task ExecuteAsync_WithBlockedPathTakesPriorityOverAllowed_ThrowsInvalidOperationExceptionAsync()
    {
        // Arrange
        var options = new ShellToolOptions
        {
            BlockedPaths = ["/tmp/secret"],
            AllowedPaths = ["/tmp"],
            BlockCommandChaining = false
        };
        var tool = new ShellTool(this._executorMock.Object, options);
        var callContent = new ShellCallContent("call-1", s_catTmpSecretFileCommand);

        // Act & Assert
        var ex = await Assert.ThrowsAsync<InvalidOperationException>(() =>
            tool.ExecuteAsync(callContent));
        Assert.Contains("BLOCKED", ex.Message.ToUpperInvariant());
    }

    [Fact]
    public async Task ExecuteAsync_WithNoPathRestrictions_ReturnsResultAsync()
    {
        // Arrange
        var options = new ShellToolOptions
        {
            BlockCommandChaining = false
        };
        var tool = new ShellTool(this._executorMock.Object, options);
        var callContent = new ShellCallContent("call-1", s_catAnyPathFileCommand);

        // Act
        var result = await tool.ExecuteAsync(callContent);

        // Assert
        Assert.NotNull(result);
    }

    [Theory]
    [InlineData("cat ../../../etc/passwd")]
    [InlineData("cat ./../../etc/passwd")]
    [InlineData("ls ../secret")]
    public async Task ExecuteAsync_WithRelativePathTraversal_ThrowsInvalidOperationExceptionAsync(string command)
    {
        // Arrange
        var options = new ShellToolOptions
        {
            WorkingDirectory = "/tmp/safe",
            AllowedPaths = ["/tmp/safe"],
            BlockCommandChaining = false
        };
        var tool = new ShellTool(this._executorMock.Object, options);
        var callContent = new ShellCallContent("call-1", [command]);

        // Act & Assert
        var ex = await Assert.ThrowsAsync<InvalidOperationException>(() =>
            tool.ExecuteAsync(callContent));
        Assert.Contains("NOT ALLOWED", ex.Message.ToUpperInvariant());
    }

    [Theory]
    [InlineData("cat ./file.txt")]
    [InlineData("ls ./subdir")]
    [InlineData("cat subdir/file.txt")]
    public async Task ExecuteAsync_WithRelativePathWithinAllowed_ReturnsResultAsync(string command)
    {
        // Arrange
        var options = new ShellToolOptions
        {
            WorkingDirectory = "/tmp/safe",
            AllowedPaths = ["/tmp/safe"],
            BlockCommandChaining = false
        };
        var tool = new ShellTool(this._executorMock.Object, options);
        var callContent = new ShellCallContent("call-1", [command]);

        // Act
        var result = await tool.ExecuteAsync(callContent);

        // Assert
        Assert.NotNull(result);
    }

    #endregion
}
