// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
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
    private bool _disposed;

    /// <summary>
    /// Snapshot of tools captured at the start of a run. This is exposed
    /// through <see cref="RunSnapshot"/> so concurrent runs observe a
    /// stable view of the provider registry.
    /// </summary>
    public SandboxExecutor(HyperlightCodeActProviderOptions options)
    {
        this._options = options;
    }

    /// <summary>
    /// Immutable snapshot of provider state at the start of a run.
    /// Used to build a run-scoped <c>execute_code</c> function that is
    /// independent of subsequent CRUD mutations.
    /// </summary>
    internal sealed record RunSnapshot(
        IReadOnlyList<AIFunction> Tools,
        IReadOnlyList<FileMount> FileMounts,
        IReadOnlyList<AllowedDomain> AllowedDomains,
        string? WorkspaceRoot);

    /// <summary>
    /// Executes <paramref name="code"/> inside the sandbox using the
    /// captured <paramref name="snapshot"/>. On first invocation the
    /// sandbox is lazily initialized and a clean "warm" snapshot is
    /// captured for subsequent restores.
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
        if (this._sandbox is not null)
        {
            return;
        }

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

        var workspaceRoot = snapshot.WorkspaceRoot;
        if (!string.IsNullOrEmpty(workspaceRoot))
        {
            builder = builder.WithInputDir(workspaceRoot!);
        }

        // The Hyperlight .NET SDK currently exposes only a single input + output + temp-output
        // surface; per-mount configuration (`FileMount`) is captured in the execute_code
        // description so the model is aware of the layout, and will be wired to a richer
        // mount API once the SDK exposes one.
        if (snapshot.FileMounts.Count > 0 || !string.IsNullOrEmpty(workspaceRoot))
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
