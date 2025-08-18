// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using Microsoft.Agents.Workflows.Declarative.Extensions;
using Microsoft.Agents.Workflows.Declarative.PowerFx;
using Microsoft.Bot.ObjectModel;
using Microsoft.PowerFx;
using Microsoft.PowerFx.Types;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.Workflows.Declarative.Interpreter;

internal sealed class DeclarativeWorkflowState
{
    private readonly RecalcEngine _engine;
    private readonly WorkflowScopes _scopes;
    private WorkflowExpressionEngine? _expressionEngine;

    public DeclarativeWorkflowState(RecalcEngine engine, WorkflowScopes? scopes = null)
    {
        this._scopes = scopes ?? new WorkflowScopes();
        this._engine = engine;
        this._scopes.Bind(this._engine);
    }

    // %%% TODO: IWorkflowContext

    public WorkflowScopes Scopes => this._scopes; // %%% NOT PUBLIC

    public WorkflowExpressionEngine ExpressionEngine => this._expressionEngine ??= new WorkflowExpressionEngine(this._engine);

    public void Clear(PropertyPath variablePath) =>
        this.Clear(WorkflowScopeType.Parse(variablePath.VariableScopeName), Throw.IfNull(variablePath.VariableName));

    public void Clear(WorkflowScopeType scope, string? varName = null)
    {
        if (string.IsNullOrWhiteSpace(varName))
        {
            this._scopes.Clear(scope);
        }
        else
        {
            this._scopes.Remove(varName, scope);
        }

        this._scopes.Bind(this._engine, scope);
    }

    public void Set(PropertyPath variablePath, FormulaValue value) =>
        this.Set(WorkflowScopeType.Parse(variablePath.VariableScopeName), Throw.IfNull(variablePath.VariableName), value);

    public void Set(WorkflowScopeType scope, string varName, FormulaValue value)
    {
        this._scopes.Set(varName, scope, value);

        this._scopes.Bind(this._engine, scope);
    }

    public string? Format(IEnumerable<TemplateLine> template) => this._engine.Format(template);

    public string? Format(TemplateLine? line) => this._engine.Format(line);
}
