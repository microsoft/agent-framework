// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading.Tasks;
using Microsoft.Agents.Workflows.Reflection;

namespace Microsoft.Agents.Workflows.Declarative.Execution;

internal sealed class WorkflowDelegateExecutor(string actionId, Func<ValueTask> action) :
    ReflectingExecutor<WorkflowDelegateExecutor>(actionId),
    IMessageHandler<string>
{
    public async ValueTask HandleAsync(string message, IWorkflowContext context)
    {
        await action.Invoke().ConfigureAwait(false);

        await context.SendMessageAsync($"{this.Id}: {DateTime.UtcNow.ToShortTimeString()}").ConfigureAwait(false);
    }
}
