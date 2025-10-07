// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Azure.AI.Agents.Persistent;
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
        string? additionalInstructions = null,
        IEnumerable<ChatMessage>? inputMessages = null,
        CancellationToken cancellationToken = default)
    {
        // Get the specified agent.
        AIAgent agent = await agentProvider.GetAgentAsync(agentName, cancellationToken).ConfigureAwait(false);

        // Prepare the run options.
        ChatClientAgentRunOptions options =
            new(
                new ChatOptions()
                {
                    ConversationId = conversationId,
                    Instructions = additionalInstructions,
                });

        // Initialize the agent thread.
        IAsyncEnumerable<AgentRunResponseUpdate> agentUpdates =
            inputMessages is not null ?
                agent.RunStreamingAsync([.. inputMessages], null, options, cancellationToken) :
                agent.RunStreamingAsync(null, options, cancellationToken);

        // Enable "autoSend" behavior if this is the workflow conversation.
        bool isWorkflowConversation = context.IsWorkflowConversation(conversationId, out string? workflowConversationId);
        autoSend |= isWorkflowConversation;

        // Process the agent response updates.
        List<AgentRunResponseUpdate> updates = [];
        await foreach (AgentRunResponseUpdate update in agentUpdates.ConfigureAwait(false))
        {
            await AssignConversationIdAsync(((ChatResponseUpdate?)update.RawRepresentation)?.ConversationId).ConfigureAwait(false);

            updates.Add(update);

            if (update.RawRepresentation is ChatResponseUpdate chatUpdate &&
                chatUpdate.RawRepresentation is RunUpdate runUpdate &&
                runUpdate.Value.Status == Azure.AI.Agents.Persistent.RunStatus.Failed) // %%% TODO - Cancelled/Cancelling/Expired && AF ISSUE
            {
                throw new DeclarativeActionException($"Unexpected failured invoking agent: {agent.Name ?? agent.Id} [{runUpdate.Value.Id}/{conversationId}]");
            }

            if (autoSend)
            {
                await context.AddEventAsync(new AgentRunUpdateEvent(executorId, update)).ConfigureAwait(false);
            }
        }

        // %%% FAILURE STATUS

        AgentRunResponse response = updates.ToAgentRunResponse();

        if (autoSend)
        {
            await context.AddEventAsync(new AgentRunResponseEvent(executorId, response)).ConfigureAwait(false);
        }

        if (autoSend && !isWorkflowConversation && workflowConversationId is not null)
        {
            // Copy messages with content that aren't function calls or results.
            IEnumerable<ChatMessage> messages =
                response.Messages.Where(
                    message =>
                        !string.IsNullOrEmpty(message.Text) &&
                        !message.Contents.OfType<FunctionCallContent>().Any() &&
                        !message.Contents.OfType<FunctionResultContent>().Any());
            foreach (ChatMessage message in messages)
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

                await context.QueueConversationUpdateAsync(conversationId).ConfigureAwait(false);
            }
        }
    }
}
