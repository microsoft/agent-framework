// Copyright (c) Microsoft. All rights reserved.

using System;
using Azure.AI.Agents.Persistent;
using Microsoft.Agents.Workflows.Declarative.PowerFx;
using Microsoft.Extensions.Logging;
using Microsoft.PowerFx;

namespace Microsoft.Agents.Workflows.Declarative.Execution;

internal sealed record class WorkflowExecutionContext(RecalcEngine Engine, WorkflowScopes Scopes, Func<PersistentAgentsClient> ClientFactory, ILogger Logger)
{
    private WorkflowExpressionEngine? _expressionEngine;

    public WorkflowExpressionEngine ExpressionEngine => this._expressionEngine ??= new WorkflowExpressionEngine(this.Engine);
}
