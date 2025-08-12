// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading.Tasks;
using Microsoft.Agents.Workflows.Core;
using Microsoft.Agents.Workflows.Declarative.PowerFx;
using Microsoft.PowerFx.Types;

namespace Microsoft.Agents.Workflows.Declarative.Execution;

/// <summary>
/// The root executor for a declarative workflow.
/// </summary>
/// <param name="scopes">// %%% COMMENT / DESIGN</param>
/// <param name="workflowId">The unique identifier for the workflow.</param>
internal sealed class DeclarativeWorkflowExecutor(WorkflowScopes scopes, string workflowId) :
    Executor<DeclarativeWorkflowExecutor>(workflowId),
    IMessageHandler<string>
{
    public async ValueTask HandleAsync(string message, IWorkflowContext context)
    {
        scopes.Set("LastMessage", WorkflowScopeType.System, FormulaValue.New(message)); // %%% MAGIC CONST "LastMessage" / SYSTEM scope

        //await context.AddEventAsync(new ExecutorInvokeEvent(this.Id, $"{this.Id}: {DateTime.UtcNow.ToShortTimeString()}")).ConfigureAwait(false);
        await context.SendMessageAsync($"{this.Id}: {DateTime.UtcNow.ToShortTimeString()}").ConfigureAwait(false);
    }
}
