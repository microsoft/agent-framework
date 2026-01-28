// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading.Tasks;
using Microsoft.Agents.AI;

namespace AgentConformance.IntegrationTests.Support;

/// <summary>
/// Helper class to delete sessions after tests.
/// </summary>
/// <param name="session">The session to delete.</param>
/// <param name="fixture">The fixture that provides agent specific capabilities.</param>
internal sealed class SessionCleanup(AgentSession session, IAgentFixture fixture) : IAsyncDisposable
{
    public async ValueTask DisposeAsync() =>
        await fixture.DeleteSessionAsync(session);
}
