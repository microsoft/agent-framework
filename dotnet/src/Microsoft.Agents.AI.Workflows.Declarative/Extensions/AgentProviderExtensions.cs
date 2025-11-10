// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Workflows.Declarative.Extensions;

internal static class AgentProviderExtensions
{
    public static async ValueTask<AgentRunResponse> InvokeAgentAsync(
        this WorkflowAgentProvider agentProvider,
        string executorId,
        IWorkflowContext context,
        string agentName,
        string? conversationId,
        bool autoSend,
        IEnumerable<ChatMessage>? inputMessages = null,
        IDictionary<string, object?>? inputArguments = null,
        CancellationToken cancellationToken = default)
    {
        IAsyncEnumerable<AgentRunResponseUpdate> agentUpdates = agentProvider.InvokeAgentAsync(agentName, null, conversationId, inputMessages, inputArguments, cancellationToken);

        // Enable "autoSend" behavior if this is the workflow conversation.
        bool isWorkflowConversation = context.IsWorkflowConversation(conversationId, out string? workflowConversationId);
        autoSend |= isWorkflowConversation;

        // Process the agent response updates.
        List<AgentRunResponseUpdate> updates = [];
        await foreach (AgentRunResponseUpdate update in agentUpdates.ConfigureAwait(false))
        {
            await AssignConversationIdAsync(((ChatResponseUpdate?)update.RawRepresentation)?.ConversationId).ConfigureAwait(false);

            updates.Add(update);

            if (autoSend)
            {
                await context.AddEventAsync(new AgentRunUpdateEvent(executorId, update), cancellationToken).ConfigureAwait(false);
            }
        }

        AgentRunResponse response = updates.ToAgentRunResponse();

        if (autoSend)
        {
            await context.AddEventAsync(new AgentRunResponseEvent(executorId, response), cancellationToken).ConfigureAwait(false);
        }

        // If autoSend is enabled and this is not the workflow conversation, copy messages to the workflow conversation.
        if (autoSend && !isWorkflowConversation && workflowConversationId is not null)
        {
            foreach (ChatMessage message in response.Messages)
            {
                await agentProvider.CreateMessageAsync(workflowConversationId, message, cancellationToken).ConfigureAwait(false);
            }
        }

        return response;

        async ValueTask AssignConversationIdAsync(string? assignValue)
        {
            if (assignValue is not null && conversationId is null)
            {
                conversationId = assignValue;

                await context.QueueConversationUpdateAsync(conversationId, cancellationToken).ConfigureAwait(false);
            }
        }
    }
}
