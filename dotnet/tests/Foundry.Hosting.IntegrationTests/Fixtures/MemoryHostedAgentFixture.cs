// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;

namespace Foundry.Hosting.IntegrationTests.Fixtures;

/// <summary>
/// Provisions a hosted agent that runs the test container in <c>IT_SCENARIO=memory</c> mode.
/// Used by tests that exercise <see cref="Microsoft.Agents.AI.Foundry.FoundryMemoryProvider"/>
/// running inside the Foundry hosted agent. The memory store name is randomised per fixture
/// instance so concurrent test runs do not share state.
/// </summary>
public sealed class MemoryHostedAgentFixture : HostedAgentFixture
{
    protected override string ScenarioName => "memory";

    /// <summary>
    /// Memory store name passed to the test container via <c>IT_MEMORY_STORE_ID</c> so that each
    /// fixture instance gets a fresh, isolated bucket of memories.
    /// </summary>
    public string MemoryStoreId { get; } = $"it-memory-{Guid.NewGuid():N}";

    protected override void ConfigureEnvironment(IDictionary<string, string> environment)
    {
        environment["IT_MEMORY_STORE_ID"] = this.MemoryStoreId;
    }
}
