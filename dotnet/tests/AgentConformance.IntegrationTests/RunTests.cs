// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Linq;
using System.Threading.Tasks;
using AgentConformance.IntegrationTests.Support;
using Microsoft.Extensions.AI;

namespace AgentConformance.IntegrationTests;

/// <summary>
/// Conformance tests for run methods on agents.
/// </summary>
/// <typeparam name="TAgentFixture">The type of test fixture used by the concrete test implementation.</typeparam>
/// <param name="createAgentFixture">Function to create the test fixture with.</param>
public abstract class RunTests<TAgentFixture>(Func<TAgentFixture> createAgentFixture) : AgentTests<TAgentFixture>(createAgentFixture)
    where TAgentFixture : IAgentFixture
{
    [RetryFact(Constants.RetryCount, Constants.RetryDelay)]
    public virtual async Task RunWithNoMessageDoesNotFailAsync()
    {
        // Arrange
        var agent = this.Fixture.Agent;
        var thread = agent.GetNewThread();
        await using var cleanup = new ThreadCleanup(thread, this.Fixture);

        // Act
        var chatResponse = await agent.RunAsync(thread);

        // Assert
        Assert.NotNull(chatResponse);
    }

    [RetryFact(Constants.RetryCount, Constants.RetryDelay)]
    public virtual async Task RunWithStringReturnsExpectedResultAsync()
    {
        // Arrange
        var agent = this.Fixture.Agent;
        var thread = agent.GetNewThread();
        await using var cleanup = new ThreadCleanup(thread, this.Fixture);

        // Act
        var response = await agent.RunAsync("What is the capital of France.", thread);

        // Assert
        Assert.NotNull(response);
        Assert.Single(response.Messages);
        Assert.Contains("Paris", response.Text);
        Assert.Equal(agent.Id, response.AgentId);
    }

    [RetryFact(Constants.RetryCount, Constants.RetryDelay)]
    public virtual async Task RunWithChatMessageReturnsExpectedResultAsync()
    {
        // Arrange
        var agent = this.Fixture.Agent;
        var thread = agent.GetNewThread();
        await using var cleanup = new ThreadCleanup(thread, this.Fixture);

        // Act
        var response = await agent.RunAsync(new ChatMessage(ChatRole.User, "What is the capital of France."), thread);

        // Assert
        Assert.NotNull(response);
        Assert.Single(response.Messages);
        Assert.Contains("Paris", response.Text);
    }

    [RetryFact(Constants.RetryCount, Constants.RetryDelay)]
    public virtual async Task RunWithChatMessagesReturnsExpectedResultAsync()
    {
        // Arrange
        var agent = this.Fixture.Agent;
        var thread = agent.GetNewThread();
        await using var cleanup = new ThreadCleanup(thread, this.Fixture);

        // Act
        var response = await agent.RunAsync(
            [
                new ChatMessage(ChatRole.User, "Hello."),
                new ChatMessage(ChatRole.User, "What is the capital of France.")
            ],
            thread);

        // Assert
        Assert.NotNull(response);
        Assert.Single(response.Messages);
        Assert.Contains("Paris", response.Text);
    }

    [RetryFact(Constants.RetryCount, Constants.RetryDelay)]
    public virtual async Task ThreadMaintainsHistoryAsync()
    {
        // Arrange
        const string Q1 = "What is the capital of France.";
        const string Q2 = "And Austria?";
        var agent = this.Fixture.Agent;
        var thread = agent.GetNewThread();
        await using var cleanup = new ThreadCleanup(thread, this.Fixture);

        // Act
        var result1 = await agent.RunAsync(Q1, thread);
        var result2 = await agent.RunAsync(Q2, thread);

        // Assert
        Assert.Contains("Paris", result1.Text);
        Assert.Contains("Vienna", result2.Text);

        var chatHistory = await this.Fixture.GetChatHistoryAsync(thread);
        Assert.Equal(4, chatHistory.Count);
        Assert.Equal(2, chatHistory.Count(x => x.Role == ChatRole.User));
        Assert.Equal(2, chatHistory.Count(x => x.Role == ChatRole.Assistant));
        Assert.Equal(Q1, chatHistory[0].Text);
        Assert.Equal(Q2, chatHistory[2].Text);
        Assert.Contains("Paris", chatHistory[1].Text);
        Assert.Contains("Vienna", chatHistory[3].Text);
    }
}
