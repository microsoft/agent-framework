// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading.Tasks;
using Microsoft.Extensions.AI.Agents;

namespace AgentConformance.IntegrationTests.Support;

/// <summary>
/// Helper class to delete agents after tests.
/// </summary>
/// <param name="agent">The agent to delete.</param>
/// <param name="fixture">The fixture that provides agent specific capabilities.</param>
internal sealed class AgentCleanup(ChatClientAgent agent, IChatClientAgentFixture fixture) : IAsyncDisposable
{
    public async ValueTask DisposeAsync() =>
        await fixture.DeleteAgentAsync(agent);
}
