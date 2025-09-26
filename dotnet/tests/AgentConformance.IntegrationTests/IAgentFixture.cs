// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Threading.Tasks;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;

namespace AgentConformance.IntegrationTests;

/// <summary>
/// Interface for setting up and tearing down agents, to be used in tests.
/// Each agent type should have its own derived class.
/// </summary>
public interface IAgentFixture : IAsyncLifetime
{
    AIAgent Agent { get; }

    Task<List<ChatMessage>> GetChatHistoryAsync(AgentThread thread);

    Task DeleteThreadAsync(AgentThread thread);
}
