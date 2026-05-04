// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Tools.Shell.UnitTests;

/// <summary>
/// Tests for the side-effect-free argv builders on <see cref="DockerShellTool"/>.
/// These don't require a Docker daemon to run.
/// </summary>
public sealed class DockerShellToolTests
{
    private static readonly string[] s_privilegedExtraRunArgs = new[] { "--privileged" };

    [Fact]
    public void BuildRunArgv_EmitsHardenedDefaults()
    {
        var argv = DockerShellTool.BuildRunArgv(
            binary: "docker",
            image: "alpine:3.19",
            containerName: "af-shell-test",
            user: "65534:65534",
            network: "none",
            memory: "256m",
            pidsLimit: 64,
            workdir: "/workspace",
            hostWorkdir: null,
            mountReadonly: true,
            readOnlyRoot: true,
            extraEnv: null,
            extraArgs: null);

        Assert.Equal("docker", argv[0]);
        Assert.Equal("run", argv[1]);
        Assert.Contains("-d", argv);
        Assert.Contains("--rm", argv);
        Assert.Contains("--network", argv);
        Assert.Contains("none", argv);
        Assert.Contains("--cap-drop", argv);
        Assert.Contains("ALL", argv);
        Assert.Contains("--security-opt", argv);
        Assert.Contains("no-new-privileges", argv);
        Assert.Contains("--read-only", argv);
        Assert.Contains("--tmpfs", argv);
        // Image, then sleep infinity at the end.
        Assert.Equal("alpine:3.19", argv[argv.Count - 3]);
        Assert.Equal("sleep", argv[argv.Count - 2]);
        Assert.Equal("infinity", argv[argv.Count - 1]);
    }

    [Fact]
    public void BuildRunArgv_HostWorkdir_AddsVolumeMount()
    {
        var argv = DockerShellTool.BuildRunArgv(
            binary: "docker",
            image: "alpine:3.19",
            containerName: "af-shell-test",
            user: "1000:1000",
            network: "none",
            memory: "256m",
            pidsLimit: 64,
            workdir: "/workspace",
            hostWorkdir: "/tmp/proj",
            mountReadonly: false,
            readOnlyRoot: false,
            extraEnv: null,
            extraArgs: null);

        var idx = argv.ToList().IndexOf("-v");
        Assert.True(idx >= 0, "expected -v flag");
        Assert.Equal("/tmp/proj:/workspace:rw", argv[idx + 1]);
        Assert.DoesNotContain("--read-only", argv);
    }

    [Fact]
    public void BuildRunArgv_HostWorkdir_DefaultsToReadonly()
    {
        var argv = DockerShellTool.BuildRunArgv(
            binary: "docker",
            image: "alpine:3.19",
            containerName: "x",
            user: "1000:1000",
            network: "none",
            memory: "256m",
            pidsLimit: 64,
            workdir: "/workspace",
            hostWorkdir: "/host/path",
            mountReadonly: true,
            readOnlyRoot: true,
            extraEnv: null,
            extraArgs: null);

        var list = argv.ToList();
        var idx = list.IndexOf("-v");
        Assert.Equal("/host/path:/workspace:ro", argv[idx + 1]);
    }

    [Fact]
    public void BuildRunArgv_EnvAndExtraArgs_AreAppended()
    {
        var env = new Dictionary<string, string> { ["LOG"] = "1", ["MODE"] = "ci" };
        var extra = new[] { "--label", "owner=test" };
        var argv = DockerShellTool.BuildRunArgv(
            binary: "docker",
            image: "alpine:3.19",
            containerName: "x",
            user: "1000:1000",
            network: "none",
            memory: "256m",
            pidsLimit: 64,
            workdir: "/workspace",
            hostWorkdir: null,
            mountReadonly: true,
            readOnlyRoot: true,
            extraEnv: env,
            extraArgs: extra);

        var list = argv.ToList();
        Assert.Contains("LOG=1", list);
        Assert.Contains("MODE=ci", list);
        Assert.Contains("--label", list);
        Assert.Contains("owner=test", list);
    }

    private static readonly string[] s_expectedInteractive = new[] { "docker", "exec", "-i", "af-shell-x", "bash", "--noprofile", "--norc" };

    [Fact]
    public void BuildExecArgv_EmitsBashNoProfileNoRc()
    {
        var argv = DockerShellTool.BuildExecArgv("docker", "af-shell-x");
        Assert.Equal(s_expectedInteractive, argv);
    }

    [Fact]
    public async Task Ctor_GeneratesUniqueContainerName()
    {
        await using var t1 = new DockerShellTool(mode: ShellMode.Stateless);
        await using var t2 = new DockerShellTool(mode: ShellMode.Stateless);
        Assert.StartsWith("af-shell-", t1.ContainerName, StringComparison.Ordinal);
        Assert.StartsWith("af-shell-", t2.ContainerName, StringComparison.Ordinal);
        Assert.NotEqual(t1.ContainerName, t2.ContainerName);
    }

    [Fact]
    public async Task Ctor_RespectsExplicitContainerName()
    {
        await using var t = new DockerShellTool(containerName: "my-explicit-name", mode: ShellMode.Stateless);
        Assert.Equal("my-explicit-name", t.ContainerName);
    }

    [Fact]
    public async Task IShellExecutor_DockerShellTool_ImplementsInterface()
    {
        await using var t = new DockerShellTool(mode: ShellMode.Stateless);
        IShellExecutor executor = t;
        Assert.NotNull(executor);
    }

    [Fact]
    public async Task AsAIFunction_HardenedDefaults_AreNotApprovalGated()
    {
        // With the default hardened config (network=none, non-root user,
        // read-only root, no extra args, no host mount) approval should
        // remain opt-in.
        await using var t = new DockerShellTool(mode: ShellMode.Stateless);
        Assert.True(t.IsHardenedConfiguration);
        var fn = t.AsAIFunction();
        Assert.IsNotType<ApprovalRequiredAIFunction>(fn);
        Assert.Equal("run_shell", fn.Name);
    }

    [Fact]
    public async Task AsAIFunction_OptInApproval_WrapsInApprovalRequired()
    {
        await using var t = new DockerShellTool(mode: ShellMode.Stateless);
        var fn = t.AsAIFunction(requireApproval: true);
        Assert.IsType<ApprovalRequiredAIFunction>(fn);
    }

    [Theory]
    [InlineData("host", "65534:65534", true, true, false)]   // network=host => relaxed
    [InlineData("none", "0:0", true, true, false)]            // root user => relaxed
    [InlineData("none", "root", true, true, false)]           // root by name => relaxed
    [InlineData("none", "65534:65534", false, true, false)]   // writable root => relaxed
    public async Task AsAIFunction_RelaxedConfig_DefaultsToApprovalGated(
        string network, string user, bool readOnlyRoot, bool mountReadonly, bool _)
    {
        await using var t = new DockerShellTool(
            mode: ShellMode.Stateless,
            network: network,
            user: user,
            readOnlyRoot: readOnlyRoot,
            mountReadonly: mountReadonly);
        Assert.False(t.IsHardenedConfiguration);

        var fn = t.AsAIFunction();
        Assert.IsType<ApprovalRequiredAIFunction>(fn);
    }

    [Fact]
    public async Task AsAIFunction_ExtraRunArgs_DefaultsToApprovalGated()
    {
        await using var t = new DockerShellTool(
            mode: ShellMode.Stateless,
            extraRunArgs: s_privilegedExtraRunArgs);
        Assert.False(t.IsHardenedConfiguration);

        var fn = t.AsAIFunction();
        Assert.IsType<ApprovalRequiredAIFunction>(fn);
    }

    [Fact]
    public async Task AsAIFunction_RelaxedButExplicitOptOut_IsNotApprovalGated()
    {
        await using var t = new DockerShellTool(
            mode: ShellMode.Stateless,
            network: "host");
        var fn = t.AsAIFunction(requireApproval: false);
        Assert.IsNotType<ApprovalRequiredAIFunction>(fn);
    }

    [Fact]
    public async Task IsAvailableAsync_NonExistentBinary_ReturnsFalseAsync()
    {
        var ok = await DockerShellTool.IsAvailableAsync(binary: "definitely-not-a-real-binary-xyz123");
        Assert.False(ok);
    }

    [Fact]
    public async Task RunAsync_RejectedCommand_ThrowsShellCommandRejectedAsync()
    {
        // Pure policy path: the policy check runs before any docker invocation,
        // so this exercises rejection without needing a Docker daemon.
        await using var t = new DockerShellTool(mode: ShellMode.Stateless);
        await Assert.ThrowsAsync<ShellCommandRejectedException>(
            () => t.RunAsync("rm -rf /"));
    }
}
