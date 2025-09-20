// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using AgentConformance.IntegrationTests.Support;
using Azure.AI.Agents.Persistent;
using Azure.Identity;
using Microsoft.Extensions.AI;
using Shared.IntegrationTests;

namespace AzureAIAgentsPersistent.IntegrationTests;

public sealed class NewPersistentAgentsChatClientTests
{
    private static readonly AzureAIConfiguration s_config = TestConfiguration.LoadSection<AzureAIConfiguration>();

    [Theory]
    [InlineData(true)]
    [InlineData(false)]
    public async Task GetResponseAsync_WithLongRunningResponsesEnabledViaOptions_ReturnsExpectedResponseAsync(bool enableLongRunningResponses)
    {
        // Arrange
        using var client = await CreateChatClientAsync();

        NewChatOptions options = new()
        {
            AllowLongRunningResponses = enableLongRunningResponses
        };

        // Act
        NewChatResponse response = (NewChatResponse)await client.GetResponseAsync("What is the capital of France?", options);

        // Assert
        Assert.NotNull(response);

        if (enableLongRunningResponses)
        {
            Assert.NotNull(response.ContinuationToken);
        }
        else
        {
            Assert.Null(response.ContinuationToken);
            Assert.Contains("Paris", response.Text);
        }
    }

    [Fact]
    public async Task GetResponseAsync_HavingReturnedInitialResponse_AllowsCallerToPollAsync()
    {
        // Part 1: Start the background run.
        using var client = await CreateChatClientAsync();

        NewChatOptions options = new()
        {
            AllowLongRunningResponses = true
        };

        NewChatResponse response = (NewChatResponse)await client.GetResponseAsync("What is the capital of France?", options);

        Assert.NotNull(response.ContinuationToken);

        // Part 2: Poll for completion.
        int attempts = 0;

        while (response.ContinuationToken is { } token && ++attempts < 5)
        {
            options.ContinuationToken = token;

            response = (NewChatResponse)await client.GetResponseAsync([], options);

            // Wait for the response to be processed
            await Task.Delay(2000);
        }

        Assert.Null(response.ContinuationToken);
        Assert.Contains("Paris", response.Text);
    }

    [Fact]
    public async Task GetResponseAsync_WithFunctionCalling_AndLongRunningResponsesDisabled_CallsFunctionAsync()
    {
        // Arrange
        using var client = await CreateChatClientAsync();

        NewChatOptions options = new()
        {
            AllowLongRunningResponses = false,
            Tools = [AIFunctionFactory.Create(() => "5:43", new AIFunctionFactoryOptions { Name = "GetCurrentTime" })]
        };

        // Act
        NewChatResponse response = (NewChatResponse)await client.GetResponseAsync("What time is it?", options);

        // Assert
        Assert.Contains("5:43", response.Text);
        Assert.Null(response.ContinuationToken);
    }

    [Fact]
    public async Task GetResponseAsync_WithOneFunction_HavingReturnedInitialResponse_AllowsCallerPollAsync()
    {
        // Part 1: Start the background run.
        using var client = await CreateChatClientAsync();

        NewChatOptions options = new()
        {
            AllowLongRunningResponses = true,
            Tools = [AIFunctionFactory.Create(() => "5:43", new AIFunctionFactoryOptions { Name = "GetCurrentTime" })]
        };

        NewChatResponse response = (NewChatResponse)await client.GetResponseAsync("What time is it?", options);

        Assert.NotNull(response.ContinuationToken);

        // Part 2: Poll for completion.
        int attempts = 0;

        while (response.ContinuationToken is { } token && ++attempts < 5)
        {
            options.ContinuationToken = token;

            response = (NewChatResponse)await client.GetResponseAsync([], options);

            // Wait for the response to be processed
            await Task.Delay(2000);
        }

        Assert.Contains("5:43", response.Text);
        Assert.Null(response.ContinuationToken);
    }

    [Fact]
    public async Task GetResponseAsync_WithTwoFunctions_HavingReturnedInitialResponse_AllowsCallerPollAsync()
    {
        // Part 1: Start the background run.
        using var client = await CreateChatClientAsync();

        NewChatOptions options = new()
        {
            AllowLongRunningResponses = true,
            Tools = [
                AIFunctionFactory.Create(() => new DateTime(2025, 09, 16, 05, 43,00), new AIFunctionFactoryOptions { Name = "GetCurrentTime" }),
                AIFunctionFactory.Create((DateTime time, string location) => $"It's cloudy in {location} at {time}", new AIFunctionFactoryOptions { Name = "GetWeather" })
            ]
        };

        NewChatResponse response = (NewChatResponse)await client.GetResponseAsync("What's the weather in Paris right now? Include the time.", options);

        Assert.NotNull(response.ContinuationToken);

        // Part 2: Poll for completion.
        int attempts = 0;

        while (response.ContinuationToken is { } token && ++attempts < 5)
        {
            options.ContinuationToken = token;

            response = (NewChatResponse)await client.GetResponseAsync([], options);

            // Wait for the response to be processed
            await Task.Delay(2000);
        }

        Assert.Contains("5:43", response.Text);
        Assert.Contains("cloud", response.Text);
        Assert.Null(response.ContinuationToken);
    }

    [Fact]
    public async Task CancelRunAsync_WhenCalled_CancelsRunAsync()
    {
        // Arrange
        using var client = await CreateChatClientAsync();

        NewChatOptions options = new()
        {
            AllowLongRunningResponses = true
        };

        NewChatResponse response = (NewChatResponse)await client.GetResponseAsync("What time is it?", options);

        ICancelableChatClient cancelableChatClient = client.GetService<ICancelableChatClient>()!;

        // Act
        NewChatResponse? cancelResponse = (NewChatResponse?)await cancelableChatClient.CancelResponseAsync(response!.ResponseId!, new() { ConversationId = response.ConversationId });

        // Assert
        Assert.NotNull(cancelResponse);
    }

    private static async Task<IChatClient> CreateChatClientAsync()
    {
        PersistentAgentsClient persistentAgentsClient = new(s_config.Endpoint, new AzureCliCredential());

        var persistentAgentResponse = await persistentAgentsClient.Administration.CreateAgentAsync(
            model: s_config.DeploymentName,
            name: "LongRunningExecutionAgent",
            instructions: "You are a helpful assistant.");

        var persistentChatClient = persistentAgentsClient.AsNewIChatClient(persistentAgentResponse.Value.Id);

        var functionInvokingChatClient = new NewFunctionInvokingChatClient(persistentChatClient);

        return new ChatClientTestProxy(persistentAgentsClient, persistentAgentResponse.Value.Id, functionInvokingChatClient);

        //var chatClient = persistentAgentsClient.AsNewIChatClient(persistentAgentResponse.Value.Id, awaitRun: awaitRun)
        //    .AsBuilder()
        //    .UseFunctionInvocation()
        //    .Build();

        //return new ChatClientTestProxy(persistentAgentsClient, persistentAgentResponse.Value.Id, chatClient);
    }

    private sealed class ChatClientTestProxy : IChatClient
    {
        private readonly PersistentAgentsClient _persistentAgentsClient;
        private readonly string _agentId;
        private readonly IChatClient _innerChatClient;

        public ChatClientTestProxy(PersistentAgentsClient persistentAgentsClient, string agentId, IChatClient innerChatClient)
        {
            this._persistentAgentsClient = persistentAgentsClient;
            this._agentId = agentId;
            this._innerChatClient = innerChatClient;
        }

        public Task<ChatResponse> GetResponseAsync(IEnumerable<ChatMessage> messages, ChatOptions? options = null, CancellationToken cancellationToken = default)
        {
            return this._innerChatClient.GetResponseAsync(messages, options, cancellationToken);
        }

        public IAsyncEnumerable<ChatResponseUpdate> GetStreamingResponseAsync(IEnumerable<ChatMessage> messages, ChatOptions? options = null, CancellationToken cancellationToken = default)
        {
            return this._innerChatClient.GetStreamingResponseAsync(messages, options, cancellationToken);
        }

        public object? GetService(Type serviceType, object? serviceKey = null)
        {
            return this._innerChatClient.GetService(serviceType, serviceKey);
        }

        public void Dispose()
        {
            this._persistentAgentsClient.Administration.DeleteAgent(this._agentId);
        }
    }
}
