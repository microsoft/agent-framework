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
public abstract class RunStreamingTests<TAgentFixture>(Func<TAgentFixture> createAgentFixture) : AgentTests<TAgentFixture>(createAgentFixture)
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
        var chatResponses = await agent.RunStreamingAsync(thread).ToListAsync();
    }

    [RetryFact(Constants.RetryCount, Constants.RetryDelay)]
    public virtual async Task RunWithStringReturnsExpectedResultAsync()
    {
        // Arrange
        var agent = this.Fixture.Agent;
        var thread = agent.GetNewThread();
        await using var cleanup = new ThreadCleanup(thread, this.Fixture);

        // Act
        var responseUpdates = await agent.RunStreamingAsync("What is the capital of France.", thread).ToListAsync();

        // Assert
        var chatResponseText = string.Concat(responseUpdates.Select(x => x.Text));
        Assert.Contains("Paris", chatResponseText);
    }

    [RetryFact(Constants.RetryCount, Constants.RetryDelay)]
    public virtual async Task RunWithChatMessageReturnsExpectedResultAsync()
    {
        // Arrange
        var agent = this.Fixture.Agent;
        var thread = agent.GetNewThread();
        await using var cleanup = new ThreadCleanup(thread, this.Fixture);

        // Act
        var responseUpdates = await agent.RunStreamingAsync(new ChatMessage(ChatRole.User, "What is the capital of France."), thread).ToListAsync();

        // Assert
        var chatResponseText = string.Concat(responseUpdates.Select(x => x.Text));
        Assert.Contains("Paris", chatResponseText);
    }

    [RetryFact(Constants.RetryCount, Constants.RetryDelay)]
    public virtual async Task RunWithChatMessagesReturnsExpectedResultAsync()
    {
        // Arrange
        var agent = this.Fixture.Agent;
        var thread = agent.GetNewThread();
        await using var cleanup = new ThreadCleanup(thread, this.Fixture);

        // Act
        var responseUpdates = await agent.RunStreamingAsync(
            [
                new ChatMessage(ChatRole.User, "Hello."),
                new ChatMessage(ChatRole.User, "What is the capital of France.")
            ],
            thread).ToListAsync();

        // Assert
        var chatResponseText = string.Concat(responseUpdates.Select(x => x.Text));
        Assert.Contains("Paris", chatResponseText);
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
        var responseUpdates1 = await agent.RunStreamingAsync(Q1, thread).ToListAsync();
        var responseUpdates2 = await agent.RunStreamingAsync(Q2, thread).ToListAsync();

        // Assert
        var response1Text = string.Concat(responseUpdates1.Select(x => x.Text));
        var response2Text = string.Concat(responseUpdates2.Select(x => x.Text));
        Assert.Contains("Paris", response1Text);
        Assert.Contains("Vienna", response2Text);

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
