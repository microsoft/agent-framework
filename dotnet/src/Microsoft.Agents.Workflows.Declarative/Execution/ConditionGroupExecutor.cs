// Copyright (c) Microsoft. All rights reserved.

using System.Threading;
using System.Threading.Tasks;
using Microsoft.Bot.ObjectModel;

namespace Microsoft.Agents.Workflows.Declarative.Execution;

internal sealed class ConditionGroupExecutor : WorkflowActionExecutor<ConditionGroup>
{
    public ConditionGroupExecutor(ConditionGroup model)
        : base(model)
    {
    }

    protected override ValueTask ExecuteAsync(IWorkflowContext context, CancellationToken cancellationToken)
    {
        return new ValueTask();
    }
}
