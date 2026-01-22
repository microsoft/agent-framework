// Copyright (c) Microsoft. All rights reserved.

using System;
using System.IO;
using System.Runtime.InteropServices;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI;

namespace Microsoft.Agents.AI.Shell.Local.IntegrationTests;

/// <summary>
/// Integration tests for <see cref="LocalShellExecutor"/>.
/// </summary>
public class LocalShellExecutorTests
{
    private static readonly string[] s_nonExistentCommand = ["this_command_does_not_exist_12345"];
    private static readonly string[] s_powershellCommand = ["-Command Write-Output 'hello'"];

    private readonly LocalShellExecutor _executor;
    private readonly ShellToolOptions _options;

    public LocalShellExecutorTests()
    {
        _executor = new LocalShellExecutor();
        _options = new ShellToolOptions
        {
            TimeoutInMilliseconds = 30000,
            MaxOutputLength = 51200
        };
    }

    [Fact]
    public async Task ExecuteAsync_WithSimpleEchoCommand_ReturnsExpectedOutput()
    {
        // Arrange
        string command = RuntimeInformation.IsOSPlatform(OSPlatform.Windows)
            ? "echo hello"
            : "echo hello";

        // Act
        var results = await _executor.ExecuteAsync(new[] { command }, _options);

        // Assert
        Assert.Single(results);
        Assert.Equal(command, results[0].Command);
        Assert.Equal(0, results[0].ExitCode);
        Assert.Contains("hello", results[0].StandardOutput);
        Assert.False(results[0].IsTimedOut);
    }

    [Fact]
    public async Task ExecuteAsync_WithNonZeroExitCode_CapturesExitCode()
    {
        // Arrange
        string command = RuntimeInformation.IsOSPlatform(OSPlatform.Windows)
            ? "cmd /c exit 42"
            : "exit 42";

        // Act
        var results = await _executor.ExecuteAsync(new[] { command }, _options);

        // Assert
        Assert.Single(results);
        Assert.Equal(42, results[0].ExitCode);
    }

    [Fact]
    public async Task ExecuteAsync_WithStderrOutput_CapturesStandardError()
    {
        // Arrange
        string command = RuntimeInformation.IsOSPlatform(OSPlatform.Windows)
            ? "cmd /c echo error message 1>&2"
            : "echo error message >&2";

        // Act
        var results = await _executor.ExecuteAsync(new[] { command }, _options);

        // Assert
        Assert.Single(results);
        Assert.Contains("ERROR", results[0].StandardError?.ToUpperInvariant() ?? string.Empty);
    }

    [Fact]
    public async Task ExecuteAsync_WithMultipleCommands_ExecutesAllInSequence()
    {
        // Arrange
        string[] commands = RuntimeInformation.IsOSPlatform(OSPlatform.Windows)
            ? ["echo first", "echo second", "echo third"]
            : ["echo first", "echo second", "echo third"];

        // Act
        var results = await _executor.ExecuteAsync(commands, _options);

        // Assert
        Assert.Equal(3, results.Count);
        Assert.Contains("first", results[0].StandardOutput);
        Assert.Contains("second", results[1].StandardOutput);
        Assert.Contains("third", results[2].StandardOutput);
    }

    [Fact]
    public async Task ExecuteAsync_WithCustomWorkingDirectory_UsesSpecifiedDirectory()
    {
        // Arrange
        string tempDir = Path.GetTempPath();
        var options = new ShellToolOptions
        {
            WorkingDirectory = tempDir,
            TimeoutInMilliseconds = 30000,
            MaxOutputLength = 51200
        };

        string command = RuntimeInformation.IsOSPlatform(OSPlatform.Windows)
            ? "cd"
            : "pwd";

        // Act
        var results = await _executor.ExecuteAsync(new[] { command }, options);

        // Assert
        Assert.Single(results);
        // Normalize paths for comparison
        var outputPath = results[0].StandardOutput?.Trim().TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar);
        var expectedPath = tempDir.TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar);
        Assert.Equal(expectedPath, outputPath, ignoreCase: RuntimeInformation.IsOSPlatform(OSPlatform.Windows));
    }

    [Fact]
    public async Task ExecuteAsync_WithShortTimeout_TimesOutLongRunningCommand()
    {
        // Arrange
        var options = new ShellToolOptions
        {
            TimeoutInMilliseconds = 100, // Very short timeout
            MaxOutputLength = 51200
        };

        // Command that sleeps longer than timeout
        string command = RuntimeInformation.IsOSPlatform(OSPlatform.Windows)
            ? "ping -n 10 127.0.0.1"
            : "sleep 10";

        // Act
        var results = await _executor.ExecuteAsync(new[] { command }, options);

        // Assert
        Assert.Single(results);
        Assert.True(results[0].IsTimedOut);
        Assert.Null(results[0].ExitCode); // No exit code when timed out
    }

    [Fact]
    public async Task ExecuteAsync_WithSmallMaxOutputLength_TruncatesLargeOutput()
    {
        // Arrange
        var options = new ShellToolOptions
        {
            TimeoutInMilliseconds = 30000,
            MaxOutputLength = 100 // Very small output limit
        };

        // Command that generates lots of output
        string command = RuntimeInformation.IsOSPlatform(OSPlatform.Windows)
            ? "cmd /c \"for /L %i in (1,1,1000) do @echo Line %i\""
            : "for i in $(seq 1 1000); do echo Line $i; done";

        // Act
        var results = await _executor.ExecuteAsync(new[] { command }, options);

        // Assert
        Assert.Single(results);
        Assert.True(results[0].IsTruncated);
        Assert.True(results[0].StandardOutput?.Length <= options.MaxOutputLength);
    }

    [Fact]
    public async Task ExecuteAsync_WithNonExistentCommand_ReturnsErrorOrNonZeroExitCode()
    {
        // Act
        var results = await _executor.ExecuteAsync(s_nonExistentCommand, _options);

        // Assert
        Assert.Single(results);
        // Either returns error in stderr or has non-zero exit code
        Assert.True(
            results[0].ExitCode != 0 ||
            !string.IsNullOrEmpty(results[0].StandardError) ||
            !string.IsNullOrEmpty(results[0].Error));
    }

    [Fact]
    public async Task ExecuteAsync_WithCustomShell_UsesSpecifiedShell()
    {
        // Skip on non-Windows for this specific test
        if (!RuntimeInformation.IsOSPlatform(OSPlatform.Windows))
        {
            return;
        }

        // Arrange
        var options = new ShellToolOptions
        {
            Shell = "powershell.exe",
            TimeoutInMilliseconds = 30000,
            MaxOutputLength = 51200
        };

        // Act
        var results = await _executor.ExecuteAsync(s_powershellCommand, options);

        // Assert
        Assert.Single(results);
        Assert.Contains("hello", results[0].StandardOutput);
    }

    [Fact]
    public async Task ExecuteAsync_WithCancellationToken_ThrowsOperationCanceledException()
    {
        // Arrange
        using var cts = new CancellationTokenSource();

        // Command that sleeps
        string command = RuntimeInformation.IsOSPlatform(OSPlatform.Windows)
            ? "ping -n 100 127.0.0.1"
            : "sleep 100";

        // Cancel after a short delay
        cts.CancelAfter(100);

        // Act & Assert - TaskCanceledException derives from OperationCanceledException
        await Assert.ThrowsAnyAsync<OperationCanceledException>(() =>
            _executor.ExecuteAsync(new[] { command }, _options, cts.Token));
    }

    [Fact]
    public async Task ExecuteAsync_WithEmptyCommandList_ReturnsEmptyList()
    {
        // Act
        var results = await _executor.ExecuteAsync(Array.Empty<string>(), _options);

        // Assert
        Assert.Empty(results);
    }
}
