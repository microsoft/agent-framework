// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.LocalCodeAct.Internal;

/// <summary>
/// Run-scoped <see cref="AIFunction"/> that exposes <c>execute_code</c> to the model.
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
              "description": "Python source code to execute locally in the agent environment."
            }
          },
          "required": ["code"]
        }
        """).RootElement;

    private readonly CodeExecutor _executor;
    private readonly CodeExecutor.RunSnapshot _snapshot;
    private readonly string _description;

    public ExecuteCodeFunction(CodeExecutor executor, CodeExecutor.RunSnapshot snapshot, string description)
    {
        this._executor = executor;
        this._snapshot = snapshot;
        this._description = description;
    }

    public override string Name => ExecuteCodeName;

    public override string Description => this._description;

    public override JsonElement JsonSchema => s_schema;

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
