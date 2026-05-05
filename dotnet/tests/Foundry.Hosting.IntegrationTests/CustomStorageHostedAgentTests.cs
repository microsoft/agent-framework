// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading.Tasks;
using Foundry.Hosting.IntegrationTests.Fixtures;

namespace Foundry.Hosting.IntegrationTests;

/// <summary>
/// Tests for a hosted agent whose container wires an in memory custom storage provider
/// in place of the platform default. Verifies the model still works and that multi turn
/// behavior reads from the custom store.
/// </summary>
public sealed class CustomStorageHostedAgentTests(CustomStorageHostedAgentFixture fixture)
    : IClassFixture<CustomStorageHostedAgentFixture>
{
    private readonly CustomStorageHostedAgentFixture _fixture = fixture;

    [Fact(Skip = "Pending TestContainer build and end to end smoke (step 5).")]
    public async Task RoundTrip_WorksWithCustomStorageAsync()
    {
        // Arrange
        var agent = this._fixture.Agent;

        // Act
        var response = await agent.RunAsync("Reply with the word 'stored'.");

        // Assert
        Assert.False(string.IsNullOrWhiteSpace(response.Text));
    }

    [Fact(Skip = "Pending TestContainer build and end to end smoke (step 5).")]
    public async Task MultiTurn_PreviousResponseId_ReadsFromCustomStoreAsync()
    {
        // Arrange
        var agent = this._fixture.Agent;
        var session = await agent.CreateSessionAsync();

        // Act
        var first = await agent.RunAsync("My favorite city is Lisbon. Acknowledge briefly.", session);
        Assert.False(string.IsNullOrWhiteSpace(first.Text));

        var second = await agent.RunAsync("What city did I just tell you?", session);

        // Assert
        Assert.Contains("Lisbon", second.Text, StringComparison.OrdinalIgnoreCase);
    }
}
