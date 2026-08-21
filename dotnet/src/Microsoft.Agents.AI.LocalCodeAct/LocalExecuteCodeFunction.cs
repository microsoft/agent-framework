// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Linq;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.LocalCodeAct.Internal;
using Microsoft.Extensions.AI;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.LocalCodeAct;

/// <summary>
/// Standalone <c>execute_code</c> <see cref="AIFunction"/> that runs Python locally in a subprocess.
/// </summary>
/// <remarks>
/// Use this when you want to expose code execution directly as a model-facing function without
/// the <see cref="LocalCodeActProvider"/> indirection. Tools and file mounts are captured at
/// construction time and immutable for the lifetime of the function.
/// </remarks>
public sealed class LocalExecuteCodeFunction : AIFunction
{
    private const string ExecuteCodeName = "execute_code";

    private readonly CodeExecutor _executor;
    private readonly CodeExecutor.RunSnapshot _snapshot;
    private readonly AIFunction _inner;

    /// <summary>Initializes a new instance of the <see cref="LocalExecuteCodeFunction"/> class.</summary>
    /// <param name="pythonExecutablePath">Path to the Python interpreter used for execution and validation.</param>
    /// <param name="options">Optional function configuration.</param>
    public LocalExecuteCodeFunction(string pythonExecutablePath, LocalCodeActProviderOptions? options = null)
    {
        _ = Throw.IfNullOrWhitespace(pythonExecutablePath);
        options ??= new LocalCodeActProviderOptions();

        var limits = options.ExecutionLimits ?? new ProcessExecutionLimits();
        var runnerScript = options.RunnerScriptPath ?? EmbeddedScripts.GetRunnerScriptPath();

        CodeValidator? validator = null;
        if (!options.ValidationDisabled)
        {
            var validatorScript = options.ValidatorScriptPath ?? EmbeddedScripts.GetValidatorScriptPath();
            validator = new CodeValidator(
                pythonExecutablePath,
                validatorScript,
                TimeSpan.FromSeconds(limits.ValidationTimeoutSeconds),
                options.AllowedImports?.ToList(),
                options.BlockedImports?.ToList(),
                options.AllowedBuiltins?.ToList(),
                options.BlockedBuiltins?.ToList());
        }

        var tools = options.Tools?.Where(t => t is not null).ToList() ?? new List<AIFunction>();
        var fileMounts = options.FileMounts?.Where(m => m is not null).Select(FileMountHelper.Normalize).ToList() ?? new List<FileMount>();

        this._executor = new CodeExecutor(
            pythonExecutablePath,
            runnerScript,
            validator,
            limits,
            options.Environment,
            options.WorkingDirectory);

        this._snapshot = new CodeExecutor.RunSnapshot(tools, fileMounts);
        this._inner = AIFunctionFactory.Create(
            this.ExecuteCodeAsync,
            new AIFunctionFactoryOptions
            {
                Name = ExecuteCodeName,
                Description = InstructionBuilder.BuildExecuteCodeDescription(tools, fileMounts),
            });
    }

    /// <inheritdoc/>
    public override string Name => this._inner.Name;

    /// <inheritdoc/>
    public override string Description => this._inner.Description;

    /// <inheritdoc/>
    public override JsonElement JsonSchema => this._inner.JsonSchema;

    /// <inheritdoc/>
    protected override ValueTask<object?> InvokeCoreAsync(AIFunctionArguments arguments, CancellationToken cancellationToken) =>
        this._inner.InvokeAsync(arguments, cancellationToken);

    private async ValueTask<object?> ExecuteCodeAsync(
        [Description("Python source code to execute locally in the agent environment.")] string code,
        CancellationToken cancellationToken)
        => string.IsNullOrWhiteSpace(code)
            ? throw new ArgumentException("Parameter 'code' must not be empty.", nameof(code))
            : await this._executor.ExecuteAsync(this._snapshot, code, cancellationToken).ConfigureAwait(false);
}
