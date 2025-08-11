// Copyright (c) Microsoft. All rights reserved.

using System.Threading;
using System.Threading.Tasks;
using Microsoft.Bot.ObjectModel;

namespace Microsoft.Agents.Workflows.Declarative.Handlers;

internal sealed class ConditionGroupAction : ProcessAction<ConditionGroup>
{
    public static class Steps
    {
        public static string End(string id) => $"{id}_{nameof(End)}";
    }

    public ConditionGroupAction(ConditionGroup model)
        : base(model)
    {
    }

    protected override Task HandleAsync(ProcessActionContext context, CancellationToken cancellationToken)
    {
        return Task.CompletedTask;
    }
}
