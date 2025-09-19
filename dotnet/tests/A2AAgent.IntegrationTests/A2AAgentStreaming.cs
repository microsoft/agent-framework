// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using System.Text.Json;
using System.Threading.Tasks;
using A2A;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.AI.Agents;
using Microsoft.Extensions.AI.Agents.A2A;

#pragma warning disable MEAI001 // Type is for evaluation purposes only and is subject to change or removal in future updates. Suppress this diagnostic to proceed.

namespace AgentConformance.IntegrationTests;

public sealed class A2AAgentStreaming
{
    [Fact]
    public async Task RunStreamingAsync_WhenHandlingTask_ReturnsExpectedResponseAsync()
    {
        // Arrange
        AIAgent agent = await this.CreateA2AAgentAsync();

        string responseText = "";
        string? firstContinuationToken = null;
        string? lastContinuationToken = null;

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

    [Fact]
    public async Task RunStreamingAsync_HavingReturnedInitialTaskResponse_AllowsToContinueItAsync()
    {
        // Part 1: Start the background run and get the first part of the response.
        AIAgent agent = await this.CreateA2AAgentAsync();

        string responseText = "";
        string? continuationToken = null;

        await foreach (var update in agent.RunStreamingAsync("What is the capital of France?"))
        {
            responseText += update;

            // Capture continuation token of the first event
            continuationToken = update.ContinuationToken;

            // Break after the first event to simulate connection drop
            break;
        }

        Assert.NotNull(continuationToken);
        Assert.Empty(responseText);

        // Part 2: Continue getting the response using the continuation token.
        AgentRunOptions options = new()
        {
            ContinuationToken = continuationToken
        };

        await foreach (var update in agent.RunStreamingAsync(options: options))
        {
            responseText += update;

            // Keep capturing the continuation token in case the connection drops again
            continuationToken = update.ContinuationToken;
        }

        Assert.Contains("Paris", responseText);
        Assert.Null(continuationToken);
    }

    [Fact]
    public async Task RunStreamingAsync_HavingReceivedUpdate_TakesItIntoAccountAsync()
    {
        // Part 1: Start the background run and get the first part of the response.
        AIAgent agent = await this.CreateA2AAgentAsync();

        string responseText = "";
        string? continuationToken = null;

        await foreach (var update in agent.RunStreamingAsync("What is the capital of France?"))
        {
            responseText += update;

            // Capture continuation token of the first event
            continuationToken = update.ContinuationToken;

            // Break after the first event to simulate connection drop
            break;
        }

        Assert.NotNull(continuationToken);
        Assert.Empty(responseText);

        // Part 2: Send an update.
        AgentRunOptions options = new()
        {
            ContinuationToken = continuationToken
        };

        await foreach (var update in agent.RunStreamingAsync("Sorry I meant Belgium.", options: options))
        {
            responseText += update;

            // Keep capturing the continuation token in case the connection drops again
            continuationToken = update.ContinuationToken;
        }

        Assert.Contains("Brussels", responseText);
        Assert.Null(continuationToken);
    }

    [Fact]
    public async Task RunStreamingAsync_HavingTaskRequiringUserInput_CanHandleItAsync()
    {
        AIAgent agent = await this.CreateA2AAgentAsync();

        AgentThread thread = agent.GetNewThread();

        string? continuationToken = null;
        UserInputRequestContent[]? userInputsRequests = null;

        // 1. Ask the agent to book a flight intentionally omitting details to trigger user input request
        await foreach (var update in agent.RunStreamingAsync("I'd like to book a flight.", thread))
        {
            // Capture continuation token to be able to continue the task later
            continuationToken = update.ContinuationToken;

            // 2. Wait for the user input request
            if (update.UserInputRequests.Any())
            {
                userInputsRequests = [.. update.UserInputRequests];
                break; // Exit the loop to handle user input
            }
        }

        List<ChatMessage> messages = [];

        // 3. Handle user input requests
        if (userInputsRequests is not null)
        {
            if (userInputsRequests.Single() is TextInputRequestContent detailsRequest)
            {
                Assert.Contains("Where would you like to fly to, and from where?", detailsRequest.Text);
                messages.Add(new ChatMessage(ChatRole.User, [detailsRequest.CreateResponse("I want to fly from New York (JFK) to London (LHR) around October 10th, returning October 17th.")]));
            }
        }

        // 4. Provide the user responses to the agent
        AgentRunOptions options = new()
        {
            ContinuationToken = continuationToken
        };

        List<AIContent> contents = [];

        await foreach (var update in agent.RunStreamingAsync(messages, thread, options))
        {
            contents.AddRange(update.Contents);
        }

        var dataContent = Assert.Single(contents.OfType<DataContent>());

        var originalContent = JsonSerializer.Deserialize<Dictionary<string, JsonElement>>(Encoding.UTF8.GetString(dataContent.Data.ToArray()));
        Assert.NotNull(originalContent);
        Assert.Equal("XYZ123", originalContent["confirmationId"].GetString());
        Assert.Equal("JFK", originalContent["from"].GetString());
        Assert.Equal("LHR", originalContent["to"].GetString());
        Assert.Equal("2024-10-10T18:00:00Z", originalContent["departure"].GetString());
        Assert.Equal("2024-10-11T06:00:00Z", originalContent["arrival"].GetString());
    }

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
