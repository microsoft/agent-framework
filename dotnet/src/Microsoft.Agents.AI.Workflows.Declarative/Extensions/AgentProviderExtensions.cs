// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Workflows.Declarative.Extensions;

internal static class AgentProviderExtensions
{
    public static async ValueTask<AgentResponse> InvokeAgentAsync(
        this ResponseAgentProvider agentProvider,
        string executorId,
        IWorkflowContext context,
        string agentName,
        string? conversationId,
        bool autoSend,
        IEnumerable<ChatMessage>? inputMessages = null,
        IDictionary<string, object?>? inputArguments = null,
        CancellationToken cancellationToken = default)
    {
        IAsyncEnumerable<AgentResponseUpdate> agentUpdates = agentProvider.InvokeAgentAsync(agentName, null, conversationId, inputMessages, inputArguments, cancellationToken);

        // Determine whether the target conversation is the workflow conversation
        // (used below to decide whether to mirror messages into the workflow conversation
        // when an agent runs against a different conversation). The caller's autoSend
        // value is honored as-is — when the workflow.yaml specifies autoSend: false the
        // raw agent output must not be streamed to the caller, even when the agent is
        // running on the workflow conversation.
        bool isWorkflowConversation = context.IsWorkflowConversation(conversationId, out string? workflowConversationId);

        // Process the agent response updates.
        List<AgentResponseUpdate> updates = [];
        await foreach (AgentResponseUpdate update in agentUpdates.ConfigureAwait(false))
        {
            await AssignConversationIdAsync(((ChatResponseUpdate?)update.RawRepresentation)?.ConversationId).ConfigureAwait(false);

            updates.Add(update);

            if (autoSend)
            {
                await context.AddEventAsync(new AgentResponseUpdateEvent(executorId, update), cancellationToken).ConfigureAwait(false);
            }
        }

        AgentResponse response = updates.ToAgentResponse();

        if (autoSend)
        {
            await context.AddEventAsync(new AgentResponseEvent(executorId, response), cancellationToken).ConfigureAwait(false);
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
