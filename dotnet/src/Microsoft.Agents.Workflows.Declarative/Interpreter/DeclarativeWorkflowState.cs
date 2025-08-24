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

    public void Set(PropertyPath variablePath, FormulaValue value) =>
        this.Set(Throw.IfNull(variablePath.VariableScopeName), Throw.IfNull(variablePath.VariableName), value);

    public void Set(string scopeName, string varName, FormulaValue value)
    {
        this._scopes.Set(varName, scopeName, value);

        this._scopes.Bind(this._engine, scopeName);
    }

    public string? Format(IEnumerable<TemplateLine> template) => this._engine.Format(template);

    public string? Format(TemplateLine? line) => this._engine.Format(line);
}
