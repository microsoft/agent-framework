// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Linq;
using System.Runtime.InteropServices;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Tools.Shell;
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
    public async Task RunAsync_EchoCommand_RoundtripsStdoutAndExitCode()
    {
        using var shell = new LocalShellTool();
        // Use an OS-appropriate echo. On Windows the resolved shell is PowerShell.
        var result = await shell.RunAsync("echo hello-from-shell");
        Assert.Equal(0, result.ExitCode);
        Assert.Contains("hello-from-shell", result.Stdout, StringComparison.Ordinal);
        Assert.False(result.TimedOut);
    }

    [Fact]
    public async Task RunAsync_RejectedCommand_ThrowsShellCommandRejected()
    {
        using var shell = new LocalShellTool();
        await Assert.ThrowsAsync<ShellCommandRejectedException>(
            () => shell.RunAsync("rm -rf /"));
    }

    [Fact]
    public async Task RunAsync_NonZeroExit_PropagatesExitCode()
    {
        using var shell = new LocalShellTool();
        // Exit-1 phrasing portable across bash and PowerShell.
        var script = RuntimeInformation.IsOSPlatform(OSPlatform.Windows)
            ? "exit 7"
            : "exit 7";
        var result = await shell.RunAsync(script);
        Assert.Equal(7, result.ExitCode);
    }

    [Fact]
    public async Task RunAsync_Timeout_FlagsTimedOutAndKillsProcess()
    {
        using var shell = new LocalShellTool(timeout: TimeSpan.FromMilliseconds(250));
        var sleepCmd = RuntimeInformation.IsOSPlatform(OSPlatform.Windows)
            ? "Start-Sleep -Seconds 30"
            : "sleep 30";
        var result = await shell.RunAsync(sleepCmd);
        Assert.True(result.TimedOut);
        Assert.Equal(124, result.ExitCode);
        Assert.True(result.Duration < TimeSpan.FromSeconds(10));
    }

    [Fact]
    public void AsAIFunction_DefaultsToApprovalRequired()
    {
        using var shell = new LocalShellTool();
        var fn = shell.AsAIFunction();
        Assert.IsType<ApprovalRequiredAIFunction>(fn);
        Assert.Equal("run_shell", fn.Name);
        Assert.False(string.IsNullOrWhiteSpace(fn.Description));
    }

    [Fact]
    public void AsAIFunction_OptOut_RequiresAcknowledgeUnsafe()
    {
        using var shell = new LocalShellTool();
        _ = Assert.Throws<InvalidOperationException>(() => shell.AsAIFunction(requireApproval: false));
    }

    [Fact]
    public void AsAIFunction_OptOut_WithAck_ReturnsPlainFunction()
    {
        using var shell = new LocalShellTool(acknowledgeUnsafe: true);
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
    public async Task OnCommand_HookFiredForAllowedCommandsOnly()
    {
        var calls = new System.Collections.Generic.List<string>();
        using var shell = new LocalShellTool(onCommand: cmd => calls.Add(cmd));
        await Assert.ThrowsAsync<ShellCommandRejectedException>(() => shell.RunAsync("rm -rf /"));
        Assert.Empty(calls);
    }

    [Fact]
    public async Task Persistent_CarriesWorkingDirectory_AcrossCalls()
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
    public async Task Persistent_CarriesEnvironment_AcrossCalls()
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
    public async Task Persistent_Timeout_ReturnsExitCode124()
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
    public async Task Stateless_OutputTruncation_UsesHeadTailFormat()
    {
        // 2KB cap, emit ~10KB → must be truncated and contain the head+tail marker.
        using var shell = new LocalShellTool(
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
}
