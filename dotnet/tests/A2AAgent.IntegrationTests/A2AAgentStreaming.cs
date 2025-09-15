// Copyright (c) Microsoft. All rights reserved.

using System;
using System.ClientModel;
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using A2A;
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

        string responseText = "";
        ContinuationToken? firstContinuationToken = null;
        ContinuationToken? lastContinuationToken = null;

        // Act
        await foreach (var update in agent.RunStreamingAsync("What is the capital of France?"))
        {
            firstContinuationToken ??= update.ContinuationToken;

            responseText += update;
            lastContinuationToken = update.ContinuationToken;
        }

        // Assert
        Assert.Contains("Paris", responseText, StringComparison.OrdinalIgnoreCase);
        Assert.NotNull(firstContinuationToken);
        Assert.Null(lastContinuationToken);
    }

    //[Fact]
    //public async Task RunStreamingAsync_HavingReturnedInitialTaskResponse_AllowsToContinueItAsync()
    //{
    //    // Part 1: Start the background run and get the first part of the response.
    //    AIAgent agent = await this.CreateA2AAgentAsync();

    //    string responseText = "";
    //    ContinuationToken? firstContinuationToken = null;
    //    ContinuationToken? lastContinuationToken = null;

    //    await foreach (var update in agent.RunStreamingAsync("What is the capital of France?"))
    //    {
    //        responseText += update;

    //        break;
    //    }

    //    Assert.NotNull(firstContinuationToken);
    //    Assert.NotNull(responseText);

    //    // Part 2: Continue getting the rest of the response from the saved point
    //    AgentRunOptions options = new();
    //    options.ContinuationToken = firstContinuationToken;

    //    await foreach (var update in agent.RunStreamingAsync("What is the capital of France?", options: options))
    //    {
    //        responseText += update;

    //        lastContinuationToken = update.ContinuationToken;
    //    }

    //    Assert.Contains("Paris", responseText);
    //    Assert.Null(lastContinuationToken);
    //}

    [Fact]
    public async Task CancelRunAsync_WhenCalled_CancelsRunAsync()
    {
        // Arrange
        AIAgent agent = await this.CreateA2AAgentAsync();

        IAsyncEnumerable<AgentRunResponseUpdate> streamingResponse = agent.RunStreamingAsync("What is the capital of France?");

        var update = (await streamingResponse.ElementAtAsync(0));

        // Act
        AgentRunResponse? response = await agent.CancelRunAsync(update.ResponseId!);

        // Assert
        Assert.NotNull(response);
        Assert.NotNull(response.ResponseId);
    }

    private async Task<AIAgent> CreateA2AAgentAsync()
    {
        A2ACardResolver a2ACardResolver = new(new Uri("http://localhost:5048"));

        return await a2ACardResolver.GetAIAgentAsync();
    }
}
