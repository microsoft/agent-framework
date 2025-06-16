﻿// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading.Tasks;
using AgentConformanceTests;
using Microsoft.Agents;

namespace AgentConformance.IntegrationTests;

/// <summary>
/// Helper class to delete threads after tests.
/// </summary>
/// <param name="thread">The thread to delete.</param>
/// <param name="fixture">The fixture that provides agent specific capabilities.</param>
internal sealed class ThreadCleanup(AgentThread thread, AgentFixture fixture) : IAsyncDisposable
{
    public async ValueTask DisposeAsync()
    {
        if (thread != null)
        {
            await fixture.DeleteThreadAsync(thread);
        }
    }
}
