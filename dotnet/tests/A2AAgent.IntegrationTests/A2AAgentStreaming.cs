// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using A2A;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.AI.Agents;
using Microsoft.Extensions.AI.Agents.A2A;

namespace AgentConformance.IntegrationTests;

public sealed class A2AAgentStreaming
{
    [Fact]
    public async Task RunStreamingAsync_WhenHandlingTask_ReturnsExpectedResponseAsync()
    {
        // Arrange
        AIAgent agent = await this.CreateA2AAgentAsync();

        List<NewResponseStatus> statuses = [];
        string responseText = "";

        // Act
        await foreach (var update in agent.RunStreamingAsync("What is the capital of France?"))
        {
            if (update.Status is { } status)
            {
                statuses.Add(status);
            }

            responseText += update;
        }

        // Assert
        Assert.Contains(NewResponseStatus.Submitted, statuses);
        Assert.Contains(NewResponseStatus.InProgress, statuses);
        Assert.Contains(NewResponseStatus.Completed, statuses);
        Assert.Contains("Paris", responseText, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public async Task RunStreamingAsync_HavingReturnedInitialTaskResponse_AllowsToContinueItAsync()
    {
        // Part 1: Start the background run and get the first part of the response.
        AIAgent agent = await this.CreateA2AAgentAsync();

        List<NewResponseStatus> statuses = [];
        string responseText = "";
        string? responseId = null;

        await foreach (var update in agent.RunStreamingAsync("What is the capital of France?"))
        {
            if (update.Status is { } status)
            {
                statuses.Add(status);
            }

            responseId = update.ResponseId;

            break;
        }

        Assert.Contains(NewResponseStatus.Submitted, statuses);
        Assert.NotNull(responseId);

        // Part 2: Continue getting the rest of the response from the saved point
        statuses.Clear();
        AgentRunOptions options = new()
        {
            ResponseId = responseId
        };

        await foreach (var update in agent.RunStreamingAsync("What is the capital of France?", options: options))
        {
            if (update.Status is { } status)
            {
                statuses.Add(status);
            }

            responseText += update;
        }

        Assert.Contains("Paris", responseText);
        Assert.Contains(NewResponseStatus.Submitted, statuses);
        Assert.Contains(NewResponseStatus.InProgress, statuses);
        Assert.Contains(NewResponseStatus.Completed, statuses);
    }

    [Fact]
    public async Task CancelRunAsync_WhenCalled_CancelsRunAsync()
    {
        // Arrange
        AIAgent agent = await this.CreateA2AAgentAsync();

        AgentRunOptions options = new()
        {
            AwaitLongRunCompletion = false
        };

        IAsyncEnumerable<AgentRunResponseUpdate> streamingResponse = agent.RunStreamingAsync("What is the capital of France?", options: options);

        var update = (await streamingResponse.ElementAtAsync(0));

        // Act
        AgentRunResponse? response = await agent.CancelRunAsync(update.ResponseId!);

        // Assert
        Assert.NotNull(response);
        Assert.NotNull(response.ResponseId);
        Assert.Equal(NewResponseStatus.Canceled, response.Status);
    }

    private async Task<AIAgent> CreateA2AAgentAsync()
    {
        A2ACardResolver a2ACardResolver = new(new Uri("http://localhost:5048"));

        return await a2ACardResolver.GetAIAgentAsync();
    }
}
