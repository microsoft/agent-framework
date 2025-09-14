// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading.Tasks;

namespace AgentConformance.IntegrationTests;

/// <summary>
/// Base class for all test classes used for testing agents.
/// </summary>
/// <typeparam name="TAgentFixture">The type of the agent fixture used in these tests.</typeparam>
/// <param name="createAgentFixture">Used to create a new fixture for this test suite.</param>
public abstract class AgentTests<TAgentFixture>(Func<TAgentFixture> createAgentFixture) : IAsyncLifetime
    where TAgentFixture : IAgentFixture
{
#pragma warning disable CS8618 // Non-nullable field must contain a non-null value when exiting constructor. Consider adding the 'required' modifier or declaring as nullable.
    protected TAgentFixture Fixture { get; private set; }
#pragma warning restore CS8618 // Non-nullable field must contain a non-null value when exiting constructor. Consider adding the 'required' modifier or declaring as nullable.

    public Task InitializeAsync()
    {
        this.Fixture = createAgentFixture();
        return this.Fixture.InitializeAsync();
    }

    public Task DisposeAsync() => this.Fixture.DisposeAsync();
}
