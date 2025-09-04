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
    public async Task GetResponseAsync_WithAwaitModeProvidedViaOptions_ReturnsExpectedResponseAsync(bool awaitRunCompletion)
    {
        // Arrange
        using var client = await CreateChatClientAsync();

        NewChatOptions options = new()
        {
            AwaitLongRunCompletion = awaitRunCompletion
        };

        // Act
        NewChatResponse response = (NewChatResponse)await client.GetResponseAsync("What is the capital of France?", options);

        // Assert
        Assert.NotNull(response);

        if (awaitRunCompletion)
        {
            Assert.Single(response.Messages);
            Assert.Contains("Paris", response.Text);
        }
        else
        {
            Assert.NotNull(response.ResponseId);
            Assert.Equal(NewResponseStatus.Queued, response.Status);
        }
    }

    [Theory]
    [InlineData(true)]
    [InlineData(false)]
    public async Task GetResponseAsync_WithAwaitModeProvidedAtInitialization_ReturnsExpectedResponseAsync(bool awaitRunCompletion)
    {
        // Arrange
        using var client = await CreateChatClientAsync(awaitRun: awaitRunCompletion);

        // Act
        NewChatResponse response = (NewChatResponse)await client.GetResponseAsync("What is the capital of France?");

        // Assert
        Assert.NotNull(response);

        if (awaitRunCompletion)
        {
            Assert.Single(response.Messages);
            Assert.Contains("Paris", response.Text);
        }
        else
        {
            Assert.NotNull(response.ResponseId);
            Assert.Equal(NewResponseStatus.Queued, response.Status);
        }
    }

    [Fact]
    public async Task GetResponseAsync_HavingReturnedInitialResponse_AllowsCallerToPollAsync()
    {
        // Part 1: Start the background run.
        using var client = await CreateChatClientAsync();

        NewChatOptions options = new()
        {
            AwaitLongRunCompletion = false
        };

        NewChatResponse response = (NewChatResponse)await client.GetResponseAsync("What is the capital of France?", options);

        Assert.NotNull(response);
        Assert.NotNull(response.ResponseId);
        Assert.Equal(NewResponseStatus.Queued, response.Status);

        // Part 2: Poll for completion.
        int attempts = 0;

        while (response.Status is { } status &&
            status != NewResponseStatus.Completed &&
            ++attempts < 5)
        {
            options.ConversationId = response.ConversationId;
            options.ResponseId = response.ResponseId!;

            response = (NewChatResponse)await client.GetResponseAsync([], options);

            // Wait for the response to be processed
            await Task.Delay(2000);
        }

        Assert.NotNull(response);
        Assert.Single(response.Messages);
        Assert.Contains("Paris", response.Text);
        Assert.NotNull(response.ResponseId);
        Assert.Equal(NewResponseStatus.Completed, response.Status);
    }

    [Fact]
    public async Task GetResponseAsync_HavingReturnedInitialResponse_CanDoPollingItselfAsync()
    {
        // Part 1: Start the background run.
        using var client = await CreateChatClientAsync();

        NewChatOptions options = new()
        {
            AwaitLongRunCompletion = false
        };

        NewChatResponse response = (NewChatResponse)await client.GetResponseAsync("What is the capital of France?", options);

        Assert.NotNull(response);
        Assert.NotNull(response.ResponseId);
        Assert.Equal(NewResponseStatus.Queued, response.Status);

        // Part 2: Wait for completion.
        options.ConversationId = response.ConversationId;
        options.ResponseId = response.ResponseId;
        options.AwaitLongRunCompletion = true;

        response = (NewChatResponse)await client.GetResponseAsync([], options);

        Assert.NotNull(response);
        Assert.Single(response.Messages);
        Assert.Contains("Paris", response.Text);
        Assert.NotNull(response.ResponseId);
        Assert.Equal(NewResponseStatus.Completed, response.Status);
    }

    [Fact]
    public async Task GetResponseAsync_WithFunctionCalling_AndAwaitModeEnabled_CallsFunctionAsync()
    {
        // Arrange
        using var client = await CreateChatClientAsync();

        NewChatOptions options = new()
        {
            AwaitLongRunCompletion = true,
            Tools = [AIFunctionFactory.Create(() => "5:43", new AIFunctionFactoryOptions { Name = "GetCurrentTime" })]
        };

        // Act
        ChatResponse response = await client.GetResponseAsync("What time is it?", options);

        // Assert
        Assert.Contains("5:43", response.Text);
    }

    [Fact]
    public async Task GetResponseAsync_WithFunctionCalling_HavingReturnedInitialResponse_AllowsCallerPollAsync()
    {
        // Part 1: Start the background run.
        using var client = await CreateChatClientAsync();

        NewChatOptions options = new()
        {
            AwaitLongRunCompletion = false,
            Tools = [AIFunctionFactory.Create(() => "5:43", new AIFunctionFactoryOptions { Name = "GetCurrentTime" })]
        };

        NewChatResponse response = (NewChatResponse)await client.GetResponseAsync("What time is it?", options);

        Assert.NotNull(response);
        Assert.NotNull(response.ResponseId);
        Assert.Equal(NewResponseStatus.Queued, response.Status);

        // Part 2: Poll for completion.
        int attempts = 0;

        while (response.Status is { } status &&
            status != NewResponseStatus.Completed &&
            ++attempts < 5)
        {
            options.ConversationId = response.ConversationId;
            options.ResponseId = response.ResponseId!;

            response = (NewChatResponse)await client.GetResponseAsync([], options);

            // Wait for the response to be processed
            await Task.Delay(2000);
        }

        Assert.Contains("5:43", response.Text);
    }

    [Fact]
    public async Task GetResponseAsync_WithFunctionCalling_HavingReturnedInitialResponse_CanPollItselfAsync()
    {
        // Part 1: Start the background run.
        using var client = await CreateChatClientAsync();

        NewChatOptions options = new()
        {
            AwaitLongRunCompletion = false,
            Tools = [AIFunctionFactory.Create(() => "5:43", new AIFunctionFactoryOptions { Name = "GetCurrentTime" })]
        };

        NewChatResponse response = (NewChatResponse)await client.GetResponseAsync("What time is it?", options);

        Assert.NotNull(response);
        Assert.NotNull(response.ResponseId);
        Assert.Equal(NewResponseStatus.Queued, response.Status);

        // Part 2: Wait for completion.
        options.ConversationId = response.ConversationId;
        options.ResponseId = response.ResponseId;
        options.AwaitLongRunCompletion = true;

        response = (NewChatResponse)await client.GetResponseAsync([], options);

        Assert.NotNull(response);
        Assert.Equal(3, response.Messages.Count);
        Assert.Contains("5:43", response.Text);
        Assert.NotNull(response.ResponseId);
        Assert.Equal(NewResponseStatus.Completed, response.Status);
    }

    [Fact]
    public async Task CancelRunAsync_WhenCalled_CancelsRunAsync()
    {
        // Arrange
        using var client = await CreateChatClientAsync();

        NewChatOptions options = new()
        {
            AwaitLongRunCompletion = false,
            Tools = [AIFunctionFactory.Create(() => "5:43", new AIFunctionFactoryOptions { Name = "GetCurrentTime" })]
        };

        ILongRunningChatClient runnableChatClient = client.GetService<ILongRunningChatClient>()!;

        NewChatResponse response = (NewChatResponse)await runnableChatClient.GetResponseAsync("What time is it?", options);

        // Act
        NewChatResponse? cancelResponse = (NewChatResponse?)await runnableChatClient.CancelRunAsync(RunId.FromChatResponse(response));

        // Assert
        Assert.NotNull(cancelResponse);

        Assert.True(cancelResponse.Status == NewResponseStatus.Cancelling || cancelResponse.Status == NewResponseStatus.Canceled);
    }

    [Fact]
    public async Task DeleteRunAsync_WhenCalled_DeletesRunAsync()
    {
        // Arrange
        using var client = await CreateChatClientAsync();

        NewChatOptions options = new()
        {
            AwaitLongRunCompletion = false
        };

        ILongRunningChatClient runnableChatClient = client.GetService<ILongRunningChatClient>()!;

        // Act
        ChatResponse? deleteResponse = await runnableChatClient.DeleteRunAsync(new RunId());  // Deletion of runs is not supported

        // Assert
        Assert.Null(deleteResponse);
    }

    private static async Task<IChatClient> CreateChatClientAsync(bool? awaitRun = null)
    {
        PersistentAgentsClient persistentAgentsClient = new(s_config.Endpoint, new AzureCliCredential());

        var persistentAgentResponse = await persistentAgentsClient.Administration.CreateAgentAsync(
            model: s_config.DeploymentName,
            name: "LongRunningExecutionAgent",
            instructions: "You are a helpful assistant.");

        var persistentChatClient = persistentAgentsClient.AsNewIChatClient(persistentAgentResponse.Value.Id, awaitRunCompletion: awaitRun);

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
