﻿// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.Declarative.Extensions;
using Microsoft.Agents.AI.Workflows.Declarative.PowerFx;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Workflows.Declarative.Interpreter;

/// <summary>
/// The root executor for a declarative workflow.
/// </summary>
internal sealed class DeclarativeWorkflowExecutor<TInput>(
    string workflowId,
    WorkflowAgentProvider agentProvider,
    WorkflowFormulaState state,
    Func<TInput, ChatMessage> inputTransform) :
    Executor<TInput>(workflowId)
    where TInput : notnull
{
    public override async ValueTask HandleAsync(TInput message, IWorkflowContext context)
    {
        // No state to restore if we're starting from the beginning.
        state.SetInitialized();

        DeclarativeWorkflowContext declarativeContext = new(context, state);
        ChatMessage input = inputTransform.Invoke(message);

        string conversationId = await agentProvider.CreateConversationAsync(cancellationToken: default).ConfigureAwait(false);
        await declarativeContext.QueueConversationUpdateAsync(conversationId).ConfigureAwait(false);

        await agentProvider.CreateMessageAsync(conversationId, input, cancellationToken: default).ConfigureAwait(false);
        await declarativeContext.SetLastMessageAsync(input).ConfigureAwait(false);

        await context.SendResultMessageAsync(this.Id).ConfigureAwait(false);
    }
}
