// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading.Tasks;
using Microsoft.Agents.Workflows.Declarative.PowerFx;
using Microsoft.Agents.Workflows.Reflection;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.Workflows.Declarative.Interpreter;

/// <summary>
/// The root executor for a declarative workflow.
/// </summary>
internal sealed class DeclarativeWorkflowExecutor<TInput>(string workflowId, DeclarativeWorkflowState state, Func<TInput, ChatMessage> inputTransform) :
    ReflectingExecutor<DeclarativeWorkflowExecutor<TInput>>(workflowId),
    IMessageHandler<TInput>
    where TInput : notnull
{
    public async ValueTask HandleAsync(TInput message, IWorkflowContext context)
    {
        ChatMessage input = inputTransform.Invoke(message);
        await state.SetLastMessageAsync(context, input).ConfigureAwait(false);

        await context.SendMessageAsync(new DeclarativeExecutorResult(this.Id)).ConfigureAwait(false);
    }
}
