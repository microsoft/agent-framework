// Copyright (c) Microsoft Corporation. All rights reserved.
// Licensed under the MIT License.

using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.LocalCodeAct;

/// <summary>
/// An <see cref="AIContextProvider"/> that enables local Python CodeAct execution.
/// </summary>
/// <remarks>
/// <para>
/// This provider injects an <c>execute_code</c> tool into the model-facing tool surface.
/// Guest Python code executed via <c>execute_code</c> runs in a subprocess with
/// the configured resource limits and AST validation.
/// </para>
/// <para>
/// <strong>Security considerations:</strong> This is NOT a security sandbox. Use only
/// in environments that already provide process, filesystem, and network isolation
/// (e.g., Azure Container Instances, VMs, Foundry hosted agents).
/// </para>
/// </remarks>
public sealed class LocalCodeActProvider : AIContextProvider, IDisposable
{
    private const string FixedStateKey = "LocalCodeActProvider";
    private static readonly IReadOnlyList<string> s_stateKeys = [FixedStateKey];

    private readonly LocalExecuteCodeFunction _function;
    private bool _disposed;

    /// <summary>
    /// Initializes a new instance of the <see cref="LocalCodeActProvider"/> class.
    /// </summary>
    /// <param name="pythonExecutablePath">Path to the Python executable (required).</param>
    /// <param name="tools">Host tools available to generated code.</param>
    /// <param name="executionLimits">Resource limits for code execution.</param>
    /// <param name="environment">Environment variables to pass to subprocess.</param>
    /// <param name="runnerScript">Optional path to bundled Python runner script.</param>
    /// <param name="allowedImports">Custom allowed imports (replaces defaults).</param>
    /// <param name="blockedImports">Custom blocked imports (replaces defaults).</param>
    /// <param name="allowedBuiltins">Custom allowed builtins (replaces defaults).</param>
    /// <param name="blockedBuiltins">Custom blocked builtins (replaces defaults).</param>
    public LocalCodeActProvider(
        string pythonExecutablePath,
        IEnumerable<AIFunction>? tools = null,
        ProcessExecutionLimits? executionLimits = null,
        IReadOnlyDictionary<string, string>? environment = null,
        string? runnerScript = null,
        string[]? allowedImports = null,
        string[]? blockedImports = null,
        string[]? allowedBuiltins = null,
        string[]? blockedBuiltins = null)
    {
        ArgumentNullException.ThrowIfNull(pythonExecutablePath);

        _function = new LocalExecuteCodeFunction(
            pythonExecutablePath,
            tools,
            executionLimits,
            environment,
            runnerScript,
            allowedImports,
            blockedImports,
            allowedBuiltins,
            blockedBuiltins);
    }

    /// <inheritdoc/>
    public override IReadOnlyList<string> StateKeys => s_stateKeys;

    /// <inheritdoc/>
    public override Task<AIContext> ProvideContextAsync(
        AIContext context,
        CancellationToken cancellationToken = default)
    {
        ObjectDisposedException.ThrowIf(_disposed, this);

        // Add execute_code tool to context
        var tools = new List<AITool>(context.Tools ?? []);
        tools.Add(_function);

        // Add CodeAct instructions
        var instructions = new List<string>(context.Instructions ?? []);
        instructions.Add("Use execute_code for Python control flow when it helps.");

        return Task.FromResult(new AIContext
        {
            Tools = tools,
            Instructions = instructions,
        });
    }

    /// <inheritdoc/>
    public void Dispose()
    {
        if (!_disposed)
        {
            _function.Dispose();
            _disposed = true;
        }
    }
}
