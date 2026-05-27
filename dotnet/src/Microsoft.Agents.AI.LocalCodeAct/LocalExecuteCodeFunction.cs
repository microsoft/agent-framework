// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
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

    private static readonly JsonElement s_schema = JsonDocument.Parse(
        """
        {
          "type": "object",
          "properties": {
            "code": {
              "type": "string",
              "description": "Python source code to execute locally in the agent environment."
            }
          },
          "required": ["code"]
        }
        """).RootElement;

    private readonly CodeExecutor _executor;
    private readonly CodeExecutor.RunSnapshot _snapshot;
    private readonly string _description;

    /// <summary>Initializes a new instance of the <see cref="LocalExecuteCodeFunction"/> class.</summary>
    /// <param name="options">Configuration including the Python executable path.</param>
    public LocalExecuteCodeFunction(LocalCodeActProviderOptions options)
    {
        _ = Throw.IfNull(options);
        if (string.IsNullOrWhiteSpace(options.PythonExecutablePath))
        {
            throw new ArgumentException("PythonExecutablePath must not be empty.", nameof(options));
        }

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

        var tools = options.Tools?.Where(t => t is not null).ToList() ?? new List<AIFunction>();
        var fileMounts = options.FileMounts?.Where(m => m is not null).Select(FileMountHelper.Normalize).ToList() ?? new List<FileMount>();

        this._executor = new CodeExecutor(
            options.PythonExecutablePath,
            runnerScript,
            validator,
            limits,
            options.Environment,
            options.WorkingDirectory);

        this._snapshot = new CodeExecutor.RunSnapshot(tools, fileMounts);
        this._description = InstructionBuilder.BuildExecuteCodeDescription(tools, fileMounts);
    }

    /// <inheritdoc/>
    public override string Name => ExecuteCodeName;

    /// <inheritdoc/>
    public override string Description => this._description;

    /// <inheritdoc/>
    public override JsonElement JsonSchema => s_schema;

    /// <inheritdoc/>
    protected override async ValueTask<object?> InvokeCoreAsync(AIFunctionArguments arguments, CancellationToken cancellationToken)
    {
        if (arguments is null || !arguments.TryGetValue("code", out var codeObj) || codeObj is null)
        {
            throw new ArgumentException("Missing required parameter 'code'.", nameof(arguments));
        }

        var code = codeObj switch
        {
            string s => s,
            JsonElement { ValueKind: JsonValueKind.String } el => el.GetString() ?? string.Empty,
            System.Text.Json.Nodes.JsonValue jv when jv.TryGetValue<string>(out var s2) => s2,
            _ => codeObj.ToString() ?? string.Empty,
        };

        if (string.IsNullOrWhiteSpace(code))
        {
            throw new ArgumentException("Parameter 'code' must not be empty.", nameof(arguments));
        }

        return await this._executor.ExecuteAsync(this._snapshot, code, cancellationToken).ConfigureAwait(false);
    }
}
