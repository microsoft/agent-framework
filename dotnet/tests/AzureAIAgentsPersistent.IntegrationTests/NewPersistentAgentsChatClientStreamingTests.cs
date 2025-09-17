// Copyright (c) Microsoft. All rights reserved.

using System;
using System.ClientModel;
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
    public async Task GetStreamingResponseAsync_WithLongRunningResponsesEnabledViaOptions_ReturnsExpectedResponseAsync(bool enableLongRunningResponses)
    {
        // Arrange
        using var client = await CreateChatClientAsync();

        NewChatOptions options = new()
        {
            AllowLongRunningResponses = enableLongRunningResponses
        };

        string responseText = "";
        ContinuationToken? firstContinuationToken = null;
        ContinuationToken? lastContinuationToken = null;

        // Act
        await foreach (var update in client.GetStreamingResponseAsync("What is the capital of France?", options).Select(u => (NewChatResponseUpdate)u))
        {
            firstContinuationToken ??= update.ContinuationToken;

            responseText += update;
            lastContinuationToken = update.ContinuationToken;
        }

        // Assert
        Assert.Contains("Paris", responseText, StringComparison.OrdinalIgnoreCase);

        if (enableLongRunningResponses)
        {
            Assert.NotNull(firstContinuationToken);
            Assert.Null(lastContinuationToken);
        }
        else
        {
            Assert.Null(firstContinuationToken);
            Assert.Null(lastContinuationToken);
        }
    }

    [Theory]
    [InlineData(true)]
    [InlineData(false)]
    public async Task GetStreamingResponseAsync_WithLongRunningResponsesEnabledAtInitialization_ReturnsExpectedResponseAsync(bool enableLongRunningResponses)
    {
        // Arrange
        using var client = await CreateChatClientAsync(enableLongRunningResponses);

        string responseText = "";
        ContinuationToken? firstContinuationToken = null;
        ContinuationToken? lastContinuationToken = null;

        // Act
        await foreach (var update in client.GetStreamingResponseAsync("What is the capital of France?").Select(u => (NewChatResponseUpdate)u))
        {
            firstContinuationToken ??= update.ContinuationToken;

            responseText += update;
            lastContinuationToken = update.ContinuationToken;
        }

        // Assert
        Assert.Contains("Paris", responseText, StringComparison.OrdinalIgnoreCase);

        if (enableLongRunningResponses)
        {
            Assert.NotNull(firstContinuationToken);
            Assert.Null(lastContinuationToken);
        }
        else
        {
            Assert.Null(firstContinuationToken);
            Assert.Null(lastContinuationToken);
        }
    }

    [Fact]
    public async Task GetStreamingResponseAsync_HavingReturnedInitialResponse_AllowsToContinueItAsync()
    {
        // Part 1: Start the background run and get the first part of the response.
        using var client = await CreateChatClientAsync();

        NewChatOptions options = new()
        {
            AllowLongRunningResponses = true
        };

        ContinuationToken? firstContinuationToken = null;
        ContinuationToken? lastContinuationToken = null;
        string responseText = "";

        await foreach (var update in client.GetStreamingResponseAsync("What is the capital of France?", options).Select(u => (NewChatResponseUpdate)u))
        {
            responseText += update;

            // Capture continuation token of the first event so we  can continue getting
            // the rest of the events starting from the same point in the test below.
            firstContinuationToken = update.ContinuationToken;

            break;
        }

        Assert.NotNull(firstContinuationToken);
        Assert.NotNull(responseText);

        // Part 2: Continue getting the rest of the response from the saved point represented by the continuation token.
        options.ContinuationToken = firstContinuationToken;
        NewChatResponseUpdate? firstContinuationUpdate = null;

        await foreach (var update in client.GetStreamingResponseAsync([], options).Select(u => (NewChatResponseUpdate)u))
        {
            firstContinuationUpdate ??= update;

            responseText += update;

            lastContinuationToken = update.ContinuationToken;
        }

        Assert.Contains("Paris", responseText);
        Assert.Null(lastContinuationToken);
        Assert.NotNull(firstContinuationUpdate?.RawRepresentation);
    }

    [Fact]
    public async Task GetStreamingResponseAsync_WithFunctionCalling_AndLongRunningResponsesDisabled_CallsFunctionAsync()
    {
        // Arrange
        using var client = await CreateChatClientAsync();

        NewChatOptions options = new()
        {
            AllowLongRunningResponses = false,
            Tools = [AIFunctionFactory.Create(() => "5:43", new AIFunctionFactoryOptions { Name = "GetCurrentTime" })]
        };

        string responseText = "";

        // Act
        await foreach (var update in client.GetStreamingResponseAsync("What time is it?", options).Select(u => (NewChatResponseUpdate)u))
        {
            responseText += update;

            Assert.Null(update.ContinuationToken);
        }

        // Assert
        Assert.Contains("5:43", responseText);
    }

    [Fact]
    public async Task GetStreamingResponseAsync_WithOneFunction_HavingReturnedInitialResponse_AllowsToContinueItAsync()
    {
        // Part 1: Start the background run.
        using var client = await CreateChatClientAsync();

        NewChatOptions options = new()
        {
            AllowLongRunningResponses = true,
            Tools = [AIFunctionFactory.Create(() => "5:43", new AIFunctionFactoryOptions { Name = "GetCurrentTime" })]
        };

        string responseText = "";
        ContinuationToken? firstContinuationToken = null;
        ContinuationToken? lastContinuationToken = null;

        await foreach (var update in client.GetStreamingResponseAsync("What time is it?", options).Select(u => (NewChatResponseUpdate)u))
        {
            responseText += update;

            // Capture continuation token of the first event so we  can continue getting
            // the rest of the events starting from the same point in the test below.
            firstContinuationToken = update.ContinuationToken;

            break;
        }

        Assert.NotNull(firstContinuationToken);
        Assert.NotNull(responseText);

        // Part 2: Continue getting the rest of the response from the saved point
        options.ContinuationToken = firstContinuationToken;

        await foreach (var update in client.GetStreamingResponseAsync([], options).Select(u => (NewChatResponseUpdate)u))
        {
            responseText += update;

            lastContinuationToken = update.ContinuationToken;
        }

        Assert.Contains("5:43", responseText);
        Assert.Null(lastContinuationToken);
    }

    [Fact]
    public async Task GetStreamingResponseAsync_WithTwoFunctions_AndLongRunningResponsesEnabled_AllowsToContinueItAsync()
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

        string responseText = "";

        await foreach (var update in client.GetStreamingResponseAsync("What's the weather in Paris right now? Include the time.", options).Select(u => (NewChatResponseUpdate)u))
        {
            responseText += update;
        }

        Assert.Contains("5:43", responseText);
        Assert.Contains("cloudy", responseText);
    }

    [Fact]
    public async Task GetStreamingResponseAsync_WithTwoFunctions_HavingReturnedInitialResponse_AllowsToContinueItAsync()
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

        string responseText = "";
        ContinuationToken? firstContinuationToken = null;
        ContinuationToken? lastContinuationToken = null;

        await foreach (var update in client.GetStreamingResponseAsync("What's the weather in Paris right now? Include the time.", options).Select(u => (NewChatResponseUpdate)u))
        {
            responseText += update;

            // Capture continuation token of the first event so we  can continue getting
            // the rest of the events starting from the same point in the test below.
            firstContinuationToken = update.ContinuationToken;

            break;
        }

        Assert.NotNull(firstContinuationToken);
        Assert.NotNull(responseText);

        // Part 2: Continue getting the rest of the response from the saved point
        options.ContinuationToken = firstContinuationToken;

        await foreach (var update in client.GetStreamingResponseAsync([], options).Select(u => (NewChatResponseUpdate)u))
        {
            responseText += update;

            lastContinuationToken = update.ContinuationToken;
        }

        Assert.Contains("5:43", responseText);
        Assert.Contains("cloud", responseText);
        Assert.Null(lastContinuationToken);
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
            AllowLongRunningResponses = true,
        };

        IAsyncEnumerable<NewChatResponseUpdate> streamingResponse = client.GetStreamingResponseAsync("What time is it?", options).Select(u => (NewChatResponseUpdate)u);

        var update = (await streamingResponse.ElementAtAsync(0));

        ICancelableChatClient cancelableChatClient = client.GetService<ICancelableChatClient>()!;

        // Act
        NewChatResponse? response = (NewChatResponse?)await cancelableChatClient.CancelResponseAsync(update!.ResponseId!, new() { ConversationId = update.ConversationId });

        // Assert
        Assert.NotNull(response);
    }

    private static async Task<IChatClient> CreateChatClientAsync(bool? enableLongRunningResponses = null)
    {
        PersistentAgentsClient persistentAgentsClient = new(s_config.Endpoint, new AzureCliCredential());

        var persistentAgentResponse = await persistentAgentsClient.Administration.CreateAgentAsync(
            model: s_config.DeploymentName,
            name: "LongRunningExecutionAgent",
            instructions: "You are a helpful assistant.");

        var persistentChatClient = persistentAgentsClient.AsNewIChatClient(persistentAgentResponse.Value.Id, enableLongRunningResponses: enableLongRunningResponses);

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
