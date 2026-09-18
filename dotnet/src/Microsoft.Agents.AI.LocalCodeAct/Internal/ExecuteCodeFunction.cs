// Copyright (c) Microsoft. All rights reserved.

using System;
using System.ComponentModel;
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

    private readonly CodeExecutor _executor;
    private readonly CodeExecutor.RunSnapshot _snapshot;
    private readonly AIFunction _inner;

    public ExecuteCodeFunction(CodeExecutor executor, CodeExecutor.RunSnapshot snapshot, string description)
    {
        this._executor = executor;
        this._snapshot = snapshot;
        this._inner = AIFunctionFactory.Create(
            this.ExecuteCodeAsync,
            new AIFunctionFactoryOptions
            {
                Name = ExecuteCodeName,
                Description = description,
            });
    }

    public override string Name => this._inner.Name;

    public override string Description => this._inner.Description;

    public override JsonElement JsonSchema => this._inner.JsonSchema;

    protected override ValueTask<object?> InvokeCoreAsync(AIFunctionArguments arguments, CancellationToken cancellationToken) =>
        this._inner.InvokeAsync(arguments, cancellationToken);

    private async ValueTask<object?> ExecuteCodeAsync(
        [Description("Python source code to execute locally in the agent environment.")] string code,
        CancellationToken cancellationToken)
        => string.IsNullOrWhiteSpace(code)
            ? throw new ArgumentException("Parameter 'code' must not be empty.", nameof(code))
            : await this._executor.ExecuteAsync(this._snapshot, code, cancellationToken).ConfigureAwait(false);
}
