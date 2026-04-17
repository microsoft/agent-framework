// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using Microsoft.Agents.AI.Hyperlight.Internal;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Hyperlight;

/// <summary>
/// Standalone <c>execute_code</c> <see cref="AIFunction"/> backed by a
/// Hyperlight sandbox. Use this for manual/static wiring when an
/// <see cref="AIContextProvider"/> lifecycle is not needed — for example
/// when the tool registry and capability configuration are fixed for the
/// lifetime of the agent.
/// </summary>
/// <remarks>
/// Unlike <see cref="HyperlightCodeActProvider"/>, this type does not hook
/// into the <see cref="AIContextProvider"/> pipeline. It captures a single
/// snapshot of the provided <see cref="HyperlightCodeActProviderOptions"/>
/// at construction time and reuses it for the lifetime of the instance.
/// </remarks>
public sealed class HyperlightExecuteCodeFunction : IDisposable
{
    private readonly SandboxExecutor _executor;
    private readonly SandboxExecutor.RunSnapshot _snapshot;
    private readonly AIFunction _function;
    private bool _disposed;

    /// <summary>
    /// Initializes a new instance of the <see cref="HyperlightExecuteCodeFunction"/> class.
    /// </summary>
    /// <param name="options">
    /// Optional configuration options. When <see langword="null"/> the defaults of
    /// <see cref="HyperlightCodeActProviderOptions"/> are used.
    /// </param>
    public HyperlightExecuteCodeFunction(HyperlightCodeActProviderOptions? options = null)
    {
        var effective = options ?? new HyperlightCodeActProviderOptions();
        this._executor = new SandboxExecutor(effective);

        var tools = (effective.Tools?.Where(t => t is not null) ?? []).ToArray();
        var fileMounts = (effective.FileMounts?.Where(m => m is not null) ?? []).ToArray();
        var allowedDomains = (effective.AllowedDomains?.Where(d => d is not null) ?? []).ToArray();

        this._snapshot = new SandboxExecutor.RunSnapshot(tools, fileMounts, allowedDomains, effective.WorkspaceRoot);

        var description = InstructionBuilder.BuildExecuteCodeDescription(
            this._snapshot.Tools,
            this._snapshot.FileMounts,
            this._snapshot.AllowedDomains,
            this._snapshot.WorkspaceRoot);

        AIFunction function = new ExecuteCodeFunction(this._executor, this._snapshot, description);
        if (HyperlightCodeActProvider.ComputeApprovalRequired(effective.ApprovalMode, this._snapshot.Tools))
        {
            function = new ApprovalRequiredAIFunction(function);
        }

        this._function = function;
    }

    /// <summary>
    /// Returns the <c>execute_code</c> function for direct registration on an agent.
    /// When approval is required the returned function is wrapped in
    /// <see cref="ApprovalRequiredAIFunction"/>.
    /// </summary>
    public AIFunction AsAIFunction()
    {
        this.ThrowIfDisposed();
        return this._function;
    }

    /// <summary>
    /// Builds a CodeAct instruction string describing the available tools and capabilities.
    /// </summary>
    /// <param name="toolsVisibleToModel">
    /// When <see langword="false"/>, the instructions assume tools are only accessible
    /// through CodeAct (via <c>call_tool</c>). When <see langword="true"/>, the instructions
    /// are abbreviated for cases where the same tools are already visible to the model as
    /// direct agent tools.
    /// </param>
    public string BuildInstructions(bool toolsVisibleToModel = false)
    {
        this.ThrowIfDisposed();
        return InstructionBuilder.BuildContextInstructions(toolsVisibleToModel);
    }

    private void ThrowIfDisposed()
    {
        if (this._disposed)
        {
            throw new ObjectDisposedException(nameof(HyperlightExecuteCodeFunction));
        }
    }

    /// <summary>Releases the underlying sandbox and associated native resources.</summary>
    public void Dispose()
    {
        if (this._disposed)
        {
            return;
        }

        this._disposed = true;
        this._executor.Dispose();
    }
}
