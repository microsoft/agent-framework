// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Threading.Tasks;
using Microsoft.Agents;
using Microsoft.Extensions.AI;

namespace AgentConformanceTests;

/// <summary>
/// Base class for setting up and tearing down agents, to be used in tests.
/// Each agent type should have its own derived class.
/// </summary>
public abstract class AgentFixture : IAsyncLifetime
{
    public abstract Agent Agent { get; }

    public abstract Task<List<ChatMessage>> GetChatHistoryAsync(AgentThread thread);

    public abstract Task DeleteThreadAsync(AgentThread thread);

    public abstract Task DisposeAsync();

    public abstract Task InitializeAsync();
}
