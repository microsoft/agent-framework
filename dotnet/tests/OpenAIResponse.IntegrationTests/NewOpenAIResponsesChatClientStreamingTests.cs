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

    private readonly IChatClient _chatClient;

    public NewOpenAIResponsesChatClientStreamingTests()
    {
        this._openAIResponseClient = new OpenAIClient(s_config.ApiKey).GetOpenAIResponseClient(s_config.ChatModelId);

        this._chatClient = this._openAIResponseClient
            .AsNewIChatClient()
            .AsBuilder()
            .UseFunctionInvocation()
            .Build();
    }

    [Theory]
    [InlineData(true)]
    [InlineData(false)]
    public async Task GetStreamingResponseAsync_WithBackgroundModeProvidedViaOptions_ReturnsExpectedResponseAsync(bool awaitRun)
    {
        // Arrange
        ChatOptions options = new();
        options.SetAwaitRunResult(awaitRun);

        List<NewResponseStatus> statuses = [];
        string responseText = "";

        // Act
        await foreach (var update in this._chatClient.GetStreamingResponseAsync("What is the capital of France?", options))
        {
            if (update.GetResponseStatus() is { } status)
            {
                statuses.Add(status);
            }

            responseText += update;
        }

        // Assert
        Assert.Contains("Paris", responseText, StringComparison.OrdinalIgnoreCase);

        if (awaitRun)
        {
            Assert.DoesNotContain(NewResponseStatus.Queued, statuses);
            Assert.Contains(NewResponseStatus.InProgress, statuses);
            Assert.Contains(NewResponseStatus.Completed, statuses);
        }
        else
        {
            Assert.Contains(NewResponseStatus.Queued, statuses);
            Assert.Contains(NewResponseStatus.InProgress, statuses);
            Assert.Contains(NewResponseStatus.Completed, statuses);
        }
    }

    [Theory]
    [InlineData(true)]
    [InlineData(false)]
    public async Task GetStreamingResponseAsync_WithBackgroundModeProvidedAtInitialization_ReturnsExpectedResponseAsync(bool awaitRun)
    {
        // Arrange
        using IChatClient client = this._openAIResponseClient
            .AsNewIChatClient(awaitRun: awaitRun)
            .AsBuilder()
            .UseFunctionInvocation()
            .Build();

        List<NewResponseStatus> statuses = [];
        string responseText = "";

        // Act
        await foreach (var update in client.GetStreamingResponseAsync("What is the capital of France?"))
        {
            if (update.GetResponseStatus() is { } status)
            {
                statuses.Add(status);
            }

            responseText += update;
        }

        // Assert
        Assert.Contains("Paris", responseText, StringComparison.OrdinalIgnoreCase);

        if (awaitRun)
        {
            Assert.DoesNotContain(NewResponseStatus.Queued, statuses);
            Assert.Contains(NewResponseStatus.InProgress, statuses);
            Assert.Contains(NewResponseStatus.Completed, statuses);
        }
        else
        {
            Assert.Contains(NewResponseStatus.Queued, statuses);
            Assert.Contains(NewResponseStatus.InProgress, statuses);
            Assert.Contains(NewResponseStatus.Completed, statuses);
        }
    }

    [Theory]
    [InlineData(true)]
    [InlineData(false)]
    public async Task GetStreamingResponseAsync_HavingReturnedInitialResponse_AllowsToContinueItAsync(bool continueInBackground)
    {
        // Part 1: Start the background run and get the first part of the response.
        ChatOptions options = new();
        options.SetAwaitRunResult(false);

        List<NewResponseStatus> statuses = [];
        string responseText = "";
        string? sequenceNumber = null;
        string? responseId = null;
        string? conversationId = null;

        await foreach (var update in this._chatClient.GetStreamingResponseAsync("What is the capital of France?", options))
        {
            if (update.GetResponseStatus() is { } status)
            {
                statuses.Add(status);
            }

            responseText += update;

            // Capture the response id, conversation id and sequence number of the first event so we
            // can continue getting the rest of the events starting from the same point in the test below.
            responseId = update.ResponseId;
            conversationId = update.ConversationId;
            sequenceNumber = update.GetSequenceNumber();
            break;
        }

        Assert.Contains(NewResponseStatus.Queued, statuses);
        Assert.NotNull(responseText);
        Assert.NotNull(sequenceNumber);
        Assert.NotNull(responseId);
        Assert.NotNull(conversationId);

        // Part 2: Continue getting the rest of the response from the saved point
        options.SetAwaitRunResult(!continueInBackground);
        options.ConversationId = conversationId;
        options.SetPreviousResponseId(responseId);
        options.SetStartAfter(sequenceNumber);
        statuses.Clear();

        await foreach (var item in this._chatClient.GetStreamingResponseAsync([], options))
        {
            if (item.GetResponseStatus() is { } status)
            {
                statuses.Add(status);
            }

            responseText += item;
        }

        Assert.Contains("Paris", responseText);

        if (continueInBackground)
        {
            Assert.Contains(NewResponseStatus.Queued, statuses);
            Assert.Contains(NewResponseStatus.InProgress, statuses);
            Assert.Contains(NewResponseStatus.Completed, statuses);
        }
        else
        {
            Assert.DoesNotContain(NewResponseStatus.Queued, statuses);
            Assert.Contains(NewResponseStatus.InProgress, statuses);
            Assert.Contains(NewResponseStatus.Completed, statuses);
        }
    }

    [Fact]
    public async Task GetStreamingResponseAsync_WithFunctionCalling_AndBackgroundModeDisabled_CallsFunctionAsync()
    {
        // Arrange
        ChatOptions options = new();
        options.SetAwaitRunResult(true);
        options.Tools = [AIFunctionFactory.Create(() => "5:43", new AIFunctionFactoryOptions { Name = "GetCurrentTime" })];

        List<NewResponseStatus> statuses = [];
        string responseText = "";

        // Act
        await foreach (var item in this._chatClient.GetStreamingResponseAsync("What time is it?", options))
        {
            if (item.GetResponseStatus() is { } status)
            {
                statuses.Add(status);
            }

            responseText += item;
        }

        // Assert
        Assert.Contains("5:43", responseText);
        Assert.Contains(NewResponseStatus.InProgress, statuses);
        Assert.Contains(NewResponseStatus.Completed, statuses);
    }

    [Theory]
    [InlineData(true)]
    [InlineData(false)]
    public async Task GetStreamingResponseAsync_WithFunctionCalling_HavingReturnedInitialResponse_AllowsToContinueItAsync(bool continueInBackground)
    {
        // Part 1: Start the background run.
        ChatOptions options = new();
        options.SetAwaitRunResult(false);
        options.Tools = [AIFunctionFactory.Create(() => "5:43", new AIFunctionFactoryOptions { Name = "GetCurrentTime" })];

        List<NewResponseStatus> statuses = [];
        string responseText = "";
        string? sequenceNumber = null;
        string? responseId = null;
        string? conversationId = null;

        await foreach (var update in this._chatClient.GetStreamingResponseAsync("What time is it?", options))
        {
            if (update.GetResponseStatus() is { } status)
            {
                statuses.Add(status);
            }

            responseText += update;

            // Capture the response id, conversation id and sequence number of the first event so we
            // can continue getting the rest of the events starting from the same point in the test below.
            responseId = update.ResponseId;
            conversationId = update.ConversationId;
            sequenceNumber = update.GetSequenceNumber();
            break;
        }

        Assert.Contains(NewResponseStatus.Queued, statuses);
        Assert.NotNull(responseText);
        Assert.NotNull(sequenceNumber);
        Assert.NotNull(responseId);
        Assert.NotNull(conversationId);

        // Part 2: Continue getting the rest of the response from the saved point
        options.SetAwaitRunResult(!continueInBackground);
        options.ConversationId = conversationId;
        options.SetPreviousResponseId(responseId);
        options.SetStartAfter(sequenceNumber);
        statuses.Clear();

        await foreach (var item in this._chatClient.GetStreamingResponseAsync([], options))
        {
            if (item.GetResponseStatus() is { } status)
            {
                statuses.Add(status);
            }

            responseText += item;
        }

        Assert.Contains("5:43", responseText);

        if (continueInBackground)
        {
            Assert.Contains(NewResponseStatus.Queued, statuses);
            Assert.Contains(NewResponseStatus.InProgress, statuses);
            Assert.Contains(NewResponseStatus.Completed, statuses);
        }
        else
        {
            Assert.DoesNotContain(NewResponseStatus.Queued, statuses);
            Assert.Contains(NewResponseStatus.InProgress, statuses);
            Assert.Contains(NewResponseStatus.Completed, statuses);
        }
    }

    [Theory]
    [InlineData(true)]
    [InlineData(false)]
    public async Task GetStreamingResponseAsync_WithFunctionCallingInterrupted_AllowsToContinueItAsync(bool continueInBackground)
    {
        // Part 1: Start the background run.
        ChatOptions options = new();
        options.SetAwaitRunResult(false);
        options.Tools = [AIFunctionFactory.Create(() => "5:43", new AIFunctionFactoryOptions { Name = "GetCurrentTime" })];

        string? sequenceNumber = null;
        string? responseId = null;
        string? conversationId = null;

        await foreach (var update in this._chatClient.GetStreamingResponseAsync("What time is it?", options))
        {
            // Stop processing updates as soon as we see the function call update received
            if (update.RawRepresentation is StreamingResponseOutputItemAddedUpdate)
            {
                // Capture the response id, conversation id, and sequence number of the event so we
                // can continue getting the rest of the events starting from the same point in the test below.
                responseId = update.ResponseId;
                sequenceNumber = update.GetSequenceNumber();
                conversationId = update.ConversationId;
                break;
            }
        }

        Assert.NotNull(sequenceNumber);
        Assert.NotNull(responseId);
        Assert.NotNull(conversationId);

        // Part 2: Continue getting the rest of the response from the saved point using a new client that does not have the previous state containing the first part of function call.
        using IChatClient chatClient = this._openAIResponseClient
            .AsNewIChatClient()
            .AsBuilder()
            .UseFunctionInvocation()
            .Build();
        string responseText = "";
        options.SetAwaitRunResult(!continueInBackground);
        options.ConversationId = conversationId;
        options.SetPreviousResponseId(responseId);
        options.SetStartAfter(sequenceNumber);

        await foreach (var item in chatClient.GetStreamingResponseAsync([], options))
        {
            responseText += item;
        }

        Assert.Contains("5:43", responseText);
    }

    [Fact]
    public async Task CancelRunAsync_WhenCalled_CancelsRunAsync()
    {
        // Arrange
        ChatOptions options = new();
        options.SetAwaitRunResult(false);

        INewRunnableChatClient runnableChatClient = this._chatClient.GetService<INewRunnableChatClient>()!;

        IAsyncEnumerable<ChatResponseUpdate> streamingResponse = runnableChatClient.GetStreamingResponseAsync("What is the capital of France?", options);

        var responseId = (await streamingResponse.ElementAtAsync(0)).ResponseId;

        // Act
        ChatResponse response = await runnableChatClient.CancelRunAsync(responseId!);

        // Assert
        Assert.NotNull(response);
        Assert.Empty(response.Messages);
        Assert.NotNull(response.ResponseId);
        Assert.Equal(NewResponseStatus.Canceled, response.GetResponseStatus());
    }

    [Fact]
    public async Task DeleteRunAsync_WhenCalled_DeletesRunAsync()
    {
        // Arrange
        var options = new ChatOptions();
        options.SetAwaitRunResult(false);

        INewRunnableChatClient runnableChatClient = this._chatClient.GetService<INewRunnableChatClient>()!;

        IAsyncEnumerable<ChatResponseUpdate> streamingResponse = runnableChatClient.GetStreamingResponseAsync("What is the capital of France?", options);

        var responseId = (await streamingResponse.ElementAtAsync(0)).ResponseId;

        // Act
        ChatResponse response = await runnableChatClient.DeleteRunAsync(responseId!);

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
