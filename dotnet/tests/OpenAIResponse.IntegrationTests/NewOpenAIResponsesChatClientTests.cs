// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading.Tasks;
using AgentConformance.IntegrationTests.Support;
using Microsoft.Extensions.AI;
using OpenAI;
using OpenAI.Responses;
using Shared.IntegrationTests;

namespace OpenAIResponse.IntegrationTests;

public sealed class NewOpenAIResponsesChatClientTests : IDisposable
{
    private static readonly OpenAIConfiguration s_config = TestConfiguration.LoadSection<OpenAIConfiguration>();

    private readonly OpenAIResponseClient _openAIResponseClient;

    private readonly IChatClient _chatClient;

    public NewOpenAIResponsesChatClientTests()
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
    public async Task GetResponseAsync_WithBackgroundModeProvidedViaOptions_ReturnsExpectedResponseAsync(bool awaitRun)
    {
        // Arrange
        ChatOptions options = new();
        options.SetAwaitRunResult(awaitRun);

        // Act
        ChatResponse response = await this._chatClient.GetResponseAsync("What is the capital of France?", options);

        // Assert
        Assert.NotNull(response);

        if (awaitRun)
        {
            Assert.Single(response.Messages);
            Assert.Contains("Paris", response.Text);
        }
        else
        {
            Assert.Empty(response.Messages);
            Assert.NotNull(response.ResponseId);
            Assert.Equal(NewResponseStatus.Queued, response.GetResponseStatus());
        }
    }

    [Theory]
    [InlineData(true)]
    [InlineData(false)]
    public async Task GetResponseAsync_WithBackgroundModeProvidedAtInitialization_ReturnsExpectedResponseAsync(bool awaitRun)
    {
        // Arrange
        using IChatClient client = this._openAIResponseClient
            .AsNewIChatClient(awaitRun: awaitRun)
            .AsBuilder()
            .UseFunctionInvocation()
            .Build();

        // Act
        ChatResponse response = await client.GetResponseAsync("What is the capital of France?");

        // Assert
        Assert.NotNull(response);

        if (awaitRun)
        {
            Assert.Single(response.Messages);
            Assert.Contains("Paris", response.Text);
        }
        else
        {
            Assert.Empty(response.Messages);
            Assert.NotNull(response.ResponseId);
            Assert.Equal(NewResponseStatus.Queued, response.GetResponseStatus());
        }
    }

    [Fact]
    public async Task GetResponseAsync_HavingReturnedInitialResponse_AllowsCallerToPollAsync()
    {
        // Part 1: Start the background run.
        ChatOptions options = new();
        options.SetAwaitRunResult(false);

        ChatResponse response = await this._chatClient.GetResponseAsync("What is the capital of France?", options);

        Assert.NotNull(response);
        Assert.Empty(response.Messages);
        Assert.NotNull(response.ResponseId);
        Assert.Equal(NewResponseStatus.Queued, response.GetResponseStatus());

        // Part 2: Poll for completion.
        int attempts = 0;

        while (response.GetResponseStatus() is { } status &&
            (status == NewResponseStatus.Completed || status == NewResponseStatus.Queued) &&
            ++attempts < 5)
        {
            options.ConversationId = response.ResponseId;
            options.SetPreviousResponseId(response.ResponseId!);

            response = await this._chatClient.GetResponseAsync([], options);

            // Wait for the response to be processed
            await Task.Delay(2000);
        }

        Assert.NotNull(response);
        Assert.Single(response.Messages);
        Assert.Contains("Paris", response.Text);
        Assert.NotNull(response.ResponseId);
        Assert.Equal(NewResponseStatus.Completed, response.GetResponseStatus());
    }

    [Fact]
    public async Task GetResponseAsync_HavingReturnedInitialResponse_CanDoPollingItselfAsync()
    {
        // Part 1: Start the background run.
        ChatOptions options = new();
        options.SetAwaitRunResult(false);

        ChatResponse response = await this._chatClient.GetResponseAsync("What is the capital of France?", options);

        Assert.NotNull(response);
        Assert.Empty(response.Messages);
        Assert.NotNull(response.ResponseId);
        Assert.Equal(NewResponseStatus.Queued, response.GetResponseStatus());

        // Part 2: Wait for completion.
        options.ConversationId = response.ResponseId;
        options.SetPreviousResponseId(response.ResponseId);
        options.SetAwaitRunResult(true);

        response = await this._chatClient.GetResponseAsync([], options);

        Assert.NotNull(response);
        Assert.Single(response.Messages);
        Assert.Contains("Paris", response.Text);
        Assert.NotNull(response.ResponseId);
        Assert.Equal(NewResponseStatus.Completed, response.GetResponseStatus());
    }

    [Fact]
    public async Task GetResponseAsync_WithFunctionCalling_AndBackgroundModeDisabled_CallsFunctionAsync()
    {
        // Arrange
        ChatOptions options = new();
        options.SetAwaitRunResult(true);
        options.Tools = [AIFunctionFactory.Create(() => "5:43", new AIFunctionFactoryOptions { Name = "GetCurrentTime" })];

        // Act
        ChatResponse response = await this._chatClient.GetResponseAsync("What time is it?", options);

        // Assert
        Assert.Contains("5:43", response.Text);
    }

    [Fact]
    public async Task GetResponseAsync_WithFunctionCalling_HavingReturnedInitialResponse_AllowsCallerPollAsync()
    {
        // Part 1: Start the background run.
        ChatOptions options = new();
        options.SetAwaitRunResult(false);
        options.Tools = [AIFunctionFactory.Create(() => "5:43", new AIFunctionFactoryOptions { Name = "GetCurrentTime" })];

        ChatResponse response = await this._chatClient.GetResponseAsync("What time is it?", options);

        Assert.NotNull(response);
        Assert.Empty(response.Messages);
        Assert.NotNull(response.ResponseId);
        Assert.Equal(NewResponseStatus.Queued, response.GetResponseStatus());

        // Part 2: Poll for completion.
        int attempts = 0;

        while (response.GetResponseStatus() is { } status &&
            (status == NewResponseStatus.Completed || status == NewResponseStatus.Queued) &&
            ++attempts < 5)
        {
            options.ConversationId = response.ResponseId;
            options.SetPreviousResponseId(response.ResponseId!);

            response = await this._chatClient.GetResponseAsync([], options);

            // Wait for the response to be processed
            await Task.Delay(2000);
        }

        Assert.Contains("5:43", response.Text);
    }

    [Fact]
    public async Task GetResponseAsync_WithFunctionCalling_HavingReturnedInitialResponse_CanDoPollingItselfAsync()
    {
        // Part 1: Start the background run.
        ChatOptions options = new();
        options.SetAwaitRunResult(false);
        options.Tools = [AIFunctionFactory.Create(() => "5:43", new AIFunctionFactoryOptions { Name = "GetCurrentTime" })];

        ChatResponse response = await this._chatClient.GetResponseAsync("What time is it?", options);

        Assert.NotNull(response);
        Assert.Empty(response.Messages);
        Assert.NotNull(response.ResponseId);
        Assert.Equal(NewResponseStatus.Queued, response.GetResponseStatus());

        // Part 2: Wait for completion.
        options.ConversationId = response.ResponseId;
        options.SetPreviousResponseId(response.ResponseId);
        options.SetAwaitRunResult(true);

        response = await this._chatClient.GetResponseAsync([], options);

        Assert.NotNull(response);
        Assert.Equal(3, response.Messages.Count);
        Assert.Contains("5:43", response.Text);
        Assert.NotNull(response.ResponseId);
        Assert.Equal(NewResponseStatus.Completed, response.GetResponseStatus());
    }

    [Fact]
    public async Task CancelRunAsync_WhenCalled_CancelsRunAsync()
    {
        // Arrange
        ChatOptions options = new();
        options.SetAwaitRunResult(false);

        INewRunnableChatClient runnableChatClient = this._chatClient.GetService<INewRunnableChatClient>()!;

        ChatResponse response = await runnableChatClient.GetResponseAsync("What is the capital of France?", options);

        // Act
        response = await runnableChatClient.CancelRunAsync(response.ResponseId!);

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
        ChatOptions options = new();
        options.SetAwaitRunResult(false);

        INewRunnableChatClient runnableChatClient = this._chatClient.GetService<INewRunnableChatClient>()!;

        ChatResponse response = await runnableChatClient.GetResponseAsync("What is the capital of France?", options);

        // Act
        response = await runnableChatClient.DeleteRunAsync(response.ResponseId!);

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
