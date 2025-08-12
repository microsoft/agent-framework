// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading.Tasks;
using Microsoft.Agents.Workflows.Core;

namespace Microsoft.Agents.Workflows.Declarative.Execution;

internal sealed class WorkflowDelegateExecutor(string actionId, Func<ValueTask> action) :
    Executor<WorkflowDelegateExecutor>(actionId),
    IMessageHandler<string>
{
    public async ValueTask HandleAsync(string message, IWorkflowContext context)
    {
        await action.Invoke().ConfigureAwait(false);

        await context.SendMessageAsync($"{this.Id}: {DateTime.UtcNow.ToShortTimeString()}").ConfigureAwait(false);
    }
}
