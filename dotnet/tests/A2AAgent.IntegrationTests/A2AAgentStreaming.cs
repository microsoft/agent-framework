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
    [Theory]
    [InlineData(true)]
    [InlineData(false)]
    public async Task RunStreamingAsync_WithAwaitModeProvidedViaOptions_ReturnsExpectedResponseAsync(bool awaitRunCompletion)
    {
        // Arrange
        AIAgent agent = await this.CreateA2AAgentAsync();

        AgentRunOptions options = new()
        {
            AwaitLongRunCompletion = awaitRunCompletion
        };

        List<NewResponseStatus> statuses = [];
        string responseText = "";

        // Act
        await foreach (var update in agent.RunStreamingAsync("What is the capital of France?", options: options))
        {
            if (update.Status is { } status)
            {
                statuses.Add(status);
            }

            responseText += update;
        }

        // Assert
        if (awaitRunCompletion)
        {
            Assert.Contains(NewResponseStatus.Submitted, statuses);
            Assert.Contains(NewResponseStatus.InProgress, statuses);
            Assert.Contains(NewResponseStatus.Completed, statuses);
            Assert.Contains("Paris", responseText, StringComparison.OrdinalIgnoreCase);
        }
        else
        {
            Assert.Single(statuses);
            Assert.Contains(NewResponseStatus.Submitted, statuses);
        }
    }

    [Theory]
    [InlineData(true)]
    [InlineData(false)]
    public async Task RunStreamingAsync_WithAwaitModeProvidedAtInitialization_ReturnsExpectedResponseAsync(bool awaitRunCompletion)
    {
        // Arrange
        AIAgent agent = await this.CreateA2AAgentAsync(awaitRunCompletion);

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
        if (awaitRunCompletion)
        {
            Assert.Contains(NewResponseStatus.Submitted, statuses);
            Assert.Contains(NewResponseStatus.InProgress, statuses);
            Assert.Contains(NewResponseStatus.Completed, statuses);
            Assert.Contains("Paris", responseText, StringComparison.OrdinalIgnoreCase);
        }
        else
        {
            Assert.Single(statuses);
            Assert.Contains(NewResponseStatus.Submitted, statuses);
        }
    }

    [Theory]
    [InlineData(true)]
    [InlineData(false)]
    public async Task GetStreamingResponseAsync_HavingReturnedInitialResponse_AllowsToContinueItAsync(bool continueWithAwaiting)
    {
        // Part 1: Start the background run and get the first part of the response.
        AIAgent agent = await this.CreateA2AAgentAsync();

        AgentRunOptions options = new()
        {
            AwaitLongRunCompletion = false
        };

        List<NewResponseStatus> statuses = [];
        string responseText = "";
        string? responseId = null;

        await foreach (var update in agent.RunStreamingAsync("What is the capital of France?", options: options))
        {
            if (update.Status is { } status)
            {
                statuses.Add(status);
            }

            responseText += update;

            responseId = update.ResponseId;
        }

        Assert.Contains(NewResponseStatus.Submitted, statuses);
        Assert.NotNull(responseText);
        Assert.NotNull(responseId);

        // Part 2: Continue getting the rest of the response from the saved point
        options.AwaitLongRunCompletion = continueWithAwaiting;
        options.ResponseId = responseId;
        statuses.Clear();

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

    [Fact]
    public async Task DeleteRunAsync_WhenCalled_CancelsRunAsync()
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
        AgentRunResponse? response = await agent.DeleteRunAsync(update.ResponseId!);

        // Assert
        Assert.Null(response); // A2A does not support deletion, so we expect null
    }

    private async Task<AIAgent> CreateA2AAgentAsync(bool? awaitRunCompletion = null)
    {
        A2ACardResolver a2ACardResolver = new(new Uri("http://localhost:5048"));

        return await a2ACardResolver.GetAIAgentAsync(awaitRunCompletion);
    }
}
