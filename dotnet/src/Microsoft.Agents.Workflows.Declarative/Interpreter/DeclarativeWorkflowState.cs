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

namespace Microsoft.Agents.Workflows.Declarative.Kit;

internal sealed class DeclarativeWorkflowState
{
    private static readonly ImmutableHashSet<string> s_mutableScopes =
        new HashSet<string>
        {
            VariableScopeNames.Topic,
            VariableScopeNames.Global,
            VariableScopeNames.System,
        }.ToImmutableHashSet();

    private readonly RecalcEngine _engine; // %%% MOVE TO SCOPES
    private WorkflowExpressionEngine? _expressionEngine;  // %%% MOVE TO SCOPES
    private int _isInitialized;

    public DeclarativeWorkflowState(RecalcEngine engine, WorkflowScopes? scopes = null)
    {
        this.Scopes = scopes ?? new WorkflowScopes();
        this._engine = engine;

        this.Bind();
    }

    public WorkflowScopes Scopes { get; }

    public WorkflowExpressionEngine ExpressionEngine => this._expressionEngine ??= new WorkflowExpressionEngine(this._engine);

    public void Bind() => this.Scopes.Bind(this._engine);  // %%% MOVE TO SCOPES

    //public void Reset(PropertyPath variablePath) =>
    //    this.Reset(Throw.IfNull(variablePath.VariableScopeName), Throw.IfNull(variablePath.VariableName));

    //public void Reset(string scopeName, string? varName = null)
    //{
    //    if (string.IsNullOrWhiteSpace(varName))
    //    {
    //        this.Scopes.Clear(scopeName);
    //    }
    //    else
    //    {
    //        this.Scopes.Reset(varName, scopeName);
    //    }

    //    this.Scopes.Bind(this._engine, scopeName);
    //}

    //public FormulaValue Get(PropertyPath variablePath) =>
    //    this.Get(Throw.IfNull(variablePath.VariableScopeName), Throw.IfNull(variablePath.VariableName));

    //public FormulaValue Get(string scope, string varName) =>
    //    this.Scopes.Get(varName, scope);

    //public void Set(PropertyPath variablePath, FormulaValue value) =>
    //    this.Set(Throw.IfNull(variablePath.VariableScopeName), Throw.IfNull(variablePath.VariableName), value);

    //public void Set(string scopeName, string varName, FormulaValue value)
    //{
    //    if (!s_mutableScopes.Contains(scopeName))
    //    {
    //        throw new DeclarativeModelException($"Invalid scope: {scopeName}");
    //    }

    //    this.Scopes.Set(varName, value, scopeName);
    //    this.Scopes.Bind(this._engine, scopeName);
    //}

    public string? Format(IEnumerable<TemplateLine> template) => this._engine.Format(template); // %%% REMOVE

    public string? Format(TemplateLine? line) => this._engine.Format(line); // %%% REMOVE

    public async ValueTask RestoreAsync(IWorkflowContext context, CancellationToken cancellationToken) // %%% MOVE TO SCOPES
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
                if (value is null || value is UnassignedValue)
                {
                    value = FormulaValue.NewBlank();
                }
                this.Scopes.Set(key, value.ToFormulaValue(), scopeName);
            }

            this.Scopes.Bind(this._engine, scopeName);
        }
    }
}
