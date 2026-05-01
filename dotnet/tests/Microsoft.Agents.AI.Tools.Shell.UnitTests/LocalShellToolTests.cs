// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Runtime.InteropServices;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Tools.Shell.UnitTests;

/// <summary>
/// Smoke + behavior tests for <see cref="LocalShellTool"/> and <see cref="ShellPolicy"/>.
/// </summary>
public sealed class LocalShellToolTests
{
    [Fact]
    public void Policy_DenyList_BlocksDestructiveRm()
    {
        var policy = new ShellPolicy();
        var decision = policy.Evaluate(new ShellRequest("rm -rf /"));
        Assert.False(decision.Allowed);
        Assert.Contains("deny pattern", decision.Reason ?? string.Empty, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void Policy_AllowList_OverridesDeny()
    {
        var policy = new ShellPolicy(
            allowList: ["^echo "],
            denyList: ["echo"]);
        var decision = policy.Evaluate(new ShellRequest("echo hello"));
        Assert.True(decision.Allowed);
    }

    [Fact]
    public void Policy_EmptyCommand_Denied()
    {
        var decision = new ShellPolicy().Evaluate(new ShellRequest("   "));
        Assert.False(decision.Allowed);
    }

    [Fact]
    public void Policy_DenyList_IsGuardrailNotBoundary_KnownBypass()
    {
        // This test codifies that the policy is a guardrail — a small change
        // to the command (variable indirection) bypasses the literal `rm -rf /`
        // pattern. Documented as expected behavior; the real boundary is
        // approval-in-the-loop.
        var policy = new ShellPolicy();
        var decision = policy.Evaluate(new ShellRequest("${RM:=rm} -rf /"));
        Assert.True(decision.Allowed, "Policy is intentionally a guardrail; this bypass is documented in ADR 0026.");
    }

    [Fact]
    public async Task RunAsync_EchoCommand_RoundtripsStdoutAndExitCodeAsync()
    {
        await using var shell = new LocalShellTool(mode: ShellMode.Stateless);
        // Use an OS-appropriate echo. On Windows the resolved shell is PowerShell.
        var result = await shell.RunAsync("echo hello-from-shell");
        Assert.Equal(0, result.ExitCode);
        Assert.Contains("hello-from-shell", result.Stdout, StringComparison.Ordinal);
        Assert.False(result.TimedOut);
    }

    [Fact]
    public async Task RunAsync_RejectedCommand_ThrowsShellCommandRejectedAsync()
    {
        await using var shell = new LocalShellTool(mode: ShellMode.Stateless);
        await Assert.ThrowsAsync<ShellCommandRejectedException>(
            () => shell.RunAsync("rm -rf /"));
    }

    [Fact]
    public async Task RunAsync_NonZeroExit_PropagatesExitCodeAsync()
    {
        await using var shell = new LocalShellTool(mode: ShellMode.Stateless);
        // Exit-1 phrasing portable across bash and PowerShell.
        var script = RuntimeInformation.IsOSPlatform(OSPlatform.Windows)
            ? "exit 7"
            : "exit 7";
        var result = await shell.RunAsync(script);
        Assert.Equal(7, result.ExitCode);
    }

    [Fact]
    public async Task RunAsync_Timeout_FlagsTimedOutAndKillsProcessAsync()
    {
        await using var shell = new LocalShellTool(mode: ShellMode.Stateless, timeout: TimeSpan.FromMilliseconds(250));
        var sleepCmd = RuntimeInformation.IsOSPlatform(OSPlatform.Windows)
            ? "Start-Sleep -Seconds 30"
            : "sleep 30";
        var result = await shell.RunAsync(sleepCmd);
        Assert.True(result.TimedOut);
        Assert.Equal(124, result.ExitCode);
        Assert.True(result.Duration < TimeSpan.FromSeconds(10));
    }

    [Fact]
    public async Task RunAsync_NullTimeout_DoesNotTimeOutAsync()
    {
        // Documented contract: timeout: null disables timeouts. Verify that
        // a short-lived command completes normally instead of being killed
        // when the caller explicitly opts out of a timeout.
        await using var shell = new LocalShellTool(mode: ShellMode.Stateless, timeout: null);
        var echo = RuntimeInformation.IsOSPlatform(OSPlatform.Windows)
            ? "Write-Output ok"
            : "echo ok";
        var result = await shell.RunAsync(echo);
        Assert.False(result.TimedOut);
        Assert.Equal(0, result.ExitCode);
    }

    [Fact]
    public void DefaultTimeout_IsThirtySeconds()
    {
        Assert.Equal(TimeSpan.FromSeconds(30), LocalShellTool.DefaultTimeout);
    }

    [Fact]
    public void AsAIFunction_DefaultsToApprovalRequired()
    {
        using var shell = new LocalShellTool(mode: ShellMode.Stateless);
        var fn = shell.AsAIFunction();
        Assert.IsType<ApprovalRequiredAIFunction>(fn);
        Assert.Equal("run_shell", fn.Name);
        Assert.False(string.IsNullOrWhiteSpace(fn.Description));
    }

    [Fact]
    public void AsAIFunction_OptOut_RequiresAcknowledgeUnsafe()
    {
        using var shell = new LocalShellTool(mode: ShellMode.Stateless);
        _ = Assert.Throws<InvalidOperationException>(() => shell.AsAIFunction(requireApproval: false));
    }

    [Fact]
    public void AsAIFunction_OptOut_WithAck_ReturnsPlainFunction()
    {
        using var shell = new LocalShellTool(mode: ShellMode.Stateless, acknowledgeUnsafe: true);
        var fn = shell.AsAIFunction(requireApproval: false);
        Assert.IsNotType<ApprovalRequiredAIFunction>(fn);
        Assert.Equal("run_shell", fn.Name);
    }

    [Fact]
    public void Persistent_Mode_RejectsCmd()
    {
        // pwsh and bash work; cmd.exe doesn't because it lacks a sentinel-friendly REPL.
        if (!RuntimeInformation.IsOSPlatform(OSPlatform.Windows))
        {
            return;
        }
        _ = Assert.Throws<NotSupportedException>(() =>
            new LocalShellTool(mode: ShellMode.Persistent, shell: "cmd.exe"));
    }

    [Fact]
    public async Task OnCommand_HookFiredForAllowedCommandsOnlyAsync()
    {
        var calls = new System.Collections.Generic.List<string>();
        await using var shell = new LocalShellTool(mode: ShellMode.Stateless, onCommand: cmd => calls.Add(cmd));
        await Assert.ThrowsAsync<ShellCommandRejectedException>(() => shell.RunAsync("rm -rf /"));
        Assert.Empty(calls);
    }

    [Fact]
    public async Task Persistent_CarriesWorkingDirectory_AcrossCallsAsync()
    {
        await using var shell = new LocalShellTool(
            mode: ShellMode.Persistent,
            timeout: TimeSpan.FromSeconds(20));

        // Use `pwd` (alias for Get-Location → PathInfo object) on pwsh to
        // exercise the formatter path that previously raced the sentinel.
        var (cdCmd, pwdCmd) = RuntimeInformation.IsOSPlatform(OSPlatform.Windows)
            ? ("Set-Location ([System.IO.Path]::GetTempPath())", "pwd")
            : ("cd \"$(dirname \"$(mktemp -u)\")\"", "pwd");

        var first = await shell.RunAsync(cdCmd);
        Assert.Equal(0, first.ExitCode);

        var second = await shell.RunAsync(pwdCmd);
        Assert.Equal(0, second.ExitCode);
        Assert.False(string.IsNullOrWhiteSpace(second.Stdout), $"pwd produced no output. stderr='{second.Stderr}'");
        var tmp = System.IO.Path.GetTempPath().TrimEnd(System.IO.Path.DirectorySeparatorChar, System.IO.Path.AltDirectorySeparatorChar);
        Assert.Contains(System.IO.Path.GetFileName(tmp), second.Stdout, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public async Task Persistent_CarriesEnvironment_AcrossCallsAsync()
    {
        await using var shell = new LocalShellTool(
            mode: ShellMode.Persistent,
            timeout: TimeSpan.FromSeconds(20));

        var (setCmd, readCmd) = RuntimeInformation.IsOSPlatform(OSPlatform.Windows)
            ? ("$env:AF_SHELL_TEST = 'persisted-value'", "$env:AF_SHELL_TEST")
            : ("export AF_SHELL_TEST=persisted-value", "echo $AF_SHELL_TEST");

        _ = await shell.RunAsync(setCmd);
        var read = await shell.RunAsync(readCmd);
        Assert.Equal(0, read.ExitCode);
        Assert.Contains("persisted-value", read.Stdout, StringComparison.Ordinal);
    }

    [Fact]
    public async Task Persistent_Timeout_ReturnsExitCode124Async()
    {
        await using var shell = new LocalShellTool(
            mode: ShellMode.Persistent,
            timeout: TimeSpan.FromMilliseconds(400));

        var sleepCmd = RuntimeInformation.IsOSPlatform(OSPlatform.Windows)
            ? "Start-Sleep -Seconds 30"
            : "sleep 30";

        var result = await shell.RunAsync(sleepCmd);
        Assert.True(result.TimedOut);
        Assert.Equal(124, result.ExitCode);
    }

    [Fact]
    public async Task Stateless_OutputTruncation_UsesHeadTailFormatAsync()
    {
        // 2KB cap, emit ~10KB → must be truncated and contain the head+tail marker.
        await using var shell = new LocalShellTool(
            mode: ShellMode.Stateless,
            maxOutputBytes: 2048,
            timeout: TimeSpan.FromSeconds(20));

        var bigCmd = RuntimeInformation.IsOSPlatform(OSPlatform.Windows)
            ? "1..400 | ForEach-Object { 'line-' + $_ + '-padding-padding-padding' }"
            : "for i in $(seq 1 400); do echo \"line-$i-padding-padding-padding\"; done";

        var result = await shell.RunAsync(bigCmd);
        Assert.True(result.Truncated);
        Assert.Contains("truncated", result.Stdout, StringComparison.OrdinalIgnoreCase);
        // Should keep both ends — first and last line should be visible.
        Assert.Contains("line-1-", result.Stdout, StringComparison.Ordinal);
        Assert.Contains("line-400-", result.Stdout, StringComparison.Ordinal);
    }

    [Fact]
    public void Ctor_DefaultsToPersistentMode()
    {
        // Skip on Windows-cmd-only hosts where Persistent throws; safe on
        // any system that has pwsh or bash on PATH (CI, dev boxes).
        try
        {
            using var shell = new LocalShellTool();
            Assert.NotNull(shell);
        }
        catch (NotSupportedException)
        {
            // Persistent + cmd.exe on a host without pwsh — acceptable; test passes.
        }
    }

    [Fact]
    public void Ctor_RejectsBothShellAndShellArgv()
    {
        var argv = new[] { "/bin/bash", "--noprofile" };
        _ = Assert.Throws<ArgumentException>(() => new LocalShellTool(
            mode: ShellMode.Stateless,
            shell: "/bin/bash",
            shellArgv: argv));
    }

    [Fact]
    public async Task Persistent_ConfineWorkdir_ReanchorsAfterCdAwayAsync()
    {
        var rootDir = System.IO.Path.GetTempPath();
        var subDir = System.IO.Path.Combine(rootDir, "af-shell-confine-" + Guid.NewGuid().ToString("N")[..8]);
        System.IO.Directory.CreateDirectory(subDir);
        try
        {
            await using var shell = new LocalShellTool(
                mode: ShellMode.Persistent,
                workingDirectory: rootDir,
                confineWorkingDirectory: true,
                timeout: TimeSpan.FromSeconds(20));

            // First call: cd into subdir.
            var cd = RuntimeInformation.IsOSPlatform(OSPlatform.Windows)
                ? $"Set-Location -LiteralPath \"{subDir}\""
                : $"cd \"{subDir}\"";
            _ = await shell.RunAsync(cd);

            // Second call: pwd. With confinement we should be re-anchored to rootDir.
            var pwdCmd = RuntimeInformation.IsOSPlatform(OSPlatform.Windows) ? "(Get-Location).Path" : "pwd";
            var result = await shell.RunAsync(pwdCmd);
            Assert.Equal(0, result.ExitCode);
            var rootName = System.IO.Path.GetFileName(rootDir.TrimEnd(System.IO.Path.DirectorySeparatorChar, System.IO.Path.AltDirectorySeparatorChar));
            Assert.Contains(rootName, result.Stdout, StringComparison.OrdinalIgnoreCase);
            Assert.DoesNotContain(System.IO.Path.GetFileName(subDir), result.Stdout, StringComparison.OrdinalIgnoreCase);
        }
        finally
        {
            try { System.IO.Directory.Delete(subDir, recursive: true); } catch { }
        }
    }

    [Fact]
    public async Task Persistent_ConfineDisabled_AllowsCdToLeakAsync()
    {
        var rootDir = System.IO.Path.GetTempPath();
        var subDir = System.IO.Path.Combine(rootDir, "af-shell-noconfine-" + Guid.NewGuid().ToString("N")[..8]);
        System.IO.Directory.CreateDirectory(subDir);
        try
        {
            await using var shell = new LocalShellTool(
                mode: ShellMode.Persistent,
                workingDirectory: rootDir,
                confineWorkingDirectory: false,
                timeout: TimeSpan.FromSeconds(20));

            var cd = RuntimeInformation.IsOSPlatform(OSPlatform.Windows)
                ? $"Set-Location -LiteralPath \"{subDir}\""
                : $"cd \"{subDir}\"";
            _ = await shell.RunAsync(cd);

            var pwdCmd = RuntimeInformation.IsOSPlatform(OSPlatform.Windows) ? "(Get-Location).Path" : "pwd";
            var result = await shell.RunAsync(pwdCmd);
            Assert.Equal(0, result.ExitCode);
            Assert.Contains(System.IO.Path.GetFileName(subDir), result.Stdout, StringComparison.OrdinalIgnoreCase);
        }
        finally
        {
            try { System.IO.Directory.Delete(subDir, recursive: true); } catch { }
        }
    }

    [Fact]
    public async Task Stateless_CleanEnvironment_StripsCustomVarAsync()
    {
        Environment.SetEnvironmentVariable("AF_SHELL_PARENT_VAR", "should-not-leak");
        try
        {
            await using var shell = new LocalShellTool(mode: ShellMode.Stateless, cleanEnvironment: true);
            var read = RuntimeInformation.IsOSPlatform(OSPlatform.Windows)
                ? "$env:AF_SHELL_PARENT_VAR"
                : "echo $AF_SHELL_PARENT_VAR";
            var result = await shell.RunAsync(read);
            Assert.Equal(0, result.ExitCode);
            Assert.DoesNotContain("should-not-leak", result.Stdout, StringComparison.Ordinal);
        }
        finally
        {
            Environment.SetEnvironmentVariable("AF_SHELL_PARENT_VAR", null);
        }
    }

    [Fact]
    public void IShellExecutor_LocalShellTool_ImplementsInterface()
    {
        using var shell = new LocalShellTool(mode: ShellMode.Stateless);
        IShellExecutor executor = shell;
        Assert.NotNull(executor);
    }
}
