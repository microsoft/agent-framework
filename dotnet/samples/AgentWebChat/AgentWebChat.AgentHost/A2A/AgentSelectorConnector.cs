// Copyright (c) Microsoft. All rights reserved.

using A2A;
using Microsoft.Extensions.AI.Agents.A2A;

namespace AgentWebChat.AgentHost.A2A;

public class AgentSelectorConnector : IA2AConnector
{
    public Task<AgentCard> GetAgentCardAsync(string agentPath, CancellationToken cancellationToken)
    {
        throw new NotImplementedException();
    }

    public Task<Message> ProcessMessageAsync(MessageSendParams messageSendParams, CancellationToken cancellationToken)
    {
        throw new NotImplementedException();
    }
}
