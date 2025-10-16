// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Workflows.Specialized;

/// <summary>
/// Executor that runs the agent and forwards all messages, input and output, to the next executor.
/// </summary>
internal sealed class AgentRunStreamingExecutor(AIAgent agent, bool includeInputInOutput)
    : ChatProtocolExecutor(agent.GetDescriptiveId(), DefaultOptions, declareCrossRunShareable: true), IResettableExecutor
{
    private static ChatProtocolExecutorOptions DefaultOptions => new()
    {
        StringMessageChatRole = ChatRole.User
    };

    protected override async ValueTask TakeTurnAsync(List<ChatMessage> messages, IWorkflowContext context, bool? emitEvents, CancellationToken cancellationToken = default)
    {
        List<ChatMessage>? roleChanged = messages.ChangeAssistantToUserForOtherParticipants(agent.DisplayName);

        List<AgentRunResponseUpdate> updates = [];
        await foreach (var update in agent.RunStreamingAsync(messages, cancellationToken: cancellationToken).ConfigureAwait(false))
        {
            updates.Add(update);
            if (emitEvents is true)
            {
                await context.AddEventAsync(new AgentRunUpdateEvent(this.Id, update), cancellationToken).ConfigureAwait(false);
            }
        }

        roleChanged.ResetUserToAssistantForChangedRoles();

        List<ChatMessage> result = includeInputInOutput ? [.. messages] : [];
        result.AddRange(updates.ToAgentRunResponse().Messages);

        await context.SendMessageAsync(result, cancellationToken: cancellationToken).ConfigureAwait(false);
    }

    public new ValueTask ResetAsync() => base.ResetAsync();
}
