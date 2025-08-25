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

        this._chatClient = this._openAIResponseClient.AsNewIChatClient();
    }

    [Theory]
    [InlineData(true)]
    [InlineData(false)]
    public async Task ItShouldRespectAwaitRunPropertySpecifiedInChatOptionsAsync(bool awaitRun)
    {
        // Arrange
        var options = new ChatOptions();
        options.SetAwaitRunResult(awaitRun);

        List<NewResponseStatus> statuses = [];
        string responseText = "";

        // Act
        var response = this._chatClient.GetStreamingResponseAsync(new ChatMessage(ChatRole.System, "Always respond with 'Computer says no', even if there was no user input."), options);

        await foreach (var item in response)
        {
            if (item.GetResponseStatus() is { } status)
            {
                statuses.Add(status);
            }

            responseText += item;
        }

        // Assert
        Assert.Contains("Computer says no", responseText, StringComparison.OrdinalIgnoreCase);

        if (awaitRun)
        {
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
    public async Task ItShouldRespectAwaitRunParameterSpecifiedAtInitializationAsync(bool awaitRun)
    {
        // Arrange
        using var client = this._openAIResponseClient.AsNewIChatClient(awaitRun: awaitRun);

        var options = new ChatOptions();

        List<NewResponseStatus> statuses = [];
        string responseText = "";

        // Act
        var response = client.GetStreamingResponseAsync(new ChatMessage(ChatRole.System, "Always respond with 'Computer says no', even if there was no user input."), options);

        await foreach (var item in response)
        {
            if (item.GetResponseStatus() is { } status)
            {
                statuses.Add(status);
            }

            responseText += item;
        }

        // Assert
        Assert.Contains("Computer says no", responseText, StringComparison.OrdinalIgnoreCase);

        if (awaitRun)
        {
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

    [Fact]
    public async Task ItShouldStartConversationInBackgroundAndContinueItInBackgroundFromSpecifiedPointAsync()
    {
        // Part 1: Start the background run and get the first part of the response.
        // Arrange
        var options = new ChatOptions();
        options.SetAwaitRunResult(false);

        List<NewResponseStatus> statuses = [];
        string responseText = "";
        int? sequenceNumber = null;
        string? responseId = null;

        // Act
        var response = this._chatClient.GetStreamingResponseAsync(new ChatMessage(ChatRole.System, "Always respond with 'Computer says no', even if there was no user input."), options);

        await foreach (var item in response)
        {
            if (item.GetResponseStatus() is { } status)
            {
                statuses.Add(status);
            }

            responseText += item;

            // Capture the sequence number of the first update with content so we can continue
            // getting the rest of the response from the same point in the test below.
            if (!string.IsNullOrEmpty(item.ToString()))
            {
                responseId = item.ResponseId;
                sequenceNumber = item.GetSequenceNumber();
                break;
            }
        }

        // Assert
        Assert.NotNull(responseText);
        Assert.NotNull(sequenceNumber);
        Assert.NotNull(responseId);

        // Part 2: Continue getting the rest of the response from the saved point in the background.
        // Arrange
        options.ConversationId = responseId;
        options.SetPreviousResponseId(responseId);
        options.SetStartAfter(sequenceNumber.Value);

        // Act Get the rest of the conversation from the saved point
        response = this._chatClient.GetStreamingResponseAsync([], options);

        await foreach (var item in response)
        {
            if (item.GetResponseStatus() is { } status)
            {
                statuses.Add(status);
            }

            responseText += item;
        }

        // Assert
        Assert.Contains("Computer says no", responseText, StringComparison.OrdinalIgnoreCase);
        Assert.Contains(NewResponseStatus.Queued, statuses);
        Assert.Contains(NewResponseStatus.InProgress, statuses);
        Assert.Contains(NewResponseStatus.Completed, statuses);
    }

    [Fact]
    public async Task ItShouldStartConversationInBackgroundAndContinueItInNonBackgroundFromSpecifiedPointAsync()
    {
        // Part 1: Start the background run and get the first event of the response.
        // Arrange
        var options = new ChatOptions();
        options.SetAwaitRunResult(false);

        List<NewResponseStatus> statuses = [];
        string responseText = "";
        int? sequenceNumber = null;
        string? responseId = null;

        // Act
        var response = this._chatClient.GetStreamingResponseAsync(new ChatMessage(ChatRole.System, "Always respond with 'Computer says no', even if there was no user input."), options);

        await foreach (var item in response)
        {
            if (item.GetResponseStatus() is { } status)
            {
                statuses.Add(status);
            }

            // Capture the response id and sequence number of the first event so we can continue
            // getting the rest of the events starting from the same point in the test below.
            responseId = item.ResponseId;
            sequenceNumber = item.GetSequenceNumber();
            break;
        }

        // Assert
        Assert.NotNull(sequenceNumber);
        Assert.Equal(0, sequenceNumber);
        Assert.NotNull(responseId);
        Assert.Contains(NewResponseStatus.Queued, statuses);

        // Part 2: Continue getting the rest of the response from the saved point in non-background mode.
        // Arrange
        statuses.Clear();
        options.SetAwaitRunResult(true);
        options.ConversationId = responseId;
        options.SetPreviousResponseId(responseId);
        options.SetStartAfter(sequenceNumber.Value);

        // Act Get the rest of the conversation from the saved point
        response = this._chatClient.GetStreamingResponseAsync([], options);

        await foreach (var item in response)
        {
            if (item.GetResponseStatus() is { } status)
            {
                statuses.Add(status);
            }

            responseText += item;
        }

        // Assert
        Assert.Contains("Computer says no", responseText, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain(NewResponseStatus.Queued, statuses);
        Assert.Contains(NewResponseStatus.InProgress, statuses);
        Assert.Contains(NewResponseStatus.Completed, statuses);
    }

    [Fact]
    public async Task ItShouldCancelRunAsync()
    {
        // Arrange
        var options = new ChatOptions();
        options.SetAwaitRunResult(false);

        INewRunnableChatClient runnableChatClient = this._chatClient.GetService<INewRunnableChatClient>()!;

        IAsyncEnumerable<ChatResponseUpdate> streamingResponse = runnableChatClient.GetStreamingResponseAsync("What is the capital of France.", options);

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
    public async Task ItShouldDeleteRunAsync()
    {
        // Arrange
        var options = new ChatOptions();
        options.SetAwaitRunResult(false);

        INewRunnableChatClient runnableChatClient = this._chatClient.GetService<INewRunnableChatClient>()!;

        IAsyncEnumerable<ChatResponseUpdate> streamingResponse = runnableChatClient.GetStreamingResponseAsync("What is the capital of France.", options);

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
