// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Linq;
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
        CancellationToken cancellationToken = default)
    {
        IAsyncEnumerable<AgentRunResponseUpdate> agentUpdates = agentProvider.InvokeAgentAsync(agentName, null, conversationId, inputMessages, cancellationToken);

        // Enable "autoSend" behavior if this is the workflow conversation.
        bool isWorkflowConversation = context.IsWorkflowConversation(conversationId, out string? workflowConversationId);
        autoSend |= isWorkflowConversation;

        // Process the agent response updates.
        List<AgentRunResponseUpdate> updates = [];
        await foreach (AgentRunResponseUpdate update in agentUpdates.ConfigureAwait(false))
        {
            await AssignConversationIdAsync(((ChatResponseUpdate?)update.RawRepresentation)?.ConversationId).ConfigureAwait(false);

            updates.Add(update);

            //if (update.RawRepresentation is ChatResponseUpdate chatUpdate && // %%% VALIDATE
            //    chatUpdate.RawRepresentation is RunUpdate runUpdate &&
            //    s_failureStatus.Contains(runUpdate.Value.Status))
            //{
            //    throw new DeclarativeActionException($"Unexpected failure invoking agent, run {runUpdate.Value.Status}: {agent.Name ?? agent.Id} [{runUpdate.Value.Id}/{conversationId}]");
            //}

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
                // %%% NOTE: Copy message by ID - Agent Provider
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
