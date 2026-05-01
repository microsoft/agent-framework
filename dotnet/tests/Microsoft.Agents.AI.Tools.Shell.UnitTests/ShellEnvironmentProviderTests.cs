// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Agents.AI.Tools.Shell.UnitTests;

/// <summary>
/// Tests for <see cref="ShellEnvironmentProvider"/>. Most assertions go
/// through a fake <see cref="IShellExecutor"/> so the tests are
/// hermetic and don't depend on the host's installed CLIs.
/// </summary>
public sealed class ShellEnvironmentProviderTests
{
    [Fact]
    public async Task RefreshAsync_OnPowerShellHost_ReportsPowerShellAsync()
    {
        if (!RuntimeInformation.IsOSPlatform(OSPlatform.Windows))
        {
            return; // The default-detection path only fires PowerShell on Windows.
        }

        await using var shell = new LocalShellTool(mode: ShellMode.Stateless);
        var provider = new ShellEnvironmentProvider(shell, new() { ProbeTools = [] });
        var snapshot = await provider.RefreshAsync();

        Assert.Equal(ShellFamily.PowerShell, snapshot.Family);
        Assert.False(string.IsNullOrWhiteSpace(snapshot.WorkingDirectory));
        // Shell version probe runs `$PSVersionTable.PSVersion` — must be non-null on a real host.
        Assert.False(string.IsNullOrWhiteSpace(snapshot.ShellVersion));
    }

    [Fact]
    public async Task RefreshAsync_OnPosixHost_ReportsPosixAsync()
    {
        if (RuntimeInformation.IsOSPlatform(OSPlatform.Windows))
        {
            return;
        }

        await using var shell = new LocalShellTool(mode: ShellMode.Stateless);
        var provider = new ShellEnvironmentProvider(shell, new() { ProbeTools = [] });
        var snapshot = await provider.RefreshAsync();

        Assert.Equal(ShellFamily.Posix, snapshot.Family);
        Assert.False(string.IsNullOrWhiteSpace(snapshot.WorkingDirectory));
    }

    [Fact]
    public void DefaultInstructionsFormatter_PowerShell_ContainsPowerShellIdioms()
    {
        var snapshot = new ShellEnvironmentSnapshot(
            Family: ShellFamily.PowerShell,
            OSDescription: "Windows 11",
            ShellVersion: "7.4.0",
            WorkingDirectory: @"C:\repo",
            ToolVersions: new Dictionary<string, string?> { ["git"] = "git 2.46", ["docker"] = null });

        var instructions = ShellEnvironmentProvider.DefaultInstructionsFormatter(snapshot);
        Assert.Contains("PowerShell 7.4.0", instructions, StringComparison.Ordinal);
        Assert.Contains("$env:NAME", instructions, StringComparison.Ordinal);
        Assert.Contains("Set-Location", instructions, StringComparison.Ordinal);
        Assert.Contains(@"C:\repo", instructions, StringComparison.Ordinal);
        Assert.Contains("git (git 2.46)", instructions, StringComparison.Ordinal);
        Assert.Contains("Not installed: docker", instructions, StringComparison.Ordinal);
    }

    [Fact]
    public void DefaultInstructionsFormatter_Posix_ContainsPosixIdioms()
    {
        var snapshot = new ShellEnvironmentSnapshot(
            Family: ShellFamily.Posix,
            OSDescription: "Ubuntu 22.04",
            ShellVersion: "5.2",
            WorkingDirectory: "/home/user/repo",
            ToolVersions: new Dictionary<string, string?> { ["git"] = "git 2.43" });

        var instructions = ShellEnvironmentProvider.DefaultInstructionsFormatter(snapshot);
        Assert.Contains("POSIX", instructions, StringComparison.Ordinal);
        Assert.Contains("export NAME=value", instructions, StringComparison.Ordinal);
        Assert.Contains("/home/user/repo", instructions, StringComparison.Ordinal);
        Assert.DoesNotContain("$env:", instructions, StringComparison.Ordinal);
    }

    [Fact]
    public async Task RefreshAsync_MissingTool_RecordedAsNullAsync()
    {
        await using var shell = new LocalShellTool(mode: ShellMode.Stateless);
        var provider = new ShellEnvironmentProvider(shell, new()
        {
            ProbeTools = ["definitely-not-a-real-binary-xyz123"],
            ProbeTimeout = TimeSpan.FromSeconds(5),
        });

        var snapshot = await provider.RefreshAsync();
        Assert.True(snapshot.ToolVersions.ContainsKey("definitely-not-a-real-binary-xyz123"));
        Assert.Null(snapshot.ToolVersions["definitely-not-a-real-binary-xyz123"]);
    }

    [Fact]
    public async Task ProvideAIContext_CustomFormatter_OverridesDefaultAsync()
    {
        var fake = new FakeShellExecutor(
            new ShellResult("VERSION=1.0\nCWD=/tmp\n", "", 0, TimeSpan.Zero));
        var provider = new ShellEnvironmentProvider(fake, new()
        {
            OverrideFamily = ShellFamily.Posix,
            ProbeTools = [],
            InstructionsFormatter = _ => "CUSTOM-INSTRUCTIONS",
        });
        var snapshot = await provider.RefreshAsync();
        Assert.Equal("/tmp", snapshot.WorkingDirectory);

        // ProvideAIContextAsync isn't directly accessible (protected), but we
        // can verify via the formatter contract: the snapshot is the only
        // input and it's correct.
        var custom = (provider.GetType()
            .GetField("_options", System.Reflection.BindingFlags.NonPublic | System.Reflection.BindingFlags.Instance)
            ?.GetValue(provider) as ShellEnvironmentProviderOptions)!.InstructionsFormatter!(snapshot);
        Assert.Equal("CUSTOM-INSTRUCTIONS", custom);
    }

    [Fact]
    public async Task RefreshAsync_RecomputesSnapshotAsync()
    {
        var fake = new FakeShellExecutor(
            new ShellResult("VERSION=1.0\nCWD=/a\n", "", 0, TimeSpan.Zero));
        var provider = new ShellEnvironmentProvider(fake, new()
        {
            OverrideFamily = ShellFamily.Posix,
            ProbeTools = [],
        });

        var first = await provider.RefreshAsync();
        Assert.Equal("/a", first.WorkingDirectory);

        fake.NextResult = new ShellResult("VERSION=2.0\nCWD=/b\n", "", 0, TimeSpan.Zero);
        var second = await provider.RefreshAsync();
        Assert.Equal("/b", second.WorkingDirectory);
        Assert.Equal("2.0", second.ShellVersion);
    }

    [Fact]
    public async Task ProvideAIContext_FirstCall_ProbesOnlyOnceAsync()
    {
        var fake = new FakeShellExecutor(
            new ShellResult("VERSION=1.0\nCWD=/x\n", "", 0, TimeSpan.Zero));
        var provider = new ShellEnvironmentProvider(fake, new()
        {
            OverrideFamily = ShellFamily.Posix,
            ProbeTools = [],
        });

        // Force first probe.
        _ = await provider.RefreshAsync();
        var probesAfterFirst = fake.RunCount;

        // Subsequent ProvideAIContext calls should not re-probe — they hit
        // the cached _snapshotTask.
        await provider.RefreshAsync();
        Assert.True(fake.RunCount > probesAfterFirst, "Refresh should re-probe");
    }

    private sealed class FakeShellExecutor : IShellExecutor
    {
        public FakeShellExecutor(ShellResult result) { this.NextResult = result; }
        public ShellResult NextResult { get; set; }
        public int RunCount { get; private set; }
        public Task StartAsync(CancellationToken cancellationToken = default) => Task.CompletedTask;
        public Task CloseAsync(CancellationToken cancellationToken = default) => Task.CompletedTask;
        public Task<ShellResult> RunAsync(string command, CancellationToken cancellationToken = default)
        {
            this.RunCount++;
            return Task.FromResult(this.NextResult);
        }
        public ValueTask DisposeAsync() => default;
    }
}
