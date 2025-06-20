// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading.Tasks;
using AgentConformance.IntegrationTests.Support;
using Microsoft.Agents;

namespace AgentConformance.IntegrationTests;

/// <summary>
/// Conformance tests that are specific to the <see cref="ChatClientAgent"/> in addition to those in <see cref="RunTests{TAgentFixture}"/>.
/// </summary>
/// <typeparam name="TAgentFixture">The type of test fixture used by the concrete test implementation.</typeparam>
/// <param name="createAgentFixture">Function to create the test fixture with.</param>
public abstract class ChatClientAgentRunTests<TAgentFixture>(Func<TAgentFixture> createAgentFixture) : AgentTests<TAgentFixture>(createAgentFixture)
    where TAgentFixture : IChatClientAgentFixture
{
    [RetryFact(Constants.RetryCount, Constants.RetryDelay)]
    public virtual async Task RunWithInstructionsAndNoMessageReturnsExpectedResultAsync()
    {
        // Arrange
        var agent = await this.Fixture.CreateAgentWithInstructionsAsync("Always respond with 'Computer says no', even if there was no user input.");
        var thread = agent.GetNewThread();
        await using var agentCleanup = new AgentCleanup(agent, this.Fixture);
        await using var threadCleanup = new ThreadCleanup(thread, this.Fixture);

        // Act
        var chatResponse = await agent.RunAsync(thread);

        // Assert
        Assert.NotNull(chatResponse);
        Assert.Single(chatResponse.Messages);
        Assert.Contains("Computer says no", chatResponse.Text, StringComparison.OrdinalIgnoreCase);
    }
}
