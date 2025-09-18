// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading.Tasks;
using Microsoft.Agents.Workflows.Declarative.PowerFx;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.Workflows.Declarative.Interpreter;

/// <summary>
/// The root executor for a declarative workflow.
/// </summary>
internal sealed class DeclarativeWorkflowExecutor<TInput>(
    string workflowId,
    WorkflowFormulaState state,
    Func<TInput, ChatMessage> inputTransform) :
    Executor<TInput>(workflowId)
    where TInput : notnull
{
    public override async ValueTask HandleAsync(TInput message, IWorkflowContext context)
    {
        // No state to restore if we're starting from the beginning.
        state.SetInitialized();

        ChatMessage input = inputTransform.Invoke(message);
        state.SetLastMessage(input);

        await context.SendMessageAsync(new ExecutorResultMessage(this.Id)).ConfigureAwait(false);
    }
}
