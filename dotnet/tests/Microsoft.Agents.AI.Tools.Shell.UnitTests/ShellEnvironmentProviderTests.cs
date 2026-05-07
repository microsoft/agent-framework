// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Agents.AI.Tools.Shell.UnitTests;

/// <summary>
/// Tests for <see cref="ShellEnvironmentProvider"/>. Most assertions go
/// through a fake <see cref="ShellExecutor"/> so the tests are
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

        await using var shell = new LocalShellExecutor(new() { Mode = ShellMode.Stateless });
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

        await using var shell = new LocalShellExecutor(new() { Mode = ShellMode.Stateless });
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
        await using var shell = new LocalShellExecutor(new() { Mode = ShellMode.Stateless });
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
        var options = new ShellEnvironmentProviderOptions
        {
            OverrideFamily = ShellFamily.Posix,
            ProbeTools = [],
            InstructionsFormatter = _ => "CUSTOM-INSTRUCTIONS",
        };
        var provider = new ShellEnvironmentProvider(fake, options);
        var snapshot = await provider.RefreshAsync();
        Assert.Equal("/tmp", snapshot.WorkingDirectory);

        // ProvideAIContextAsync is protected; assert the formatter contract directly
        // against the options instance the test owns.
        var custom = options.InstructionsFormatter!(snapshot);
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
    public async Task RefreshAsync_ReProbesEachCallAsync()
    {
        var fake = new FakeShellExecutor(
            new ShellResult("VERSION=1.0\nCWD=/x\n", "", 0, TimeSpan.Zero));
        var provider = new ShellEnvironmentProvider(fake, new()
        {
            OverrideFamily = ShellFamily.Posix,
            ProbeTools = [],
        });

        _ = await provider.RefreshAsync();
        var probesAfterFirst = fake.RunCount;

        await provider.RefreshAsync();
        Assert.True(fake.RunCount > probesAfterFirst, "RefreshAsync should re-probe each call");
    }

    [Fact]
    public async Task RefreshAsync_InvalidToolName_RecordedAsNullWithoutInvokingExecutorAsync()
    {
        var fake = new FakeShellExecutor(
            new ShellResult("VERSION=1.0\nCWD=/\n", "", 0, TimeSpan.Zero));
        var provider = new ShellEnvironmentProvider(fake, new()
        {
            OverrideFamily = ShellFamily.Posix,
            ProbeTools = ["git; rm -rf /", "echo $PATH", "good-tool && bad"],
        });

        var snapshot = await provider.RefreshAsync();
        // One probe for shell+CWD; none of the bogus tool names should reach the executor.
        Assert.Equal(1, fake.RunCount);
        Assert.Null(snapshot.ToolVersions["git; rm -rf /"]);
        Assert.Null(snapshot.ToolVersions["echo $PATH"]);
        Assert.Null(snapshot.ToolVersions["good-tool && bad"]);
    }

    [Fact]
    public async Task RefreshAsync_DuplicateProbeToolsCaseInsensitive_ProbesOnceAsync()
    {
        // ProbeTools is user-supplied. With a case-insensitive backing dictionary,
        // {"git","GIT"} used to probe twice and let the second insertion silently
        // overwrite the first. Verify we now skip duplicates.
        var fake = new ScriptedShellExecutor();
        fake.Responses.Enqueue(new ShellResult("VERSION=1.0\nCWD=/\n", "", 0, TimeSpan.Zero)); // shell+cwd probe
        fake.Responses.Enqueue(new ShellResult("git 2.46\n", "", 0, TimeSpan.Zero));          // first git probe
        // No second probe response queued — if dedup is broken, the test will throw on dequeue.

        var provider = new ShellEnvironmentProvider(fake, new()
        {
            OverrideFamily = ShellFamily.Posix,
            ProbeTools = ["git", "GIT", "Git"],
        });

        var snapshot = await provider.RefreshAsync();
        Assert.Single(snapshot.ToolVersions);
        Assert.Equal("git 2.46", snapshot.ToolVersions["git"]);
        Assert.Equal("git 2.46", snapshot.ToolVersions["GIT"]);
    }

    [Fact]
    public async Task RefreshAsync_ToolEmitsVersionToStderr_FallsBackToStderrAsync()
    {
        // Some CLIs (e.g. java, older gcc) write `--version` output to stderr.
        var fake = new ScriptedShellExecutor();
        fake.Responses.Enqueue(new ShellResult("VERSION=1.0\nCWD=/\n", "", 0, TimeSpan.Zero)); // shell+cwd probe
        fake.Responses.Enqueue(new ShellResult("", "openjdk 21.0.1 2023-10-17\n", 0, TimeSpan.Zero)); // tool probe

        var provider = new ShellEnvironmentProvider(fake, new()
        {
            OverrideFamily = ShellFamily.Posix,
            ProbeTools = ["java"],
        });

        var snapshot = await provider.RefreshAsync();
        Assert.Equal("openjdk 21.0.1 2023-10-17", snapshot.ToolVersions["java"]);
    }

    private sealed class ScriptedShellExecutor : ShellExecutor
    {
        public Queue<ShellResult> Responses { get; } = new();
        public override Task InitializeAsync(CancellationToken cancellationToken = default) => Task.CompletedTask;
        public override Task<ShellResult> RunAsync(string command, CancellationToken cancellationToken = default) =>
            Task.FromResult(this.Responses.Dequeue());
        public override ValueTask DisposeAsync() => default;
    }

    [Fact]
    public async Task RefreshAsync_CallerCancellation_PropagatesAsync()
    {
        var fake = new ThrowingShellExecutor(token =>
        {
            token.ThrowIfCancellationRequested();
            return new ShellResult("VERSION=1.0\nCWD=/x\n", "", 0, TimeSpan.Zero);
        });
        var provider = new ShellEnvironmentProvider(fake, new()
        {
            OverrideFamily = ShellFamily.Posix,
            ProbeTools = [],
        });

        using var cts = new CancellationTokenSource();
        cts.Cancel();

        await Assert.ThrowsAnyAsync<OperationCanceledException>(
            () => provider.RefreshAsync(cts.Token));
    }

    [Fact]
    public async Task RefreshAsync_ProbeTimeout_RecordedAsNullFieldsAsync()
    {
        // Executor honors the (linked) probe-timeout token by throwing OCE when it fires.
        var fake = new ThrowingShellExecutor(token =>
        {
            token.WaitHandle.WaitOne(TimeSpan.FromSeconds(5));
            token.ThrowIfCancellationRequested();
            return new ShellResult("VERSION=1.0\nCWD=/\n", "", 0, TimeSpan.Zero);
        });
        var provider = new ShellEnvironmentProvider(fake, new()
        {
            OverrideFamily = ShellFamily.Posix,
            ProbeTimeout = TimeSpan.FromMilliseconds(50),
            ProbeTools = ["git"],
        });

        // Caller-side token stays alive; only the per-probe timeout fires.
        var snapshot = await provider.RefreshAsync();
        Assert.Null(snapshot.ShellVersion);
        Assert.Null(snapshot.ToolVersions["git"]);
    }

    private sealed class ThrowingShellExecutor : ShellExecutor
    {
        private readonly Func<CancellationToken, ShellResult> _factory;
        public ThrowingShellExecutor(Func<CancellationToken, ShellResult> factory) { this._factory = factory; }
        public override Task InitializeAsync(CancellationToken cancellationToken = default) => Task.CompletedTask;
        public override Task<ShellResult> RunAsync(string command, CancellationToken cancellationToken = default) =>
            Task.FromResult(this._factory(cancellationToken));
        public override ValueTask DisposeAsync() => default;
    }

    [Fact]
    public async Task ProvideAIContextAsync_FirstCallFails_NextCallRetriesAndSucceedsAsync()
    {
        // Reproduce the "poisoned _snapshotTask" scenario: the first probe throws
        // (e.g. caller cancels, or an executor blip), and a subsequent call must
        // be able to recover instead of returning the cached failure forever.
        var calls = 0;
        var fake = new ThrowingShellExecutor(_ =>
        {
            calls++;
            if (calls == 1)
            {
                throw new InvalidOperationException("boom");
            }
            return new ShellResult("VERSION=2.0\nCWD=/tmp\n", "", 0, TimeSpan.Zero);
        });
        var provider = new ShellEnvironmentProvider(fake, new()
        {
            OverrideFamily = ShellFamily.Posix,
            ProbeTools = [],
        });

        // First call surfaces the executor failure.
        await Assert.ThrowsAnyAsync<Exception>(() => InvokeProvideAsync(provider));

        // Second call must re-probe and succeed.
        var ctx = await InvokeProvideAsync(provider);
        Assert.NotNull(ctx.Instructions);
        Assert.NotNull(provider.CurrentSnapshot);
        Assert.Equal("2.0", provider.CurrentSnapshot!.ShellVersion);
    }

    [Fact]
    public async Task ProvideAIContextAsync_FirstCallCancelled_NextCallSucceedsAsync()
    {
        // Round 6 made caller cancellation propagate. Combined with the cached
        // _snapshotTask, a single Ctrl-C on the first turn used to permanently
        // break the provider — verify that round 7's reset clears that.
        var calls = 0;
        var fake = new ThrowingShellExecutor(token =>
        {
            calls++;
            if (calls == 1)
            {
                token.ThrowIfCancellationRequested();
            }
            return new ShellResult("VERSION=3.0\nCWD=/x\n", "", 0, TimeSpan.Zero);
        });
        var provider = new ShellEnvironmentProvider(fake, new()
        {
            OverrideFamily = ShellFamily.Posix,
            ProbeTools = [],
        });

        using var cts = new CancellationTokenSource();
        cts.Cancel();
        await Assert.ThrowsAnyAsync<OperationCanceledException>(() => InvokeProvideAsync(provider, cts.Token));

        var ctx = await InvokeProvideAsync(provider);
        Assert.NotNull(ctx.Instructions);
        Assert.Equal("3.0", provider.CurrentSnapshot!.ShellVersion);
    }

    /// <summary>
    /// Invokes the protected <c>ProvideAIContextAsync</c> via reflection so tests
    /// can target the cached-task code path directly. <see cref="ShellEnvironmentProvider"/>
    /// is sealed, so we cannot derive a public passthrough.
    /// </summary>
    private static async Task<AIContext> InvokeProvideAsync(ShellEnvironmentProvider provider, CancellationToken ct = default)
    {
        var method = typeof(ShellEnvironmentProvider).GetMethod(
            "ProvideAIContextAsync",
            BindingFlags.Instance | BindingFlags.NonPublic | BindingFlags.Public)
            ?? throw new InvalidOperationException("ProvideAIContextAsync not found");
        var task = (ValueTask<AIContext>)method.Invoke(provider, new object?[] { null, ct })!;
        return await task.ConfigureAwait(false);
    }

    private sealed class FakeShellExecutor : ShellExecutor
    {
        public FakeShellExecutor(ShellResult result) { this.NextResult = result; }
        public ShellResult NextResult { get; set; }
        public int RunCount { get; private set; }
        public override Task InitializeAsync(CancellationToken cancellationToken = default) => Task.CompletedTask;
        public override Task<ShellResult> RunAsync(string command, CancellationToken cancellationToken = default)
        {
            this.RunCount++;
            return Task.FromResult(this.NextResult);
        }
        public override ValueTask DisposeAsync() => default;
    }
}
