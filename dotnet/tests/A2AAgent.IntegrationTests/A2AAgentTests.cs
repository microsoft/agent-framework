// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading.Tasks;
using A2A;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.AI.Agents;
using Microsoft.Extensions.AI.Agents.A2A;

namespace AgentConformance.IntegrationTests;

public class A2AAgentTests
{
    [Fact]
    public async Task RunAsync_WhenHandlingTask_ReturnsInitialResponseAsync()
    {
        // Arrange
        AIAgent agent = await this.CreateA2AAgentAsync();

        // Act
        AgentRunResponse response = await agent.RunAsync("What is the capital of France?");

        // Assert
        Assert.NotNull(response);
        Assert.NotNull(response.ResponseId);
        Assert.Equal(NewResponseStatus.Submitted, response.Status);
    }

    [Fact]
    public async Task RunAsync_HavingReturnedInitialResponse_AllowsCallerToPollAsync()
    {
        // Part 1: Start the background run.
        AIAgent agent = await this.CreateA2AAgentAsync();

        AgentRunResponse response = await agent.RunAsync("What is the capital of France?");

        Assert.NotNull(response);
        Assert.NotNull(response.ResponseId);
        Assert.Equal(NewResponseStatus.Submitted, response.Status);

        // Part 2: Poll for completion.
        AgentRunOptions options = new();

        int attempts = 0;

        while (response.Status is { } status &&
            status != NewResponseStatus.Completed &&
            ++attempts < 10)
        {
            options.ResponseId = response.ResponseId!;

            response = await agent.RunAsync([], options: options);

            // Wait for the response to be processed
            await Task.Delay(1000);
        }

        Assert.NotNull(response);
        Assert.Equal(2, response.Messages.Count);
        Assert.Contains("Paris", response.Text);
        Assert.NotNull(response.ResponseId);
        Assert.Equal(NewResponseStatus.Completed, response.Status);
    }

    [Fact]
    public async Task CancelRunAsync_WhenCalled_CancelsRunAsync()
    {
        // Arrange
        AIAgent agent = await this.CreateA2AAgentAsync();

        AgentRunResponse response = await agent.RunAsync("What is the capital of France?");

        // Act
        AgentRunResponse? cancelResponse = await agent.CancelRunAsync(response.ResponseId!);

        // Assert
        Assert.NotNull(cancelResponse);
        Assert.Equal(NewResponseStatus.Canceled, cancelResponse.Status);
    }

    private async Task<AIAgent> CreateA2AAgentAsync()
    {
        A2ACardResolver a2ACardResolver = new(new Uri("http://localhost:5048"));

        return await a2ACardResolver.GetAIAgentAsync();
    }
}
