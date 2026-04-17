// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Hyperlight.Internal;
using Microsoft.Extensions.AI;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Hyperlight;

/// <summary>
/// An <see cref="AIContextProvider"/> that enables CodeAct execution through a
/// Hyperlight-backed sandbox.
/// </summary>
/// <remarks>
/// <para>
/// The provider injects an <c>execute_code</c> tool into the model-facing tool
/// surface and contributes a short CodeAct guidance block through
/// <see cref="AIContext.Instructions"/>. Guest code executed via
/// <c>execute_code</c> runs in an isolated Hyperlight sandbox with
/// snapshot/restore for clean state per invocation.
/// </para>
/// <para>
/// If no CodeAct-managed tools are configured the provider behaves as a code
/// interpreter. If one or more tools are configured they are exposed to guest
/// code via <c>call_tool(...)</c> but not to the model directly.
/// </para>
/// <para>
/// Only a single <see cref="HyperlightCodeActProvider"/> may be attached to a
/// given agent. <see cref="StateKeys"/> returns a fixed value so
/// <c>ChatClientAgent</c>'s state-key uniqueness validation rejects duplicate
/// registrations.
/// </para>
/// <para>
/// <strong>Security considerations:</strong> guest code runs with only the
/// capabilities explicitly configured on this provider (file mounts, allowed
/// outbound domains). Callers should configure the smallest capability set
/// sufficient for the task and consider using
/// <see cref="CodeActApprovalMode.AlwaysRequire"/> when guest code can reach
/// sensitive resources.
/// </para>
/// </remarks>
public sealed class HyperlightCodeActProvider : AIContextProvider, IDisposable
{
    /// <summary>
    /// Fixed state key used to enforce a single provider-per-agent.
    /// </summary>
    internal const string FixedStateKey = "HyperlightCodeActProvider";

    private static readonly IReadOnlyList<string> s_stateKeys = [FixedStateKey];

    private readonly object _gate = new();
    private readonly HyperlightCodeActProviderOptions _options;
    private readonly SandboxExecutor _executor;

    private readonly Dictionary<string, AIFunction> _tools = new(StringComparer.Ordinal);
    private readonly Dictionary<string, FileMount> _fileMounts = new(StringComparer.Ordinal);
    private readonly Dictionary<string, AllowedDomain> _allowedDomains = new(StringComparer.Ordinal);
    private bool _disposed;

    /// <summary>
    /// Initializes a new instance of the <see cref="HyperlightCodeActProvider"/> class.
    /// </summary>
    /// <param name="options">
    /// Optional configuration options for the provider. When <see langword="null"/> the provider
    /// uses the defaults of <see cref="HyperlightCodeActProviderOptions"/> — equivalent to a
    /// <see cref="SandboxBackend.Wasm"/> backend with no module, tools, mounts, or allow-list entries.
    /// </param>
    public HyperlightCodeActProvider(HyperlightCodeActProviderOptions? options = null)
    {
        this._options = options ?? new HyperlightCodeActProviderOptions();
        this._executor = new SandboxExecutor(this._options);

        if (this._options.Tools is not null)
        {
            foreach (var tool in this._options.Tools)
            {
                if (tool is null)
                {
                    continue;
                }

                this._tools[tool.Name] = tool;
            }
        }

        if (this._options.FileMounts is not null)
        {
            foreach (var mount in this._options.FileMounts)
            {
                if (mount is null)
                {
                    continue;
                }

                this._fileMounts[mount.MountPath] = mount;
            }
        }

        if (this._options.AllowedDomains is not null)
        {
            foreach (var domain in this._options.AllowedDomains)
            {
                if (domain is null)
                {
                    continue;
                }

                this._allowedDomains[domain.Target] = domain;
            }
        }
    }

    /// <inheritdoc />
    public override IReadOnlyList<string> StateKeys => s_stateKeys;

    // -------------------------------------------------------------------
    // Tool registry
    // -------------------------------------------------------------------

    /// <summary>Adds tools to the provider-owned CodeAct tool registry. Tools with a duplicate name replace the existing registration.</summary>
    /// <param name="tools">The tools to add.</param>
    public void AddTools(params AIFunction[] tools)
    {
        _ = Throw.IfNull(tools);
        lock (this._gate)
        {
            this.ThrowIfDisposed();
            foreach (var tool in tools)
            {
                if (tool is null)
                {
                    continue;
                }

                this._tools[tool.Name] = tool;
            }
        }
    }

    /// <summary>Returns the current CodeAct-managed tools.</summary>
    public IReadOnlyList<AIFunction> GetTools()
    {
        lock (this._gate)
        {
            return this._tools.Values.ToArray();
        }
    }

    /// <summary>Removes tools by name from the CodeAct tool registry.</summary>
    /// <param name="names">The names of the tools to remove.</param>
    public void RemoveTools(params string[] names)
    {
        _ = Throw.IfNull(names);
        lock (this._gate)
        {
            foreach (var name in names)
            {
                if (name is null)
                {
                    continue;
                }

                _ = this._tools.Remove(name);
            }
        }
    }

    /// <summary>Removes all CodeAct-managed tools.</summary>
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

    /// <summary>Adds file mount configurations. Mounts with a duplicate mount path replace the existing entry.</summary>
    /// <param name="mounts">The mount configurations to add.</param>
    public void AddFileMounts(params FileMount[] mounts)
    {
        _ = Throw.IfNull(mounts);
        lock (this._gate)
        {
            foreach (var mount in mounts)
            {
                if (mount is null)
                {
                    continue;
                }

                this._fileMounts[mount.MountPath] = mount;
            }
        }
    }

    /// <summary>Returns the current file mount configurations.</summary>
    public IReadOnlyList<FileMount> GetFileMounts()
    {
        lock (this._gate)
        {
            return this._fileMounts.Values.ToArray();
        }
    }

    /// <summary>Removes file mounts by sandbox mount path.</summary>
    /// <param name="mountPaths">The mount paths to remove.</param>
    public void RemoveFileMounts(params string[] mountPaths)
    {
        _ = Throw.IfNull(mountPaths);
        lock (this._gate)
        {
            foreach (var path in mountPaths)
            {
                if (path is null)
                {
                    continue;
                }

                _ = this._fileMounts.Remove(path);
            }
        }
    }

    /// <summary>Removes all file mount configurations.</summary>
    public void ClearFileMounts()
    {
        lock (this._gate)
        {
            this._fileMounts.Clear();
        }
    }

    // -------------------------------------------------------------------
    // Network allow-list
    // -------------------------------------------------------------------

    /// <summary>Adds outbound network allow-list entries. Entries with a duplicate target replace the existing entry.</summary>
    /// <param name="domains">The allow-list entries to add.</param>
    public void AddAllowedDomains(params AllowedDomain[] domains)
    {
        _ = Throw.IfNull(domains);
        lock (this._gate)
        {
            foreach (var domain in domains)
            {
                if (domain is null)
                {
                    continue;
                }

                this._allowedDomains[domain.Target] = domain;
            }
        }
    }

    /// <summary>Returns the current outbound allow-list entries.</summary>
    public IReadOnlyList<AllowedDomain> GetAllowedDomains()
    {
        lock (this._gate)
        {
            return this._allowedDomains.Values.ToArray();
        }
    }

    /// <summary>Removes allow-list entries by target.</summary>
    /// <param name="targets">The targets to remove.</param>
    public void RemoveAllowedDomains(params string[] targets)
    {
        _ = Throw.IfNull(targets);
        lock (this._gate)
        {
            foreach (var target in targets)
            {
                if (target is null)
                {
                    continue;
                }

                _ = this._allowedDomains.Remove(target);
            }
        }
    }

    /// <summary>Removes all outbound allow-list entries.</summary>
    public void ClearAllowedDomains()
    {
        lock (this._gate)
        {
            this._allowedDomains.Clear();
        }
    }

    // -------------------------------------------------------------------
    // AIContextProvider implementation
    // -------------------------------------------------------------------

    /// <inheritdoc />
    protected override ValueTask<AIContext> ProvideAIContextAsync(InvokingContext context, CancellationToken cancellationToken = default)
    {
        _ = Throw.IfNull(context);

        SandboxExecutor.RunSnapshot snapshot;
        lock (this._gate)
        {
            this.ThrowIfDisposed();
            snapshot = new SandboxExecutor.RunSnapshot(
                this._tools.Values.ToArray(),
                this._fileMounts.Values.ToArray(),
                this._allowedDomains.Values.ToArray(),
                this._options.WorkspaceRoot);
        }

        var approvalRequired = ComputeApprovalRequired(this._options.ApprovalMode, snapshot.Tools);

        var description = InstructionBuilder.BuildExecuteCodeDescription(
            snapshot.Tools,
            snapshot.FileMounts,
            snapshot.AllowedDomains,
            snapshot.WorkspaceRoot);

        AIFunction executeCode = new ExecuteCodeFunction(this._executor, snapshot, description);
        if (approvalRequired)
        {
            executeCode = new ApprovalRequiredAIFunction(executeCode);
        }

        var instructions = InstructionBuilder.BuildContextInstructions(toolsVisibleToModel: false);

        var result = new AIContext
        {
            Instructions = instructions,
            Tools = [executeCode],
        };

        return new ValueTask<AIContext>(result);
    }

    internal static bool ComputeApprovalRequired(CodeActApprovalMode mode, IReadOnlyList<AIFunction> tools)
    {
        if (mode == CodeActApprovalMode.AlwaysRequire)
        {
            return true;
        }

        foreach (var tool in tools)
        {
            if (tool is ApprovalRequiredAIFunction)
            {
                return true;
            }
        }

        return false;
    }

    private void ThrowIfDisposed()
    {
        if (this._disposed)
        {
            throw new ObjectDisposedException(nameof(HyperlightCodeActProvider));
        }
    }

    /// <summary>Releases the underlying sandbox and associated native resources.</summary>
    public void Dispose()
    {
        lock (this._gate)
        {
            if (this._disposed)
            {
                return;
            }

            this._disposed = true;
        }

        this._executor.Dispose();
    }
}
