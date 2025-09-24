// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Runtime.CompilerServices;
using System.Threading;
using System.Threading.Tasks;
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
    /// %%% COMMENT
    /// </summary>
    /// <returns></returns>
    protected async IAsyncEnumerable<AgentRunResponseUpdate> InvokeAgentAsync(
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
            //await AssignConversationIdAsync(((ChatResponseUpdate?)update.RawRepresentation)?.ConversationId).ConfigureAwait(false); // %%% REFACTOR

            if (autoSend)
            {
                await context.AddEventAsync(new AgentRunUpdateEvent(this.Id, update)).ConfigureAwait(false);
            }

            yield return update;
        }
    }
}
