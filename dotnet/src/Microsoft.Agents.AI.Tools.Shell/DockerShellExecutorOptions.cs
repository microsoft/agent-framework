// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;

namespace Microsoft.Agents.AI.Tools.Shell;

/// <summary>
/// Configuration for <see cref="DockerShellExecutor"/>. New knobs will be
/// added as properties here so the constructor surface stays binary-stable.
/// </summary>
public sealed class DockerShellExecutorOptions
{
    /// <summary>OCI image to run. Must include <c>bash</c> and (for persistent mode) <c>sleep</c>.</summary>
    public string Image { get; set; } = DockerShellExecutor.DefaultImage;

    /// <summary>Optional container name. When <see langword="null"/>, a unique name is generated.</summary>
    public string? ContainerName { get; set; }

    /// <summary>
    /// Execution mode. Defaults to <see cref="ShellMode.Persistent"/>.
    /// <para>
    /// In <see cref="ShellMode.Persistent"/> the resulting executor instance owns a
    /// long-lived container plus the bash REPL inside it, and is intended to be owned
    /// by a single conversation / agent session; do not share it across users or
    /// concurrent sessions. See <see cref="DockerShellExecutor"/> remarks.
    /// </para>
    /// </summary>
    public ShellMode Mode { get; set; } = ShellMode.Persistent;

    /// <summary>Optional host directory mounted at <see cref="ContainerWorkdir"/>.</summary>
    public string? HostWorkdir { get; set; }

    /// <summary>Path inside the container. Defaults to <c>/workspace</c>.</summary>
    public string ContainerWorkdir { get; set; } = DockerShellExecutor.DefaultContainerWorkdir;

    /// <summary>When <see langword="true"/> (the default), the host workdir is mounted read-only.</summary>
    public bool MountReadonly { get; set; } = true;

    /// <summary>Docker network mode. Defaults to <see cref="DockerNetworkMode.None"/>.</summary>
    public string Network { get; set; } = DockerNetworkMode.None;

    /// <summary>Container memory limit, in bytes. <see langword="null"/> selects 512 MiB.</summary>
    public long? MemoryBytes { get; set; }

    /// <summary>Max processes inside the container.</summary>
    public int PidsLimit { get; set; } = DockerShellExecutor.DefaultPidsLimit;

    /// <summary>Container user. Defaults to <see cref="ContainerUser.Default"/> (nobody).</summary>
    public ContainerUser User { get; set; } = ContainerUser.Default;

    /// <summary>When <see langword="true"/> (the default), the container root filesystem is read-only.</summary>
    public bool ReadOnlyRoot { get; set; } = true;

    /// <summary>Additional args appended to <c>docker run</c>.</summary>
    public IReadOnlyList<string>? ExtraRunArgs { get; set; }

    /// <summary>Environment variables passed via <c>-e</c> to every command.</summary>
    public IReadOnlyDictionary<string, string>? Environment { get; set; }

    /// <summary>
    /// Optional <see cref="ShellPolicy"/>. When <see langword="null"/>,
    /// a default (empty) policy is used that allows any non-empty command.
    /// Container isolation is the security boundary for Docker mode; a
    /// <see cref="ShellPolicy"/> here is a UX pre-filter for shapes you
    /// would rather see rejected with a clear error than run.
    /// </summary>
    public ShellPolicy? Policy { get; set; }

    /// <summary>Per-command timeout. <see langword="null"/> disables timeouts.</summary>
    public TimeSpan? Timeout { get; set; }

    /// <summary>Per-stream cap before head+tail truncation. Defaults to 64 KiB.</summary>
    public int MaxOutputBytes { get; set; } = 64 * 1024;

    /// <summary>Override (e.g. <c>podman</c>).</summary>
    public string DockerBinary { get; set; } = "docker";
}
