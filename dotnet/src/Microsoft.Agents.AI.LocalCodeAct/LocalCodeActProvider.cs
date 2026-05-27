// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.LocalCodeAct.Internal;
using Microsoft.Extensions.AI;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.LocalCodeAct;

/// <summary>
/// An <see cref="AIContextProvider"/> that injects a local Python <c>execute_code</c> tool
/// into the agent's tool surface.
/// </summary>
/// <remarks>
/// <para>
/// Generated code is executed in a child Python process with default-on AST allow-list
/// validation, configurable resource limits, an isolated environment, and capture of files
/// written under <see cref="FileMountMode.ReadWrite"/> mounts.
/// </para>
/// <para>
/// <strong>Security:</strong> This package is NOT a sandbox. It is intended for environments
/// that already provide process, filesystem, and network isolation (Foundry hosted agents,
/// Azure Container Instances, dedicated VMs, etc.).
/// </para>
/// </remarks>
public sealed class LocalCodeActProvider : AIContextProvider, IDisposable
{
    /// <summary>Fixed state key used to enforce a single provider per agent.</summary>
    internal const string FixedStateKey = "LocalCodeActProvider";

    private static readonly IReadOnlyList<string> s_stateKeys = [FixedStateKey];

    private readonly object _gate = new();
    private readonly LocalCodeActProviderOptions _options;
    private readonly CodeExecutor _executor;

    private readonly Dictionary<string, AIFunction> _tools = new(StringComparer.Ordinal);
    private readonly Dictionary<string, FileMount> _fileMounts = new(StringComparer.Ordinal);
    private bool _disposed;

    /// <summary>Initializes a new instance of the <see cref="LocalCodeActProvider"/> class.</summary>
    /// <param name="options">Provider configuration. Must specify the Python executable path.</param>
    public LocalCodeActProvider(LocalCodeActProviderOptions options)
    {
        _ = Throw.IfNull(options);
        if (string.IsNullOrWhiteSpace(options.PythonExecutablePath))
        {
            throw new ArgumentException("PythonExecutablePath must not be empty.", nameof(options));
        }

        this._options = options;

        var limits = options.ExecutionLimits ?? new ProcessExecutionLimits();
        var runnerScript = options.RunnerScriptPath ?? EmbeddedScripts.GetRunnerScriptPath();

        CodeValidator? validator = null;
        if (options.ValidationEnabled)
        {
            var validatorScript = options.ValidatorScriptPath ?? EmbeddedScripts.GetValidatorScriptPath();
            validator = new CodeValidator(
                options.PythonExecutablePath,
                validatorScript,
                TimeSpan.FromSeconds(limits.ValidationTimeoutSeconds),
                options.AllowedImports?.ToList(),
                options.BlockedImports?.ToList(),
                options.AllowedBuiltins?.ToList(),
                options.BlockedBuiltins?.ToList());
        }

        this._executor = new CodeExecutor(
            options.PythonExecutablePath,
            runnerScript,
            validator,
            limits,
            options.Environment,
            options.WorkingDirectory);

        if (options.Tools is not null)
        {
            foreach (var tool in options.Tools.Where(t => t is not null))
            {
                this._tools[tool.Name] = tool;
            }
        }

        if (options.FileMounts is not null)
        {
            foreach (var mount in options.FileMounts.Where(m => m is not null))
            {
                var normalized = FileMountHelper.Normalize(mount);
                this._fileMounts[normalized.MountPath] = normalized;
            }
        }
    }

    /// <inheritdoc/>
    public override IReadOnlyList<string> StateKeys => s_stateKeys;

    // -------------------------------------------------------------------
    // Tool registry
    // -------------------------------------------------------------------

    /// <summary>Adds tools to the provider-owned tool registry. Duplicate names replace existing entries.</summary>
    public void AddTools(params AIFunction[] tools)
    {
        _ = Throw.IfNull(tools);
        lock (this._gate)
        {
            this.ThrowIfDisposed();
            foreach (var tool in tools.Where(t => t is not null))
            {
                this._tools[tool.Name] = tool;
            }
        }
    }

    /// <summary>Returns the currently registered tools.</summary>
    public IReadOnlyList<AIFunction> GetTools()
    {
        lock (this._gate)
        {
            return this._tools.Values.ToList();
        }
    }

    /// <summary>Removes tools by name.</summary>
    public void RemoveTools(params string[] names)
    {
        _ = Throw.IfNull(names);
        lock (this._gate)
        {
            foreach (var name in names.Where(n => n is not null))
            {
                _ = this._tools.Remove(name);
            }
        }
    }

    /// <summary>Removes all registered tools.</summary>
    public void ClearTools()
    {
        lock (this._gate)
        {
            this._tools.Clear();
        }
    }

    // -------------------------------------------------------------------
    // File mounts
    // -------------------------------------------------------------------

    /// <summary>Adds file mounts. Duplicate mount paths replace existing entries.</summary>
    public void AddFileMounts(params FileMount[] mounts)
    {
        _ = Throw.IfNull(mounts);
        lock (this._gate)
        {
            this.ThrowIfDisposed();
            foreach (var mount in mounts.Where(m => m is not null))
            {
                var normalized = FileMountHelper.Normalize(mount);
                this._fileMounts[normalized.MountPath] = normalized;
            }
        }
    }

    /// <summary>Returns the currently registered file mounts.</summary>
    public IReadOnlyList<FileMount> GetFileMounts()
    {
        lock (this._gate)
        {
            return this._fileMounts.Values.ToList();
        }
    }

    /// <summary>Removes file mounts by mount path.</summary>
    public void RemoveFileMounts(params string[] mountPaths)
    {
        _ = Throw.IfNull(mountPaths);
        lock (this._gate)
        {
            foreach (var path in mountPaths.Where(p => p is not null))
            {
                _ = this._fileMounts.Remove(path);
            }
        }
    }

    /// <summary>Removes all registered file mounts.</summary>
    public void ClearFileMounts()
    {
        lock (this._gate)
        {
            this._fileMounts.Clear();
        }
    }

    // -------------------------------------------------------------------
    // AIContextProvider implementation
    // -------------------------------------------------------------------

    /// <inheritdoc/>
    protected override ValueTask<AIContext> ProvideAIContextAsync(InvokingContext context, CancellationToken cancellationToken = default)
    {
        _ = Throw.IfNull(context);

        CodeExecutor.RunSnapshot snapshot;
        lock (this._gate)
        {
            this.ThrowIfDisposed();
            snapshot = new CodeExecutor.RunSnapshot(
                this._tools.Values.ToList(),
                this._fileMounts.Values.ToList());
        }

        var description = InstructionBuilder.BuildExecuteCodeDescription(snapshot.Tools, snapshot.FileMounts);
        var executeCode = new ExecuteCodeFunction(this._executor, snapshot, description);

        var instructions = InstructionBuilder.BuildContextInstructions();

        return new ValueTask<AIContext>(new AIContext
        {
            Instructions = instructions,
            Tools = [executeCode],
        });
    }

    private void ThrowIfDisposed() => ObjectDisposedException.ThrowIf(this._disposed, this);

    /// <inheritdoc/>
    public void Dispose()
    {
        lock (this._gate)
        {
            this._disposed = true;
        }
    }
}
