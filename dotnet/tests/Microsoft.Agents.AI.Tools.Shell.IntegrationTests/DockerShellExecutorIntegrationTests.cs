// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.IO;
using System.Threading.Tasks;

namespace Microsoft.Agents.AI.Tools.Shell.IntegrationTests;

/// <summary>
/// End-to-end tests that exercise <see cref="DockerShellExecutor"/> against a live
/// Docker (or Podman) daemon. Tests auto-skip when no daemon is available, so
/// they're safe to run in CI.
/// </summary>
/// <remarks>
/// To run only these tests locally:
/// <code>
/// dotnet test --filter "Category=Integration&amp;FullyQualifiedName~DockerShellExecutorIntegrationTests"
/// </code>
/// or run the test exe directly with the trait filter.
/// </remarks>
[Trait("Category", "Integration")]
public sealed class DockerShellExecutorIntegrationTests
{
    // Small, fast image that has bash. Pulled lazily on first run.
    // Alpine ships only busybox sh, which the persistent shell session can't use.
    private const string TestImage = "debian:stable-slim";

    private static async Task<bool> EnsureDockerOrSkipAsync()
    {
        if (!await DockerShellExecutor.IsAvailableAsync().ConfigureAwait(false))
        {
            Assert.Skip("Docker (or Podman) daemon is not available on this machine.");
            return false; // unreachable
        }
        return true;
    }

    [Fact]
    public async Task IsAvailableAsync_ReturnsTrue_WhenDaemonRunningAsync()
    {
        await EnsureDockerOrSkipAsync();
        Assert.True(await DockerShellExecutor.IsAvailableAsync());
    }

    [Fact]
    public async Task Persistent_RunsBasicCommandAsync()
    {
        await EnsureDockerOrSkipAsync();

        await using var tool = new DockerShellExecutor(new() { Image = TestImage, Mode = ShellMode.Persistent });
        await tool.InitializeAsync();

        var result = await tool.RunAsync("echo hello-from-docker");

        Assert.Equal(0, result.ExitCode);
        Assert.Contains("hello-from-docker", result.Stdout);
    }

    [Fact]
    public async Task Persistent_PreservesStateAcrossCallsAsync()
    {
        await EnsureDockerOrSkipAsync();

        await using var tool = new DockerShellExecutor(new() { Image = TestImage, Mode = ShellMode.Persistent });
        await tool.InitializeAsync();

        var set = await tool.RunAsync("export DEMO=persisted-12345");
        Assert.Equal(0, set.ExitCode);

        var get = await tool.RunAsync("echo $DEMO");
        Assert.Equal(0, get.ExitCode);
        Assert.Contains("persisted-12345", get.Stdout);
    }

    [Fact]
    public async Task NetworkNone_BlocksOutboundConnectionsAsync()
    {
        await EnsureDockerOrSkipAsync();

        await using var tool = new DockerShellExecutor(new() { Image = TestImage, Mode = ShellMode.Persistent /* network defaults to "none" */ });
        await tool.InitializeAsync();

        // Try to resolve a hostname; with --network none, even DNS should fail.
        // Use getent (always present on debian) so we don't depend on optional tools.
        var result = await tool.RunAsync("getent hosts example.com 2>&1; echo MARKER:$?");

        Assert.Contains("MARKER:", result.Stdout);
        // Non-zero status from getent proves DNS resolution (and therefore the
        // network) was blocked.
        Assert.DoesNotContain("MARKER:0", result.Stdout);
    }

    [Fact]
    public async Task ReadOnlyRoot_PreventsWritesOutsideTmpAsync()
    {
        await EnsureDockerOrSkipAsync();

        await using var tool = new DockerShellExecutor(new() { Image = TestImage, Mode = ShellMode.Persistent });
        await tool.InitializeAsync();

        var rootWrite = await tool.RunAsync("touch /should-not-exist 2>&1; echo CODE:$?");
        Assert.Contains("CODE:", rootWrite.Stdout);
        Assert.DoesNotContain("CODE:0", rootWrite.Stdout);

        var tmpWrite = await tool.RunAsync("touch /tmp/ok && echo TMP_OK");
        Assert.Equal(0, tmpWrite.ExitCode);
        Assert.Contains("TMP_OK", tmpWrite.Stdout);
    }

    [Fact]
    public async Task NonRootUser_RunsAsNobodyAsync()
    {
        await EnsureDockerOrSkipAsync();

        await using var tool = new DockerShellExecutor(new() { Image = TestImage, Mode = ShellMode.Persistent });
        await tool.InitializeAsync();

        var result = await tool.RunAsync("id -u");

        Assert.Equal(0, result.ExitCode);
        // Default user is 65534:65534
        Assert.Contains("65534", result.Stdout);
    }

    [Fact]
    public async Task Stateless_RunsEachCommandInFreshContainerAsync()
    {
        await EnsureDockerOrSkipAsync();

        await using var tool = new DockerShellExecutor(new() { Image = TestImage, Mode = ShellMode.Stateless });

        var first = await tool.RunAsync("echo first; export STATE=set");
        Assert.Equal(0, first.ExitCode);
        Assert.Contains("first", first.Stdout);

        // Stateless: env var must NOT survive
        var second = await tool.RunAsync("echo \"second:[${STATE:-unset}]\"");
        Assert.Equal(0, second.ExitCode);
        Assert.Contains("second:[unset]", second.Stdout);
    }

    [Fact]
    public async Task HostWorkdir_MountsAndIsReadOnlyByDefaultAsync()
    {
        await EnsureDockerOrSkipAsync();

        var hostDir = Path.Combine(Path.GetTempPath(), "af-docker-shell-it-" + Guid.NewGuid().ToString("N")[..8]);
        Directory.CreateDirectory(hostDir);
        var sentinel = Path.Combine(hostDir, "from-host.txt");
        await File.WriteAllTextAsync(sentinel, "host-content");

        try
        {
            await using var tool = new DockerShellExecutor(new()
            {
                Image = TestImage,
                Mode = ShellMode.Persistent,
                HostWorkdir = hostDir,
                MountReadonly = true,
            });
            await tool.InitializeAsync();

            var read = await tool.RunAsync("cat /workspace/from-host.txt");
            Assert.Equal(0, read.ExitCode);
            Assert.Contains("host-content", read.Stdout);

            // Read-only mount: write must fail
            var write = await tool.RunAsync("echo bad > /workspace/should-fail 2>&1; echo CODE:$?");
            Assert.DoesNotContain("CODE:0", write.Stdout);
        }
        finally
        {
            try { Directory.Delete(hostDir, recursive: true); } catch { /* best-effort cleanup */ }
        }
    }

    [Fact]
    public async Task EnvironmentVariables_ArePassedThroughAsync()
    {
        await EnsureDockerOrSkipAsync();

        await using var tool = new DockerShellExecutor(new()
        {
            Image = TestImage,
            Mode = ShellMode.Persistent,
            Environment = new Dictionary<string, string>
            {
                ["INJECTED_VAR"] = "injected-value-7777",
            },
        });
        await tool.InitializeAsync();

        var result = await tool.RunAsync("echo $INJECTED_VAR");

        Assert.Equal(0, result.ExitCode);
        Assert.Contains("injected-value-7777", result.Stdout);
    }
}
