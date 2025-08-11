// Copyright (c) Microsoft. All rights reserved.

using System.Threading;
using System.Threading.Tasks;
using Microsoft.Bot.ObjectModel;

namespace Microsoft.Agents.Workflows.Declarative.Execution;

internal sealed class ConditionGroupExecutor : WorkflowActionExecutor<ConditionGroup>
{
    public static class Steps
    {
        public static string End(string id) => $"{id}_{nameof(End)}";
    }

    public ConditionGroupExecutor(ConditionGroup model)
        : base(model)
    {
    }

    protected override ValueTask ExecuteAsync(CancellationToken cancellationToken)
    {
        return new ValueTask();
    }
}
