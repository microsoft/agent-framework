// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Tools.Shell;

namespace Microsoft.Agents.AI.Tools.Shell.UnitTests;

/// <summary>
/// Tests for the side-effect-free argv builders on <see cref="DockerShellTool"/>.
/// These don't require a Docker daemon to run.
/// </summary>
public sealed class DockerShellToolTests
{
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
    private static readonly string[] s_expectedStateless = new[] { "podman", "exec", "-i", "ctr", "bash", "-c" };

    [Fact]
    public void BuildExecArgv_Interactive_AddsBashNoProfile()
    {
        var argv = DockerShellTool.BuildExecArgv("docker", "af-shell-x", interactive: true);
        Assert.Equal(s_expectedInteractive, argv);
    }

    [Fact]
    public void BuildExecArgv_Stateless_AddsDashC()
    {
        var argv = DockerShellTool.BuildExecArgv("podman", "ctr", interactive: false);
        Assert.Equal(s_expectedStateless, argv);
    }

    [Fact]
    public void Ctor_GeneratesUniqueContainerName()
    {
        using var t1 = new DockerShellTool(mode: ShellMode.Stateless);
        using var t2 = new DockerShellTool(mode: ShellMode.Stateless);
        Assert.StartsWith("af-shell-", t1.ContainerName, StringComparison.Ordinal);
        Assert.StartsWith("af-shell-", t2.ContainerName, StringComparison.Ordinal);
        Assert.NotEqual(t1.ContainerName, t2.ContainerName);
    }

    [Fact]
    public void Ctor_RespectsExplicitContainerName()
    {
        using var t = new DockerShellTool(containerName: "my-explicit-name", mode: ShellMode.Stateless);
        Assert.Equal("my-explicit-name", t.ContainerName);
    }

    [Fact]
    public void IShellExecutor_DockerShellTool_ImplementsInterface()
    {
        using var t = new DockerShellTool(mode: ShellMode.Stateless);
        IShellExecutor executor = t;
        Assert.NotNull(executor);
    }

    [Fact]
    public void AsAIFunction_DefaultIsNotApprovalGated()
    {
        // Container is the boundary; approval is opt-in for DockerShellTool.
        using var t = new DockerShellTool(mode: ShellMode.Stateless);
        var fn = t.AsAIFunction();
        Assert.IsNotType<Microsoft.Extensions.AI.ApprovalRequiredAIFunction>(fn);
        Assert.Equal("run_shell", fn.Name);
    }

    [Fact]
    public void AsAIFunction_OptInApproval_WrapsInApprovalRequired()
    {
        using var t = new DockerShellTool(mode: ShellMode.Stateless);
        var fn = t.AsAIFunction(requireApproval: true);
        Assert.IsType<Microsoft.Extensions.AI.ApprovalRequiredAIFunction>(fn);
    }

    [Fact]
    public async Task IsAvailableAsync_NonExistentBinary_ReturnsFalse()
    {
        var ok = await DockerShellTool.IsAvailableAsync(binary: "definitely-not-a-real-binary-xyz123");
        Assert.False(ok);
    }
}
