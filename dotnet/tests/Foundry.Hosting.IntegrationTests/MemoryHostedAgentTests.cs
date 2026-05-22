// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading.Tasks;
using Foundry.Hosting.IntegrationTests.Fixtures;
using Microsoft.Agents.AI;

#pragma warning disable OPENAI001 // Experimental Responses API surfaces

namespace Foundry.Hosting.IntegrationTests;

/// <summary>
/// Validates the Hosted-MemoryAgent end-to-end against a deployed test container running the
/// <c>IT_SCENARIO=memory</c> scenario. Asserts that <see cref="Microsoft.Agents.AI.Foundry.FoundryMemoryProvider"/>
/// scoped via <see cref="Microsoft.Agents.AI.Foundry.Hosting.HostedSessionContext"/> recalls user
/// preferences across multiple turns of a conversation.
/// </summary>
[Trait("Category", "FoundryHostedAgents")]
public sealed class MemoryHostedAgentTests(MemoryHostedAgentFixture fixture) : IClassFixture<MemoryHostedAgentFixture>
{
    private readonly MemoryHostedAgentFixture _fixture = fixture;

    [Fact]
    public async Task Memory_RecallsAcrossTurnsAsync()
    {
        // Arrange
        var agent = this._fixture.Agent;
        var session = await agent.CreateSessionAsync();

        // Act: teach the agent two pieces of information about the user.
        var first = await agent.RunAsync("My name is Taylor and I am planning a hiking trip to Patagonia in November.", session);
        Assert.False(string.IsNullOrWhiteSpace(first.Text));

        var second = await agent.RunAsync("I am travelling with my sister and we love finding scenic viewpoints.", session);
        Assert.False(string.IsNullOrWhiteSpace(second.Text));

        // FoundryMemoryProvider defaults to UpdateDelay=0 (immediate trigger). Server-side ingestion
        // typically completes within ~3 seconds; allow a small margin.
        await Task.Delay(TimeSpan.FromSeconds(5));

        var recall = await agent.RunAsync("What do you already know about my upcoming trip?", session);

        // Assert
        Assert.Contains("Patagonia", recall.Text, StringComparison.OrdinalIgnoreCase);
    }

    [Fact(Skip = "Foundry Memory write propagation is eventually consistent and the in-container WhenUpdatesCompletedAsync flush hook is not callable from the test process; this scenario is exercised manually via the sample's smoke.ps1.")]
    public async Task Memory_PersistsAcrossSessionsForSameUserAsync()
    {
        // Arrange: drive a session that establishes some user-private memory. Foundry Memory
        // extracts memories more reliably from multi-turn conversations than from a single
        // imperative utterance, so mirror the sample's two-turn teaching pattern.
        var agent = this._fixture.Agent;
        var teachingSession = await agent.CreateSessionAsync();
        await agent.RunAsync("My preferred airline is Iberia and I always fly business class.", teachingSession);
        await agent.RunAsync("I also prefer aisle seats whenever they are available.", teachingSession);

        // FoundryMemoryProvider defaults to UpdateDelay=0 (immediate trigger). Server-side
        // ingestion typically completes within ~3 seconds; poll a fresh-session recall a few
        // times before failing so the test does not flake on cold caches.
        AgentResponse recall = null!;
        const int MaxAttempts = 6;
        for (var attempt = 1; attempt <= MaxAttempts; attempt++)
        {
            await Task.Delay(TimeSpan.FromSeconds(5));

            var freshSession = await agent.CreateSessionAsync();
            recall = await agent.RunAsync("Which airline do I prefer? Reply with just the airline name.", freshSession);

            if (recall.Text.Contains("Iberia", StringComparison.OrdinalIgnoreCase))
            {
                break;
            }
        }

        // Assert
        Assert.Contains("Iberia", recall.Text, StringComparison.OrdinalIgnoreCase);
    }
}
