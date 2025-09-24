// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Runtime.CompilerServices;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.Workflows.Declarative.Extensions;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.AI.Agents;

namespace Microsoft.Agents.Workflows.Declarative.Kit;

/// <summary>
/// Base class for agent invokcation.
/// </summary>
/// <param name="id">The executor id</param>
/// <param name="session">Session to support formula expressions.</param>
/// <param name="agentProvider">Provider for accessing and manipulating agents and conversations.</param>
public abstract class AgentExecutor(string id, FormulaSession session, WorkflowAgentProvider agentProvider) : ActionExecutor(id, session)
{
    /// <summary>
    /// Invokes an agent using the provided <see cref="WorkflowAgentProvider"/>.
    /// </summary>
    /// <param name="context">The workflow execution context providing messaging and state services.</param>
    /// <param name="agentName">The name or identifier of the agent.</param>
    /// <param name="conversationId">The identifier of the conversation.</param>
    /// <param name="autoSend">Send the agent's response as workflow output. (default: true).</param>
    /// <param name="additionalInstructions">Optional additional instructions to the agent.</param>
    /// <param name="inputMessages">Optional messages to add to the conversation prior to invocation.</param>
    /// <param name="cancellationToken">A token that can be used to observe cancellation.</param>
    /// <returns></returns>
    protected async IAsyncEnumerable<AgentRunResponseUpdate> InvokeAgentAsync(  // %%% REFACTOR
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
                await context.AddEventAsync(new AgentRunUpdateEvent(this.Id, update)).ConfigureAwait(false);
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
