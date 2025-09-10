// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using AgentConformance.IntegrationTests.Support;
using Azure.AI.Agents.Persistent;
using Azure.Identity;
using Microsoft.Extensions.AI;
using Shared.IntegrationTests;

namespace AzureAIAgentsPersistent.IntegrationTests;

public sealed class NewPersistentAgentsChatClientStreamingTests
{
    private static readonly AzureAIConfiguration s_config = TestConfiguration.LoadSection<AzureAIConfiguration>();

    [Theory]
    [InlineData(true)]
    [InlineData(false)]
    public async Task GetStreamingResponseAsync_WithAwaitModeProvidedViaOptions_ReturnsExpectedResponseAsync(bool awaitRunCompletion)
    {
        // Arrange
        using var client = await CreateChatClientAsync();

        NewChatOptions options = new()
        {
            AwaitLongRunCompletion = awaitRunCompletion
        };

        List<NewResponseStatus> statuses = [];
        string responseText = "";

        // Act
        await foreach (var update in client.GetStreamingResponseAsync("What is the capital of France?", options).Select(u => (NewChatResponseUpdate)u))
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
            Assert.Empty(statuses);
            Assert.Contains("Paris", responseText, StringComparison.OrdinalIgnoreCase);
        }
        else
        {
            Assert.Single(statuses);
            Assert.Contains(NewResponseStatus.Queued, statuses);
        }
    }

    [Theory]
    [InlineData(true)]
    [InlineData(false)]
    public async Task GetStreamingResponseAsync_WithAwaitModeProvidedAtInitialization_ReturnsExpectedResponseAsync(bool awaitRunCompletion)
    {
        // Arrange
        using var client = await CreateChatClientAsync(awaitRunCompletion);

        List<NewResponseStatus> statuses = [];
        string responseText = "";

        // Act
        await foreach (var update in client.GetStreamingResponseAsync("What is the capital of France?").Select(u => (NewChatResponseUpdate)u))
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
            Assert.Empty(statuses);
            Assert.Contains("Paris", responseText, StringComparison.OrdinalIgnoreCase);
        }
        else
        {
            Assert.Single(statuses);
            Assert.Contains(NewResponseStatus.Queued, statuses);
        }
    }

    [Theory]
    [InlineData(true)]
    [InlineData(false)]
    public async Task GetStreamingResponseAsync_HavingReturnedInitialResponse_AllowsToContinueItAsync(bool continueWithAwaiting)
    {
        // Part 1: Start the background run and get the first part of the response.
        using var client = await CreateChatClientAsync();

        NewChatOptions options = new()
        {
            AwaitLongRunCompletion = false
        };

        List<NewResponseStatus> statuses = [];
        string responseText = "";
        string? responseId = null;
        string? conversationId = null;

        await foreach (var update in client.GetStreamingResponseAsync("What is the capital of France?", options).Select(u => (NewChatResponseUpdate)u))
        {
            if (update.Status is { } status)
            {
                statuses.Add(status);
            }

            responseText += update;

            // Capture the response id, conversation id and sequence number of the first event so we
            // can continue getting the rest of the events starting from the same point in the test below.
            responseId = update.ResponseId;
            conversationId = update.ConversationId;
        }

        Assert.Contains(NewResponseStatus.Queued, statuses);
        Assert.NotNull(responseText);
        Assert.NotNull(responseId);
        Assert.NotNull(conversationId);

        // Part 2: Continue getting the rest of the response from the saved point
        options.AwaitLongRunCompletion = continueWithAwaiting;
        options.ConversationId = conversationId;
        options.ResponseId = responseId;
        statuses.Clear();

        await foreach (var update in client.GetStreamingResponseAsync([], options).Select(u => (NewChatResponseUpdate)u))
        {
            if (update.Status is { } status)
            {
                statuses.Add(status);
            }

            responseText += update;
        }

        if (continueWithAwaiting)
        {
            Assert.Contains("Paris", responseText);
            Assert.Empty(statuses);
        }
        else
        {
            Assert.Contains("Paris", responseText);
            Assert.Contains(NewResponseStatus.InProgress, statuses);
            Assert.Contains(NewResponseStatus.Completed, statuses);
        }
    }

    [Fact]
    public async Task GetStreamingResponseAsync_WithFunctionCalling_AndAwaitModeEnabled_CallsFunctionAsync()
    {
        // Arrange
        using var client = await CreateChatClientAsync();

        NewChatOptions options = new()
        {
            AwaitLongRunCompletion = true,
            Tools = [AIFunctionFactory.Create(() => "5:43", new AIFunctionFactoryOptions { Name = "GetCurrentTime" })]
        };

        List<NewResponseStatus> statuses = [];
        string responseText = "";

        // Act
        await foreach (var update in client.GetStreamingResponseAsync("What time is it?", options).Select(u => (NewChatResponseUpdate)u))
        {
            if (update.Status is { } status)
            {
                statuses.Add(status);
            }

            responseText += update;
        }

        // Assert
        Assert.Contains("5:43", responseText);
        Assert.Empty(statuses);
    }

    [Theory]
    [InlineData(true)]
    [InlineData(false)]
    public async Task GetStreamingResponseAsync_WithFunctionCalling_HavingReturnedInitialResponse_AllowsToContinueItAsync(bool continueWithAwaiting)
    {
        // Part 1: Start the background run.
        using var client = await CreateChatClientAsync();

        NewChatOptions options = new()
        {
            AwaitLongRunCompletion = false,
            Tools = [AIFunctionFactory.Create(() => "5:43", new AIFunctionFactoryOptions { Name = "GetCurrentTime" })]
        };

        List<NewResponseStatus> statuses = [];
        string responseText = "";
        string? responseId = null;
        string? conversationId = null;

        await foreach (var update in client.GetStreamingResponseAsync("What time is it?", options).Select(u => (NewChatResponseUpdate)u))
        {
            if (update.Status is { } status)
            {
                statuses.Add(status);
            }

            responseText += update;

            // Capture the response id, conversation id and sequence number of the first event so we
            // can continue getting the rest of the events starting from the same point in the test below.
            responseId = update.ResponseId;
            conversationId = update.ConversationId;
        }

        Assert.Contains(NewResponseStatus.Queued, statuses);
        Assert.NotNull(responseText);
        Assert.NotNull(responseId);
        Assert.NotNull(conversationId);

        // Part 2: Continue getting the rest of the response from the saved point
        options.AwaitLongRunCompletion = continueWithAwaiting;
        options.ConversationId = conversationId;
        options.ResponseId = responseId;
        statuses.Clear();

        await foreach (var update in client.GetStreamingResponseAsync([], options).Select(u => (NewChatResponseUpdate)u))
        {
            if (update.Status is { } status)
            {
                statuses.Add(status);
            }

            responseText += update;
        }

        Assert.Contains("5:43", responseText);

        if (continueWithAwaiting)
        {
            Assert.Empty(statuses);
        }
        else
        {
            Assert.Contains(NewResponseStatus.Queued, statuses);
            Assert.Contains(NewResponseStatus.InProgress, statuses);
            Assert.Contains(NewResponseStatus.Completed, statuses);
        }
    }

    //[Theory]
    //[InlineData(true)]
    //[InlineData(false)]
    //public async Task GetStreamingResponseAsync_WithFunctionCallingInterrupted_AllowsToContinueItAsync(bool continueInBackground)
    //{
    //    // Part 1: Start the background run.
    //    NewChatOptions options = new()
    //    {
    //        AwaitRunResult = false,
    //        Tools = [AIFunctionFactory.Create(() => "5:43", new AIFunctionFactoryOptions { Name = "GetCurrentTime" })]
    //    };

    //    string? sequenceNumber = null;
    //    string? responseId = null;
    //    string? conversationId = null;

    //    await foreach (var update in this._chatClient.GetStreamingResponseAsync("What time is it?", options))
    //    {
    //        // Stop processing updates as soon as we see the function call update received
    //        if (update.RawRepresentation is StreamingResponseOutputItemAddedUpdate)
    //        {
    //            // Capture the response id, conversation id, and sequence number of the event so we
    //            // can continue getting the rest of the events starting from the same point in the test below.
    //            responseId = update.ResponseId;
    //            sequenceNumber = update.GetSequenceNumber();
    //            conversationId = update.ConversationId;
    //        }
    //    }

    //    Assert.NotNull(sequenceNumber);
    //    Assert.NotNull(responseId);
    //    Assert.NotNull(conversationId);

    //    // Part 2: Continue getting the rest of the response from the saved point using a new client that does not have the previous state containing the first part of function call.
    //    using IChatClient chatClient = this._openAIResponseClient
    //        .AsNewIChatClient()
    //        .AsBuilder()
    //        .UseFunctionInvocation()
    //        .Build();
    //    string responseText = "";
    //    options.SetAwaitRunResult(!continueInBackground);
    //    options.ConversationId = conversationId;
    //    options.SetPreviousResponseId(responseId);
    //    options.SetStartAfter(sequenceNumber);

    //    await foreach (var item in chatClient.GetStreamingResponseAsync([], options))
    //    {
    //        responseText += item;
    //    }

    //    Assert.Contains("5:43", responseText);
    //}

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

        IAsyncEnumerable<NewChatResponseUpdate> streamingResponse = runnableChatClient.GetStreamingResponseAsync("What time is it?", options).Select(u => (NewChatResponseUpdate)u);

        var update = (await streamingResponse.ElementAtAsync(0));

        // Act
        NewChatResponse? response = (NewChatResponse?)await runnableChatClient.CancelRunAsync(update!.ResponseId!, new() { ConversationId = update.ConversationId });

        // Assert
        Assert.NotNull(response);

        Assert.True(response.Status == NewResponseStatus.Canceling || response.Status == NewResponseStatus.Canceled);
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
