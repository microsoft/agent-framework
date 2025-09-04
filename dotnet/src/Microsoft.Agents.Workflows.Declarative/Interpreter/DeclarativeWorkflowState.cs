// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Collections.Immutable;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.Workflows.Declarative.Extensions;
using Microsoft.Agents.Workflows.Declarative.PowerFx;
using Microsoft.Bot.ObjectModel;
using Microsoft.PowerFx;
using Microsoft.PowerFx.Types;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.Workflows.Declarative.Interpreter;

internal sealed class DeclarativeWorkflowState
{
    private static readonly ImmutableHashSet<string> s_mutableScopes =
        new HashSet<string>
        {
            VariableScopeNames.Topic,
            VariableScopeNames.Global,
            VariableScopeNames.System,
        }.ToImmutableHashSet();

    private readonly RecalcEngine _engine;
    private readonly WorkflowScopes _scopes;
    private WorkflowExpressionEngine? _expressionEngine;
    private int _isInitialized;

    public DeclarativeWorkflowState(RecalcEngine engine, WorkflowScopes? scopes = null)
    {
        this._scopes = scopes ?? new WorkflowScopes();
        this._engine = engine;
        this._scopes.Bind(this._engine);
    }

    public WorkflowExpressionEngine ExpressionEngine => this._expressionEngine ??= new WorkflowExpressionEngine(this._engine);

    public void Reset(PropertyPath variablePath) =>
        this.Reset(Throw.IfNull(variablePath.VariableScopeName), Throw.IfNull(variablePath.VariableName));

    public void Reset(string scopeName, string? varName = null)
    {
        if (string.IsNullOrWhiteSpace(varName))
        {
            this._scopes.Clear(scopeName);
        }
        else
        {
            this._scopes.Reset(varName, scopeName);
        }

        this._scopes.Bind(this._engine, scopeName);
    }

    public FormulaValue Get(PropertyPath variablePath) =>
        this.Get(Throw.IfNull(variablePath.VariableScopeName), Throw.IfNull(variablePath.VariableName));

    public FormulaValue Get(string scope, string varName) =>
        this._scopes.Get(varName, scope);

    public ValueTask SetAsync(PropertyPath variablePath, FormulaValue value, IWorkflowContext context) =>
        this.SetAsync(Throw.IfNull(variablePath.VariableScopeName), Throw.IfNull(variablePath.VariableName), value, context);

    public async ValueTask SetAsync(string scopeName, string varName, FormulaValue value, IWorkflowContext context)
    {
        if (!s_mutableScopes.Contains(scopeName))
        {
            throw new DeclarativeModelException($"Invalid scope: {scopeName}");
        }

        this._scopes.Set(varName, value, scopeName);
        this._scopes.Bind(this._engine, scopeName);

        await context.QueueStateUpdateAsync(varName, value.ToObject(), scopeName).ConfigureAwait(false);
    }

    public string? Format(IEnumerable<TemplateLine> template) => this._engine.Format(template);

    public string? Format(TemplateLine? line) => this._engine.Format(line);

    public async ValueTask RestoreAsync(IWorkflowContext context, CancellationToken cancellationToken)
    {
        if (Interlocked.CompareExchange(ref this._isInitialized, 1, 0) == 1)
        {
            return;
        }

        await Task.WhenAll(s_mutableScopes.Select(scopeName => ReadScopeAsync(scopeName).AsTask())).ConfigureAwait(false);

        async ValueTask ReadScopeAsync(string scopeName)
        {
            HashSet<string> keys = await context.ReadStateKeysAsync(scopeName).ConfigureAwait(false);
            foreach (string key in keys)
            {
                object? value = await context.ReadStateAsync<object>(key, scopeName).ConfigureAwait(false);
                this._scopes.Set(key, value.ToFormulaValue(), scopeName);
            }
        }
    }
}
