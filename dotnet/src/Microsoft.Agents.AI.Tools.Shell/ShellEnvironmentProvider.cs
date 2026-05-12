// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Agents.AI.Tools.Shell;

/// <summary>
/// An <see cref="AIContextProvider"/> that probes the underlying shell
/// (OS, shell family/version, working directory, available CLI tools)
/// once per session and injects an authoritative instructions block so
/// the agent emits commands in the correct shell idiom.
/// </summary>
/// <remarks>
/// <para>
/// This addresses a common failure mode where a model defaults to bash
/// syntax while talking to a PowerShell session (or vice versa). Probes
/// run through the supplied <see cref="ShellExecutor"/>, so the same
/// provider works for both <see cref="LocalShellExecutor"/> (host shell) and
/// <see cref="DockerShellExecutor"/> (container shell).
/// </para>
/// <para>
/// The provider does not expose any new tools; it augments the system
/// prompt only (<see cref="AIContext.Instructions"/>). Probe failures
/// are swallowed in a narrow set of cases — per-probe timeout
/// (<see cref="TimeoutException"/>, or an
/// <see cref="OperationCanceledException"/> caused by the
/// <see cref="ShellEnvironmentProviderOptions.ProbeTimeout"/> linked
/// token), policy rejection (<see cref="ShellCommandRejectedException"/>),
/// and process spawn / pipe failures (<see cref="IOException"/>) —
/// and surfaced as <see langword="null"/> entries in the snapshot.
/// Caller-requested cancellation (a <see cref="CancellationToken"/>
/// passed in by the host) is NOT swallowed and propagates as an
/// <see cref="OperationCanceledException"/> so shutdown paths work.
/// Other exceptions (e.g. argument errors, internal bugs) propagate
/// normally. A missing CLI never fails the agent: the model simply
/// sees fewer hints in its system prompt.
/// </para>
/// <para>
/// <b>Why <see cref="AIContext.Instructions"/> rather than
/// <see cref="AIContext.Messages"/>?</b> The shell environment
/// (OS, family, version, CWD, available CLIs) is stable runtime
/// metadata, not per-turn retrieved data. The framework's
/// <c>AgentSkillsProvider</c> uses <c>Instructions</c> for the same
/// reason; <c>TextSearchProvider</c> and <c>ChatHistoryMemoryProvider</c>
/// use <c>Messages</c> for retrieval payloads that are <em>about</em>
/// the user's question. System-prompt steering also has higher weight
/// in major providers (OpenAI, Anthropic) and benefits from prompt
/// caching, so injecting the env block as a fake user message would
/// be both weaker and more expensive.
/// </para>
/// </remarks>
public sealed class ShellEnvironmentProvider : AIContextProvider
{
    private readonly ShellExecutor _executor;
    private readonly ShellEnvironmentProviderOptions _options;
    private Task<ShellEnvironmentSnapshot>? _snapshotTask;

    /// <summary>
    /// Initializes a new instance of the <see cref="ShellEnvironmentProvider"/> class.
    /// </summary>
    /// <param name="executor">The shell executor used to run probe commands.</param>
    /// <param name="options">Optional configuration; defaults are used when <see langword="null"/>.</param>
    /// <exception cref="ArgumentNullException"><paramref name="executor"/> is <see langword="null"/>.</exception>
    public ShellEnvironmentProvider(ShellExecutor executor, ShellEnvironmentProviderOptions? options = null)
    {
        this._executor = executor ?? throw new ArgumentNullException(nameof(executor));
        this._options = options ?? new ShellEnvironmentProviderOptions();
    }

    /// <summary>
    /// Gets the most recently captured snapshot, or <see langword="null"/>
    /// if no probe has completed yet.
    /// </summary>
    public ShellEnvironmentSnapshot? CurrentSnapshot { get; private set; }

    /// <summary>
    /// Force a re-probe and refresh the cached snapshot. Useful when the
    /// agent has changed something the snapshot depends on (e.g., installed
    /// a new CLI mid-session).
    /// </summary>
    /// <param name="cancellationToken">Cancellation token.</param>
    /// <returns>The freshly captured snapshot.</returns>
    public async Task<ShellEnvironmentSnapshot> RefreshAsync(CancellationToken cancellationToken = default)
    {
        var snapshot = await this.ProbeAsync(cancellationToken).ConfigureAwait(false);
        this.CurrentSnapshot = snapshot;
        this._snapshotTask = Task.FromResult(snapshot);
        return snapshot;
    }

    /// <inheritdoc />
    protected override async ValueTask<AIContext> ProvideAIContextAsync(InvokingContext context, CancellationToken cancellationToken = default)
    {
        // First-call wins: subsequent concurrent callers await the same Task.
        // If the cached task faults or is cancelled, clear it so the next call
        // re-probes instead of permanently poisoning the provider.
        var task = this._snapshotTask;
        if (task is null)
        {
            var fresh = this.ProbeAsync(cancellationToken);
            task = Interlocked.CompareExchange(ref this._snapshotTask, fresh, null) ?? fresh;
        }

        ShellEnvironmentSnapshot snapshot;
        try
        {
            snapshot = await task.ConfigureAwait(false);
        }
        catch
        {
            // Replace the cached failed task with null only if no other thread
            // has already done so. Concurrent waiters will all observe the
            // failure once, but the next call starts a fresh probe.
            _ = Interlocked.CompareExchange(ref this._snapshotTask, null, task);
            throw;
        }

        this.CurrentSnapshot = snapshot;
        var formatter = this._options.InstructionsFormatter ?? DefaultInstructionsFormatter;
        return new AIContext { Instructions = formatter(snapshot) };
    }

    private async Task<ShellEnvironmentSnapshot> ProbeAsync(CancellationToken cancellationToken)
    {
        var family = this._options.OverrideFamily ?? DetectFamily();

        await this._executor.InitializeAsync(cancellationToken).ConfigureAwait(false);

        var (shellVersion, workingDir) = await this.ProbeShellAndCwdAsync(family, cancellationToken).ConfigureAwait(false);

        var toolVersions = new Dictionary<string, string?>(StringComparer.OrdinalIgnoreCase);
        foreach (var tool in this._options.ProbeTools)
        {
            // ProbeTools is user-supplied. Skip duplicates that differ only by
            // case (e.g., "git" and "GIT") so we don't probe the same CLI twice
            // and don't depend on dictionary insertion order for the result.
            if (toolVersions.ContainsKey(tool))
            {
                continue;
            }
            toolVersions[tool] = await this.ProbeToolVersionAsync(tool, cancellationToken).ConfigureAwait(false);
        }

        return new ShellEnvironmentSnapshot(
            Family: family,
            OSDescription: RuntimeInformation.OSDescription,
            ShellVersion: shellVersion,
            WorkingDirectory: workingDir,
            ToolVersions: toolVersions);
    }

    private async Task<(string? Version, string Cwd)> ProbeShellAndCwdAsync(ShellFamily family, CancellationToken cancellationToken)
    {
        var probe = family == ShellFamily.PowerShell
            ? "Write-Output (\"VERSION=\" + $PSVersionTable.PSVersion.ToString()); Write-Output (\"CWD=\" + (Get-Location).Path)"
            : "echo \"VERSION=${BASH_VERSION:-${ZSH_VERSION:-unknown}}\"; echo \"CWD=$PWD\"";

        var result = await this.RunProbeAsync(probe, cancellationToken).ConfigureAwait(false);
        if (result is null)
        {
            return (null, string.Empty);
        }

        string? version = null;
        string cwd = string.Empty;
        foreach (var line in result.Stdout.Split(['\r', '\n'], StringSplitOptions.RemoveEmptyEntries))
        {
            if (line.StartsWith("VERSION=", StringComparison.Ordinal))
            {
                var v = line.Substring("VERSION=".Length).Trim();
                version = string.IsNullOrEmpty(v) || v == "unknown" ? null : v;
            }
            else if (line.StartsWith("CWD=", StringComparison.Ordinal))
            {
                cwd = line.Substring("CWD=".Length).Trim();
            }
        }
        return (version, cwd);
    }

    private static readonly System.Text.RegularExpressions.Regex s_toolNamePattern =
        new("^[A-Za-z0-9._-]+$", System.Text.RegularExpressions.RegexOptions.Compiled);

    private async Task<string?> ProbeToolVersionAsync(string tool, CancellationToken cancellationToken)
    {
        // The tool name is interpolated into a shell command, so reject anything that
        // isn't a plain identifier. Whitespace, quotes, $, ;, |, &, etc. are not valid
        // in any real CLI binary name and would otherwise allow shell injection if the
        // configured tool list is sourced from untrusted input.
        if (string.IsNullOrEmpty(tool) || !s_toolNamePattern.IsMatch(tool))
        {
            return null;
        }

        var probe = $"{tool} --version";
        var result = await this.RunProbeAsync(probe, cancellationToken).ConfigureAwait(false);
        if (result is null || result.ExitCode != 0)
        {
            return null;
        }

        // Some CLIs (java, gcc on older versions) emit `--version` to stderr.
        var firstLine = FirstNonEmptyLine(result.Stdout) ?? FirstNonEmptyLine(result.Stderr);
        return string.IsNullOrWhiteSpace(firstLine) ? null : firstLine!.Trim();

        static string? FirstNonEmptyLine(string text) =>
            text.Split(['\r', '\n'], StringSplitOptions.RemoveEmptyEntries).FirstOrDefault();
    }

    private async Task<ShellResult?> RunProbeAsync(string command, CancellationToken cancellationToken)
    {
        using var cts = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
        cts.CancelAfter(this._options.ProbeTimeout);
        try
        {
            return await this._executor.RunAsync(command, cts.Token).ConfigureAwait(false);
        }
        catch (OperationCanceledException) when (!cancellationToken.IsCancellationRequested)
        {
            // Probe-timeout-driven cancellation: surface as a null snapshot field.
            // Caller-driven cancellation is allowed to propagate.
            return null;
        }
        catch (Exception ex) when (ex is ShellCommandRejectedException || ex is IOException || ex is TimeoutException)
        {
            return null;
        }
    }

    private static ShellFamily DetectFamily() =>
        RuntimeInformation.IsOSPlatform(OSPlatform.Windows)
            ? ShellFamily.PowerShell
            : ShellFamily.Posix;

    /// <summary>
    /// Default formatter for the instructions block. Public so callers
    /// who want to wrap or augment the default can call it directly.
    /// </summary>
    /// <param name="snapshot">The snapshot to render.</param>
    /// <returns>A multi-line markdown-style instructions block.</returns>
    public static string DefaultInstructionsFormatter(ShellEnvironmentSnapshot snapshot)
    {
        var sb = new StringBuilder();
        _ = sb.AppendLine("## Shell environment");

        if (snapshot.Family == ShellFamily.PowerShell)
        {
            var version = snapshot.ShellVersion is null ? string.Empty : $" {snapshot.ShellVersion}";
            _ = sb.Append("You are operating a PowerShell").Append(version).Append(" session on ").Append(snapshot.OSDescription).AppendLine(".");
            _ = sb.AppendLine("Use PowerShell idioms, NOT bash:");
            _ = sb.AppendLine("- Set environment variables with `$env:NAME = 'value'` (NOT `NAME=value`).");
            _ = sb.AppendLine("- Change directory with `Set-Location` or `cd`. Paths use `\\` separators.");
            _ = sb.AppendLine("- Reference environment variables as `$env:NAME` (NOT `$NAME`).");
            _ = sb.AppendLine("- The system temp directory is `[System.IO.Path]::GetTempPath()` (NOT `/tmp`).");
            _ = sb.AppendLine("- Pipe to `Out-Null` to suppress output (NOT `> /dev/null`).");
        }
        else
        {
            var version = snapshot.ShellVersion is null ? string.Empty : $" {snapshot.ShellVersion}";
            _ = sb.Append("You are operating a POSIX shell").Append(version).Append(" session on ").Append(snapshot.OSDescription).AppendLine(".");
            _ = sb.AppendLine("Use POSIX shell idioms (bash/sh).");
            _ = sb.AppendLine("- Set environment variables for the next command with `export NAME=value`.");
            _ = sb.AppendLine("- Reference environment variables as `$NAME` or `${NAME}`.");
            _ = sb.AppendLine("- Paths use `/` separators.");
        }

        if (!string.IsNullOrEmpty(snapshot.WorkingDirectory))
        {
            _ = sb.Append("Working directory: ").AppendLine(snapshot.WorkingDirectory);
        }

        var installed = snapshot.ToolVersions
            .Where(kv => kv.Value is not null)
            .Select(kv => $"{kv.Key} ({kv.Value})")
            .ToList();
        var missing = snapshot.ToolVersions
            .Where(kv => kv.Value is null)
            .Select(kv => kv.Key)
            .ToList();

        if (installed.Count > 0)
        {
            _ = sb.Append("Available CLIs: ").AppendLine(string.Join(", ", installed));
        }
        if (missing.Count > 0)
        {
            _ = sb.Append("Not installed: ").AppendLine(string.Join(", ", missing));
        }

        return sb.ToString().TrimEnd();
    }
}
