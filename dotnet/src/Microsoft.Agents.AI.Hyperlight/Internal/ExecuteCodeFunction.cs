// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Hyperlight.Internal;

/// <summary>
/// Run-scoped <see cref="AIFunction"/> that exposes <c>execute_code</c>
/// to the model. The function closes over an immutable
/// <see cref="SandboxExecutor.RunSnapshot"/> captured at the start of the
/// agent invocation, so subsequent CRUD mutations on the provider do not
/// affect an in-flight run.
/// </summary>
internal sealed class ExecuteCodeFunction : AIFunction
{
    private const string ExecuteCodeName = "execute_code";

    private static readonly JsonElement s_schema = JsonDocument.Parse(
        """
        {
          "type": "object",
          "properties": {
            "code": {
              "type": "string",
              "description": "Code to execute using the provider's configured backend/runtime behavior."
            }
          },
          "required": ["code"]
        }
        """).RootElement;

    private readonly SandboxExecutor _executor;
    private readonly SandboxExecutor.RunSnapshot _snapshot;
    private readonly string _description;

    public ExecuteCodeFunction(
        SandboxExecutor executor,
        SandboxExecutor.RunSnapshot snapshot,
        string description)
    {
        this._executor = executor;
        this._snapshot = snapshot;
        this._description = description;
    }

    /// <inheritdoc />
    public override string Name => ExecuteCodeName;

    /// <inheritdoc />
    public override string Description => this._description;

    /// <inheritdoc />
    public override JsonElement JsonSchema => s_schema;

    /// <inheritdoc />
    protected override async ValueTask<object?> InvokeCoreAsync(
        AIFunctionArguments arguments,
        CancellationToken cancellationToken)
    {
        if (arguments is null || !arguments.TryGetValue("code", out var codeObj) || codeObj is null)
        {
            throw new ArgumentException("Missing required parameter 'code'.", nameof(arguments));
        }

        var code = codeObj switch
        {
            string s => s,
            JsonElement { ValueKind: JsonValueKind.String } el => el.GetString() ?? string.Empty,
            _ => codeObj.ToString() ?? string.Empty,
        };

        if (string.IsNullOrWhiteSpace(code))
        {
            throw new ArgumentException("Parameter 'code' must not be empty.", nameof(arguments));
        }

        return await this._executor.ExecuteAsync(this._snapshot, code, cancellationToken).ConfigureAwait(false);
    }
}
