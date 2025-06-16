// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading.Tasks;
using AgentConformanceTests;
using Microsoft.Extensions.AI;

namespace AgentConformance.IntegrationTests;

/// <summary>
/// Conformance tests for run methods on agents.
/// </summary>
/// <typeparam name="TAgentFixture">The type of test fixture used by the concrete test implementation.</typeparam>
/// <param name="createAgentFixture">Function to create the test fixture with.</param>
public abstract class RunAsyncTests<TAgentFixture>(Func<TAgentFixture> createAgentFixture) : AgentTests<TAgentFixture>(createAgentFixture)
    where TAgentFixture : AgentFixture
{
    [RetryFact(3, 5000)]
    public virtual async Task RunReturnsResultAsync()
    {
        // Arrange
        var agent = this.Fixture.Agent;
        var thread = agent.GetNewThread();

        // Act
        var chatResponse = await agent.RunAsync(new ChatMessage(ChatRole.User, "What is the capital of France."), thread);

        // Assert
        Assert.NotNull(chatResponse);
        Assert.Single(chatResponse.Messages);
        Assert.Contains("Paris", chatResponse.Text);
    }
}
