// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using AgentConformance.IntegrationTests.Support;
using Microsoft.Extensions.AI;
using OpenAI;
using OpenAI.Responses;
using Shared.IntegrationTests;

namespace OpenAIResponse.IntegrationTests;

public sealed class NewOpenAIResponsesChatClientStreamingTests : IDisposable
{
    private static readonly OpenAIConfiguration s_config = TestConfiguration.LoadSection<OpenAIConfiguration>();

    private readonly OpenAIResponseClient _openAIResponseClient;

#pragma warning disable CA1859 // Use concrete types when possible for improved performance
    private readonly IChatClient _chatClient;
#pragma warning restore CA1859 // Use concrete types when possible for improved performance

    public NewOpenAIResponsesChatClientStreamingTests()
    {
        this._openAIResponseClient = new OpenAIClient(s_config.ApiKey).GetOpenAIResponseClient(s_config.ChatModelId);

        this._chatClient = new NewFunctionInvokingChatClient(this._openAIResponseClient.AsNewIChatClient());

        //this._chatClient = this._openAIResponseClient
        //    .AsNewIChatClient()
        //    .AsBuilder()
        //    .UseFunctionInvocation()
        //    .Build();
    }

    [Theory]
    [InlineData(true)]
    [InlineData(false)]
    public async Task GetStreamingResponseAsync_WithAwaitModeProvidedViaOptions_ReturnsExpectedResponseAsync(bool awaitRunCompletion)
    {
        // Arrange
        NewChatOptions options = new()
        {
            AwaitLongRunCompletion = awaitRunCompletion
        };

        List<NewResponseStatus> statuses = [];
        string responseText = "";

        // Act
        await foreach (var update in this._chatClient.GetStreamingResponseAsync("What is the capital of France?", options).Select(u => (NewChatResponseUpdate)u))
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
            Assert.DoesNotContain(NewResponseStatus.Queued, statuses);
            Assert.Contains(NewResponseStatus.InProgress, statuses);
            Assert.Contains(NewResponseStatus.Completed, statuses);
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
        using IChatClient client = this._openAIResponseClient
            .AsNewIChatClient(awaitRunCompletion: awaitRunCompletion)
            .AsBuilder()
            .UseFunctionInvocation()
            .Build();

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
            Assert.DoesNotContain(NewResponseStatus.Queued, statuses);
            Assert.Contains(NewResponseStatus.InProgress, statuses);
            Assert.Contains(NewResponseStatus.Completed, statuses);
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
        NewChatOptions options = new()
        {
            AwaitLongRunCompletion = false
        };

        List<NewResponseStatus> statuses = [];
        string responseText = "";
        string? sequenceNumber = null;
        string? responseId = null;
        string? conversationId = null;

        await foreach (var update in this._chatClient.GetStreamingResponseAsync("What is the capital of France?", options).Select(u => (NewChatResponseUpdate)u))
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
            sequenceNumber = update.SequenceNumber;
        }

        Assert.Contains(NewResponseStatus.Queued, statuses);
        Assert.NotNull(responseText);
        Assert.NotNull(sequenceNumber);
        Assert.NotNull(responseId);
        Assert.NotNull(conversationId);

        // Part 2: Continue getting the rest of the response from the saved point
        options.AwaitLongRunCompletion = continueWithAwaiting;
        options.ConversationId = conversationId;
        options.ResponseId = responseId;
        options.StartAfter = sequenceNumber;
        statuses.Clear();

        await foreach (var update in this._chatClient.GetStreamingResponseAsync([], options).Select(u => (NewChatResponseUpdate)u))
        {
            if (update.Status is { } status)
            {
                statuses.Add(status);
            }

            responseText += update;
        }

        Assert.Contains("Paris", responseText);

        Assert.DoesNotContain(NewResponseStatus.Queued, statuses);
        Assert.Contains(NewResponseStatus.InProgress, statuses);
        Assert.Contains(NewResponseStatus.Completed, statuses);
    }

    [Fact]
    public async Task GetStreamingResponseAsync_WithFunctionCalling_AndAwaitModeEnabled_CallsFunctionAsync()
    {
        // Arrange
        NewChatOptions options = new()
        {
            AwaitLongRunCompletion = true,
            Tools = [AIFunctionFactory.Create(() => "5:43", new AIFunctionFactoryOptions { Name = "GetCurrentTime" })]
        };

        List<NewResponseStatus> statuses = [];
        string responseText = "";

        // Act
        await foreach (var update in this._chatClient.GetStreamingResponseAsync("What time is it?", options).Select(u => (NewChatResponseUpdate)u))
        {
            if (update.Status is { } status)
            {
                statuses.Add(status);
            }

            responseText += update;
        }

        // Assert
        Assert.Contains("5:43", responseText);
        Assert.Contains(NewResponseStatus.InProgress, statuses);
        Assert.Contains(NewResponseStatus.Completed, statuses);
    }

    [Theory]
    [InlineData(true)]
    [InlineData(false)]
    public async Task GetStreamingResponseAsync_WithFunctionCalling_HavingReturnedInitialResponse_AllowsToContinueItAsync(bool continueWithAwaiting)
    {
        // Part 1: Start the background run.
        NewChatOptions options = new()
        {
            AwaitLongRunCompletion = false,
            Tools = [AIFunctionFactory.Create(() => "5:43", new AIFunctionFactoryOptions { Name = "GetCurrentTime" })]
        };

        List<NewResponseStatus> statuses = [];
        string responseText = "";
        string? sequenceNumber = null;
        string? responseId = null;
        string? conversationId = null;

        await foreach (var update in this._chatClient.GetStreamingResponseAsync("What time is it?", options).Select(u => (NewChatResponseUpdate)u))
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
            sequenceNumber = update.SequenceNumber;
        }

        Assert.Contains(NewResponseStatus.Queued, statuses);
        Assert.NotNull(responseText);
        Assert.NotNull(sequenceNumber);
        Assert.NotNull(responseId);
        Assert.NotNull(conversationId);

        // Part 2: Continue getting the rest of the response from the saved point
        options.AwaitLongRunCompletion = continueWithAwaiting;
        options.ConversationId = conversationId;
        options.ResponseId = responseId;
        options.StartAfter = sequenceNumber;
        statuses.Clear();

        await foreach (var update in this._chatClient.GetStreamingResponseAsync([], options).Select(u => (NewChatResponseUpdate)u))
        {
            if (update.Status is { } status)
            {
                statuses.Add(status);
            }

            responseText += update;
        }

        Assert.Contains("5:43", responseText);

        Assert.Contains(NewResponseStatus.InProgress, statuses);
        Assert.Contains(NewResponseStatus.Completed, statuses);
    }

    //[Theory]
    //[InlineData(true)]
    //[InlineData(false)]
    //public async Task GetStreamingResponseAsync_WithFunctionCallingInterrupted_AllowsToContinueItAsync(bool continueInBackground)
    //{
    //    // Part 1: Start the background run.
    //    NewChatOptions options = new();
    //    options.SetAwaitRunResult(false);
    //    options.Tools = [AIFunctionFactory.Create(() => "5:43", new AIFunctionFactoryOptions { Name = "GetCurrentTime" })];

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
        NewChatOptions options = new()
        {
            AwaitLongRunCompletion = false
        };

        ILongRunningChatClient runnableChatClient = this._chatClient.GetService<ILongRunningChatClient>()!;

        IAsyncEnumerable<NewChatResponseUpdate> streamingResponse = runnableChatClient.GetStreamingResponseAsync("What is the capital of France?", options).Select(u => (NewChatResponseUpdate)u);

        var update = (await streamingResponse.ElementAtAsync(0));

        // Act
        NewChatResponse? response = (NewChatResponse?)await runnableChatClient.CancelRunAsync(update.ResponseId!);

        // Assert
        Assert.NotNull(response);
        Assert.Empty(response.Messages);
        Assert.NotNull(response.ResponseId);
        Assert.Equal(NewResponseStatus.Canceled, response.Status);
    }

    [Fact]
    public async Task DeleteRunAsync_WhenCalled_DeletesRunAsync()
    {
        // Arrange
        NewChatOptions options = new()
        {
            AwaitLongRunCompletion = false
        };

        ILongRunningChatClient runnableChatClient = this._chatClient.GetService<ILongRunningChatClient>()!;

        IAsyncEnumerable<NewChatResponseUpdate> streamingResponse = runnableChatClient.GetStreamingResponseAsync("What is the capital of France?", options).Select(u => (NewChatResponseUpdate)u);

        var update = (await streamingResponse.ElementAtAsync(0));

        // Act
        ChatResponse? response = await runnableChatClient.DeleteRunAsync(update.ResponseId!);

        // Assert
        Assert.NotNull(response);
        Assert.Empty(response.Messages);
        Assert.NotNull(response.ResponseId);
        Assert.True(((ResponseDeletionResult)response.RawRepresentation!).Deleted);
    }

    public void Dispose()
    {
        this._chatClient?.Dispose();
    }
}
