// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading.Tasks;
using Microsoft.Agents.Workflows.Core;

namespace Microsoft.Agents.Workflows.Declarative.Execution;

internal sealed class DeclarativeActionExecutor(string actionId, Func<ValueTask> action) :
    Executor<DeclarativeActionExecutor>(actionId),
    IMessageHandler<string>
{
    public async ValueTask HandleAsync(string message, IWorkflowContext context)
    {
        await action.Invoke().ConfigureAwait(false);

        //await context.AddEventAsync(new ExecutorInvokeEvent(this.Id, $"{this.Id}: {DateTime.UtcNow.ToShortTimeString()}")).ConfigureAwait(false);
        await context.SendMessageAsync($"{this.Id}: {DateTime.UtcNow.ToShortTimeString()}").ConfigureAwait(false);
    }
}
