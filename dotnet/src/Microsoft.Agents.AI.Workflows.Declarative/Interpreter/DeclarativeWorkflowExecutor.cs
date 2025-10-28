// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading;
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
    DeclarativeWorkflowOptions options,
    WorkflowFormulaState state,
    Func<TInput, ChatMessage> inputTransform) :
    Executor<TInput>(workflowId), IResettableExecutor, IModeledAction where TInput : notnull
{
    /// <inheritdoc/>
    public ValueTask ResetAsync()
    {
        return default;
    }

    public override async ValueTask HandleAsync(TInput message, IWorkflowContext context, CancellationToken cancellationToken = default)
    {
        // No state to restore if we're starting from the beginning.
        state.SetInitialized();

        DeclarativeWorkflowContext declarativeContext = new(context, state);
        ChatMessage input = inputTransform.Invoke(message);

        string? conversationId = options.ConversationId;
        if (string.IsNullOrWhiteSpace(conversationId))
        {
            conversationId = await options.AgentProvider.CreateConversationAsync(cancellationToken).ConfigureAwait(false);
        }
        await declarativeContext.QueueConversationUpdateAsync(conversationId, isExternal: true, cancellationToken).ConfigureAwait(false);

        ChatMessage inputMessage = await options.AgentProvider.CreateMessageAsync(conversationId, input, cancellationToken).ConfigureAwait(false);
        await declarativeContext.SetLastMessageAsync(inputMessage).ConfigureAwait(false);

        await context.SendResultMessageAsync(this.Id, cancellationToken).ConfigureAwait(false);
    }
}
