// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading.Tasks;
using Microsoft.Extensions.AI.Agents;

namespace AgentConformance.IntegrationTests.Support;

/// <summary>
/// Helper class to delete threads after tests.
/// </summary>
/// <param name="thread">The thread to delete.</param>
/// <param name="fixture">The fixture that provides agent specific capabilities.</param>
internal sealed class ThreadCleanup(AgentThread thread, IAgentFixture fixture) : IAsyncDisposable
{
    public async ValueTask DisposeAsync() =>
        await fixture.DeleteThreadAsync(thread);
}
