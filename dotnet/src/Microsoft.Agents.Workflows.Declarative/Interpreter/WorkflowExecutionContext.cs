// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.Workflows.Declarative.PowerFx;
using Microsoft.PowerFx;

namespace Microsoft.Agents.Workflows.Declarative.ObjectModel;

internal sealed record class WorkflowExecutionContext(RecalcEngine Engine, WorkflowScopes Scopes) // %%% COLLAPSE (Executor?) and/or RENAME (Engine/State/PowerFx)
{
    private WorkflowExpressionEngine? _expressionEngine;

    public WorkflowExpressionEngine ExpressionEngine => this._expressionEngine ??= new WorkflowExpressionEngine(this.Engine);

    public object? Result { get; set; }
}
