// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading.Tasks;
using Foundry.Hosting.IntegrationTests.Fixtures;

namespace Foundry.Hosting.IntegrationTests;

/// <summary>
/// Basic round trip, streaming, and container-instruction behaviour for a hosted Responses agent.
/// Store and session semantics live in <see cref="HostedResponsesStoreConfigTests"/>.
/// </summary>
[Trait("Category", "FoundryHostedAgents")]
public sealed class HappyPathHostedAgentTests(HappyPathHostedAgentFixture fixture) : IClassFixture<HappyPathHostedAgentFixture>
{
    private readonly HappyPathHostedAgentFixture _fixture = fixture;

    [Fact]
    public async Task RunAsync_ReturnsNonEmptyTextAsync()
    {
        // Arrange
        var agent = this._fixture.Agent;

        // Act
        var response = await agent.RunAsync("Reply with a short greeting.");

        // Assert
        Assert.False(string.IsNullOrWhiteSpace(response.Text));
    }

    [Fact]
    public async Task RunStreamingAsync_YieldsAtLeastOneUpdateAsync()
    {
        // Arrange
        var agent = this._fixture.Agent;

        // Act
        var collected = new System.Collections.Generic.List<string>();
        await foreach (var update in agent.RunStreamingAsync("Reply with a short greeting."))
        {
            if (!string.IsNullOrEmpty(update.Text))
            {
                collected.Add(update.Text);
            }
        }

        // Assert
        Assert.NotEmpty(collected);
        Assert.False(string.IsNullOrWhiteSpace(string.Concat(collected)));
    }

    [Fact]
    public async Task Instructions_FromContainerDefinition_AreObeyedAsync()
    {
        // Arrange: the container-side happy-path instructions require every reply to end with the
        // marker token CONTAINER-OK. See TestContainer/Program.cs.
        var agent = this._fixture.Agent;

        // Act
        var response = await agent.RunAsync("Say something useful.");

        // Assert
        Assert.False(string.IsNullOrWhiteSpace(response.Text));
        Assert.Contains("CONTAINER-OK", response.Text, StringComparison.OrdinalIgnoreCase);
    }
}
