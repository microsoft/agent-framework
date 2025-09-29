// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Runtime.CompilerServices;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Workflows.Declarative.Extensions;

internal static class AgentProviderExtensions
{
    public static async IAsyncEnumerable<AgentRunResponseUpdate> InvokeAgentAsync(
        this WorkflowAgentProvider agentProvider,
        string executorId,
        IWorkflowContext context,
        string agentName,
        string? conversationId,
        bool autoSend,
        string? additionalInstructions = null,
        IEnumerable<ChatMessage>? inputMessages = null,
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        AIAgent agent = await agentProvider.GetAgentAsync(agentName, cancellationToken).ConfigureAwait(false);

        ChatClientAgentRunOptions options =
            new(
                new ChatOptions()
                {
                    Instructions = additionalInstructions,
                });

        AgentThread agentThread = conversationId is not null && agent is ChatClientAgent chatClientAgent ? chatClientAgent.GetNewThread(conversationId) : agent.GetNewThread();
        IAsyncEnumerable<AgentRunResponseUpdate> agentUpdates =
            inputMessages is not null ?
                agent.RunStreamingAsync([.. inputMessages], agentThread, options, cancellationToken) :
                agent.RunStreamingAsync(agentThread, options, cancellationToken);

        await foreach (AgentRunResponseUpdate update in agentUpdates.ConfigureAwait(false))
        {
            await AssignConversationIdAsync(((ChatResponseUpdate?)update.RawRepresentation)?.ConversationId).ConfigureAwait(false);

            if (autoSend)
            {
                await context.AddEventAsync(new AgentRunUpdateEvent(executorId, update)).ConfigureAwait(false);
            }

            yield return update;
        }

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
