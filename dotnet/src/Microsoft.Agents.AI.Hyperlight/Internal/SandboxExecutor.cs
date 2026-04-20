// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using HyperlightSandbox.Api;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Hyperlight.Internal;

/// <summary>
/// Captures a per-run snapshot of the provider state and owns the
/// lifecycle of the underlying <see cref="Sandbox"/>. A single
/// <see cref="SandboxExecutor"/> is shared across runs and serializes
/// execution via snapshot/restore.
/// </summary>
internal sealed class SandboxExecutor : IDisposable
{
    private readonly HyperlightCodeActProviderOptions _options;
    private readonly SemaphoreSlim _executionLock = new(1, 1);

    private Sandbox? _sandbox;
    private SandboxSnapshot? _warmSnapshot;
    private string? _lastConfigFingerprint;
    private bool _disposed;

    public SandboxExecutor(HyperlightCodeActProviderOptions options)
    {
        this._options = options;
    }

    /// <summary>
    /// Immutable snapshot of provider state at the start of a run.
    /// Used to build a run-scoped <c>execute_code</c> function that is
    /// independent of subsequent CRUD mutations.
    /// </summary>
    internal sealed class RunSnapshot
    {
        public RunSnapshot(
            IReadOnlyList<AIFunction> tools,
            IReadOnlyList<FileMount> fileMounts,
            IReadOnlyList<AllowedDomain> allowedDomains,
            string? hostInputDirectory)
        {
            this.Tools = tools;
            this.FileMounts = fileMounts;
            this.AllowedDomains = allowedDomains;
            this.HostInputDirectory = hostInputDirectory;
            this.ConfigFingerprint = ComputeFingerprint(tools, fileMounts, allowedDomains, hostInputDirectory);
        }

        public IReadOnlyList<AIFunction> Tools { get; }

        public IReadOnlyList<FileMount> FileMounts { get; }

        public IReadOnlyList<AllowedDomain> AllowedDomains { get; }

        public string? HostInputDirectory { get; }

        /// <summary>
        /// Stable fingerprint of the configuration that materially affects how
        /// the sandbox must be built. Used by <see cref="SandboxExecutor"/> to
        /// decide whether a previously-built sandbox can be reused or must be
        /// rebuilt because tools / mounts / allow-list entries have changed.
        /// </summary>
        public string ConfigFingerprint { get; }

        internal static string ComputeFingerprint(
            IReadOnlyList<AIFunction> tools,
            IReadOnlyList<FileMount> fileMounts,
            IReadOnlyList<AllowedDomain> allowedDomains,
            string? hostInputDirectory)
        {
            var sb = new StringBuilder();
            sb.Append("tools=");
            foreach (var name in tools.Select(t => t.Name).OrderBy(n => n, StringComparer.Ordinal))
            {
                sb.Append(name).Append('|');
            }

            sb.Append(";mounts=");
            foreach (var m in fileMounts
                .Select(m => m.MountPath + "->" + m.HostPath)
                .OrderBy(s => s, StringComparer.Ordinal))
            {
                sb.Append(m).Append('|');
            }

            sb.Append(";allow=");
            foreach (var d in allowedDomains
                .Select(d => d.Target + "/" + (d.Methods is null ? "*" : string.Join(",", d.Methods)))
                .OrderBy(s => s, StringComparer.Ordinal))
            {
                sb.Append(d).Append('|');
            }

            sb.Append(";input=").Append(hostInputDirectory ?? string.Empty);
            return sb.ToString();
        }
    }

    /// <summary>
    /// Executes <paramref name="code"/> inside the sandbox using the
    /// captured <paramref name="snapshot"/>. Builds (or rebuilds) the
    /// sandbox lazily when the snapshot's configuration fingerprint
    /// differs from the previously-used one.
    /// </summary>
    public async Task<string> ExecuteAsync(RunSnapshot snapshot, string code, CancellationToken cancellationToken)
    {
        await this._executionLock.WaitAsync(cancellationToken).ConfigureAwait(false);
        try
        {
            this.EnsureInitialized(snapshot);

            if (this._warmSnapshot is not null)
            {
                this._sandbox!.Restore(this._warmSnapshot);
            }

            ExecutionResult result;
            try
            {
                result = this._sandbox!.Run(code);
            }
#pragma warning disable CA1031 // Surface sandbox execution failures as structured JSON rather than propagating.
            catch (Exception ex)
#pragma warning restore CA1031
            {
                return BuildErrorResult(ex.Message);
            }

            return BuildResult(result);
        }
        finally
        {
            this._executionLock.Release();
        }
    }

    private void EnsureInitialized(RunSnapshot snapshot)
    {
        if (this._sandbox is not null && string.Equals(this._lastConfigFingerprint, snapshot.ConfigFingerprint, StringComparison.Ordinal))
        {
            return;
        }

        // Configuration changed (or first run) — dispose the previous sandbox
        // so the new one picks up the new tool/mount/allow-list set.
        this._warmSnapshot?.Dispose();
        this._sandbox?.Dispose();
        this._warmSnapshot = null;
        this._sandbox = null;

        this.BuildAndWarmUp(snapshot);
    }

    private void BuildAndWarmUp(RunSnapshot snapshot)
    {
        var builder = new SandboxBuilder()
            .WithBackend(this._options.Backend);

        if (!string.IsNullOrEmpty(this._options.ModulePath))
        {
            builder = builder.WithModulePath(this._options.ModulePath!);
        }

        if (!string.IsNullOrEmpty(this._options.HeapSize))
        {
            builder = builder.WithHeapSize(this._options.HeapSize!);
        }

        if (!string.IsNullOrEmpty(this._options.StackSize))
        {
            builder = builder.WithStackSize(this._options.StackSize!);
        }

        var hostInput = snapshot.HostInputDirectory;
        if (!string.IsNullOrEmpty(hostInput))
        {
            builder = builder.WithInputDir(hostInput!);
        }

        // The Hyperlight .NET SDK currently exposes only a single input + output + temp-output
        // surface; per-mount configuration (`FileMount`) is captured in the execute_code
        // description so the model is aware of the layout, and will be wired to a richer
        // mount API once the SDK exposes one.
        if (snapshot.FileMounts.Count > 0 || !string.IsNullOrEmpty(hostInput))
        {
            builder = builder.WithTempOutput();
        }

        var sandbox = builder.Build();

        // Tools must be registered before the first Run() call.
        ToolBridge.RegisterAll(sandbox, snapshot.Tools);

        foreach (var allowedDomain in snapshot.AllowedDomains)
        {
            sandbox.AllowDomain(allowedDomain.Target, allowedDomain.Methods);
        }

        // Warm-up run to trigger lazy initialization, then capture a clean snapshot
        // that is restored before every subsequent user invocation.
        _ = sandbox.Run(this._options.Backend == SandboxBackend.JavaScript ? "undefined" : "None");
        this._warmSnapshot = sandbox.Snapshot();
        this._sandbox = sandbox;
        this._lastConfigFingerprint = snapshot.ConfigFingerprint;
    }

    private static string BuildResult(ExecutionResult result)
    {
        var payload = new Dictionary<string, object?>(StringComparer.Ordinal)
        {
            ["stdout"] = result.Stdout ?? string.Empty,
            ["stderr"] = result.Stderr ?? string.Empty,
            ["exit_code"] = result.ExitCode,
            ["success"] = result.ExitCode == 0,
        };

        return JsonSerializer.Serialize(payload);
    }

    private static string BuildErrorResult(string message)
    {
        var payload = new Dictionary<string, object?>(StringComparer.Ordinal)
        {
            ["stdout"] = string.Empty,
            ["stderr"] = message,
            ["exit_code"] = -1,
            ["success"] = false,
        };

        return JsonSerializer.Serialize(payload);
    }

    public void Dispose()
    {
        if (this._disposed)
        {
            return;
        }

        this._disposed = true;
        this._warmSnapshot?.Dispose();
        this._sandbox?.Dispose();
        this._executionLock.Dispose();
    }
}
