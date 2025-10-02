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
        bool isWorkflowConversation = context.IsWorkflowConversation(conversationId);
        autoSend |= isWorkflowConversation;

        // Process the agent response updates.
        List<AgentRunResponseUpdate> updates = [];
        await foreach (AgentRunResponseUpdate update in agentUpdates.ConfigureAwait(false))
        {
            await AssignConversationIdAsync(((ChatResponseUpdate?)update.RawRepresentation)?.ConversationId).ConfigureAwait(false);

            updates.Add(update);

            if (autoSend)
            {
                await context.AddEventAsync(new AgentRunUpdateEvent(executorId, update)).ConfigureAwait(false);
            }
        }

        AgentRunResponse response = updates.ToAgentRunResponse();

        if (autoSend)
        {
            await context.AddEventAsync(new AgentRunResponseEvent(executorId, response)).ConfigureAwait(false);
        }

        if (autoSend && !isWorkflowConversation && conversationId is not null)
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
                await agentProvider.CreateMessageAsync(conversationId, message, cancellationToken).ConfigureAwait(false);
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
