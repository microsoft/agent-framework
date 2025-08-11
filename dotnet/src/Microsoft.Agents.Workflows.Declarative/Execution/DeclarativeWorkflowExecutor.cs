// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading.Tasks;
using Microsoft.Agents.Workflows.Core;
using Microsoft.Agents.Workflows.Declarative.PowerFx;
using Microsoft.PowerFx.Types;

namespace Microsoft.Agents.Workflows.Declarative.Execution;

internal sealed class DeclarativeWorkflowExecutor(WorkflowScopes scopes, string workflowId) :
    Executor<DeclarativeWorkflowExecutor>(workflowId),
    IMessageHandler<string>
{
    public async ValueTask HandleAsync(string message, IWorkflowContext context)
    {
        Console.WriteLine("!!! INIT WORKFLOW"); // %%% REMOVE
        scopes.Set("LastMessage", WorkflowScopeType.System, FormulaValue.New(message)); // %%% MAGIC CONST "LastMessage"

        //await context.AddEventAsync(new ExecutorInvokeEvent(this.Id, $"{this.Id}: {DateTime.UtcNow.ToShortTimeString()}")).ConfigureAwait(false);
        await context.SendMessageAsync($"{this.Id}: {DateTime.UtcNow.ToShortTimeString()}").ConfigureAwait(false);
    }
}
