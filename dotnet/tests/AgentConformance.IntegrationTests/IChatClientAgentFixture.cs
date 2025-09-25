// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Threading.Tasks;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;

namespace AgentConformance.IntegrationTests;

/// <summary>
/// Interface for setting up and tearing down <see cref="IChatClient"/> based agents, to be used in tests.
/// Each agent type should have its own derived class.
/// </summary>
public interface IChatClientAgentFixture : IAgentFixture
{
    IChatClient ChatClient { get; }

    Task<ChatClientAgent> CreateChatClientAgentAsync(
        string name = "HelpfulAssistant",
        string instructions = "You are a helpful assistant.",
        IList<AITool>? aiTools = null);

    Task DeleteAgentAsync(ChatClientAgent agent);
}
