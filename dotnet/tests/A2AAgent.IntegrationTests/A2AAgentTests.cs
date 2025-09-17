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
        Assert.NotNull(response.ContinuationToken);
    }

    [Fact]
    public async Task RunAsync_HavingReturnedInitialResponse_AllowsCallerToPollAsync()
    {
        // Part 1: Start the background run.
        AIAgent agent = await this.CreateA2AAgentAsync();

        AgentRunResponse response = await agent.RunAsync("What is the capital of France?");

        Assert.NotNull(response);
        Assert.NotNull(response.ResponseId);
        Assert.NotNull(response.ContinuationToken);

        // Part 2: Poll for completion.
        AgentRunOptions options = new();

        int attempts = 0;

        while (response.ContinuationToken is { } token && ++attempts < 10)
        {
            options.ContinuationToken = token;

            response = await agent.RunAsync([], options: options);

            // Wait for the response to be processed
            await Task.Delay(1000);
        }

        Assert.NotNull(response);
        Assert.Contains("Paris", response.Text);
        Assert.Null(response.ContinuationToken);
    }

    [Fact]
    public async Task RunAsync_HavingReceivedUpdate_TakesItIntoAccountAsync()
    {
        // Part 1: Start the background run.
        AIAgent agent = await this.CreateA2AAgentAsync();

        AgentRunResponse response = await agent.RunAsync("What is the capital of France?");

        Assert.NotNull(response.ContinuationToken);

        // Part 2: Send an update.
        AgentRunOptions options = new()
        {
            ContinuationToken = response.ContinuationToken
        };

        response = await agent.RunAsync("Sorry I meant Belgium.", options: options);

        // Part 3: Poll for completion.
        int attempts = 0;

        while (response.ContinuationToken is { } token && ++attempts < 10)
        {
            options.ContinuationToken = token;

            response = await agent.RunAsync([], options: options);

            // Wait for the response to be processed
            await Task.Delay(1000);
        }

        Assert.Null(response.ContinuationToken);
        Assert.Contains("Brussels", response.Text);
    }

    [Fact]
    public async Task RunAsync_HavingTaskRequiringUserInput_CanHandleItAsync()
    {
        AIAgent agent = await this.CreateA2AAgentAsync();

        AgentThread thread = agent.GetNewThread();

        // 1. Ask the agent to book a flight intentionally omitting details to trigger user input request
        AgentRunResponse response = await agent.RunAsync("I'd like to book a flight.", thread);

        // 2. Poll for completion or user input request
        AgentRunOptions options = new();

        while (response.ContinuationToken is { } token && !response.UserInputRequests.Any())
        {
            options.ContinuationToken = token;

            response = await agent.RunAsync([], thread, options: options);

            // Wait for the response to be processed
            await Task.Delay(1000);
        }

        // 3. Handle user input requests
        while (response.UserInputRequests.Any())
        {
            List<ChatMessage> messages = [];

            if (response.UserInputRequests.Single() is TextInputRequestContent detailsRequest)
            {
                Assert.Contains("Where would you like to fly to, and from where?", detailsRequest.Text);
                messages.Add(new ChatMessage(ChatRole.User, [detailsRequest.CreateResponse("I want to fly from New York (JFK) to London (LHR) around October 10th, returning October 17th.")]));
            }

            options.ContinuationToken = response.ContinuationToken;

            // Provide the user responses to the agent
            response = await agent.RunAsync(messages, thread, options);
        }

        // 4. Poll for completion.
        int attempts = 0;

        while (response.ContinuationToken is { } token && ++attempts < 10)
        {
            options.ContinuationToken = token;

            response = await agent.RunAsync([], options: options);

            // Wait for the response to be processed
            await Task.Delay(1000);
        }

        Assert.Null(response.ContinuationToken);

        var dataContent = Assert.Single(response.Messages.SelectMany(m => m.Contents.OfType<DataContent>()));

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

        AgentRunResponse response = await agent.RunAsync("What is the capital of France?");

        // Act
        AgentRunResponse? cancelResponse = await agent.CancelRunAsync(response.ResponseId!);

        // Assert
        Assert.NotNull(cancelResponse);
    }

    private async Task<AIAgent> CreateA2AAgentAsync()
    {
        A2ACardResolver a2ACardResolver = new(new Uri("http://localhost:5048"));

        return await a2ACardResolver.GetAIAgentAsync();
    }
}
