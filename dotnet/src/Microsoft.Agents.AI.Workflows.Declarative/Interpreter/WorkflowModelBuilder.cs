// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Diagnostics;

namespace Microsoft.Agents.AI.Workflows.Declarative.Interpreter;

internal sealed class WorkflowModelBuilder : IModelBuilder<Func<object?, bool>>
{
    public WorkflowModelBuilder(Executor rootAction)
    {
        this.WorkflowBuilder = new WorkflowBuilder(rootAction);
    }

    public WorkflowBuilder WorkflowBuilder { get; }

    public void Connect(IModeledAction source, IModeledAction target, Func<object?, bool>? condition)
    {
        Debug.WriteLine($"> CONNECT: {source.Id} => {target.Id}{(condition is null ? string.Empty : " (?)")}");

        this.WorkflowBuilder.AddEdge(
            GetExecutorIsh(source),
            GetExecutorIsh(target),
            condition);
    }

    private static ExecutorIsh GetExecutorIsh(IModeledAction action) =>
        action switch
        {
            RequestPortAction port => port.RequestPort,
            Executor executor => executor,
            _ => throw new DeclarativeModelException($"Unsupported modeled action: {action.GetType().Name}.")
        };
}
