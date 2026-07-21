// Copyright (c) Microsoft. All rights reserved.

using System;
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

        // Foundry managed workflows treat responses produced on the workflow conversation
        // as workflow output even when autoSend is explicitly false. Preserve that direct-run
        // contract here. Workflow.AsAIAgent separately removes matching streamed/completed
        // message duplicates at its hosting boundary.
        bool isWorkflowConversation = context.IsWorkflowConversation(conversationId, out string? workflowConversationId);
        autoSend |= isWorkflowConversation;

        // Assign stable IDs to content-bearing chat updates before emitting and aggregating them.
        // Contentless updates may carry only metadata and must not become empty messages.
        List<AgentResponseUpdate> updates = [];
        string? generatedMessageId = null;
        string? generatedMessageResponseId = null;
        ChatRole? generatedMessageRole = null;
        await foreach (AgentResponseUpdate update in agentUpdates.ConfigureAwait(false))
        {
            await AssignConversationIdAsync(((ChatResponseUpdate?)update.RawRepresentation)?.ConversationId).ConfigureAwait(false);

            if (string.IsNullOrEmpty(update.MessageId) && update.RawRepresentation is ChatResponseUpdate rawUpdate)
            {
                if (update.Contents.Count > 0)
                {
                    if (generatedMessageId is null
                        || !string.Equals(generatedMessageResponseId, update.ResponseId, StringComparison.Ordinal)
                        || generatedMessageRole != update.Role)
                    {
                        generatedMessageId = Guid.NewGuid().ToString("N");
                        generatedMessageResponseId = update.ResponseId;
                        generatedMessageRole = update.Role;
                    }
                    update.MessageId = generatedMessageId;
                    rawUpdate.MessageId = generatedMessageId;
                }
            }
            else
            {
                generatedMessageId = null;
                generatedMessageResponseId = null;
                generatedMessageRole = null;
            }

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
