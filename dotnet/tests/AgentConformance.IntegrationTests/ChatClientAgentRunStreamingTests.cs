// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Linq;
using System.Threading.Tasks;
using AgentConformance.IntegrationTests.Support;
using Microsoft.Agents;

namespace AgentConformance.IntegrationTests;

/// <summary>
/// Conformance tests that are specific to the <see cref="ChatClientAgent"/> in addition to those in <see cref="RunStreamingTests{TAgentFixture}"/>.
/// </summary>
/// <typeparam name="TAgentFixture">The type of test fixture used by the concrete test implementation.</typeparam>
/// <param name="createAgentFixture">Function to create the test fixture with.</param>
public abstract class ChatClientAgentRunStreamingTests<TAgentFixture>(Func<TAgentFixture> createAgentFixture) : AgentTests<TAgentFixture>(createAgentFixture)
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
        var chatResponses = await agent.RunStreamingAsync(thread).ToListAsync();

        // Assert
        var chatResponseText = string.Join("", chatResponses.Select(x => x.Text));
        Assert.Contains("Computer says no", chatResponseText, StringComparison.OrdinalIgnoreCase);
    }
}
