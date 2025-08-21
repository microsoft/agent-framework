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

        // Act
        var response = await this._chatClient.GetResponseAsync("What is the capital of France.", options);

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
    public async Task ItShouldRespectAwaitRunParameterSpecifiedAtInitializationAsync(bool awaitRun)
    {
        // Arrange
        using var client = this._openAIResponseClient.AsNewIChatClient(awaitRun: awaitRun);

        var options = new ChatOptions();

        // Act
        var response = await client.GetResponseAsync("What is the capital of France.", options);

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
    public async Task ItShouldReturnRunStatusAndResultByIdAsync()
    {
        // Arrange
        var options = new ChatOptions();
        options.SetAwaitRunResult(false);

        // Act
        var response = await this._chatClient.GetResponseAsync("What is the capital of France.", options);

        // Assert
        Assert.NotNull(response);
        Assert.Empty(response.Messages);
        Assert.NotNull(response.ResponseId);
        Assert.Equal(NewResponseStatus.Queued, response.GetResponseStatus());

        // Now, retrieve the response by ID
        options.ConversationId = response.ResponseId;

        int attempts = 0;

        while (response.GetResponseStatus() != NewResponseStatus.Completed && ++attempts < 5)
        {
            response = await this._chatClient.GetResponseAsync([], options);

            if (response.GetResponseStatus() != NewResponseStatus.Completed)
            {
                // Wait for the response to be processed
                await Task.Delay(2000);
            }
        }

        // Assert
        Assert.NotNull(response);
        Assert.Single(response.Messages);
        Assert.Contains("Paris", response.Text);
        Assert.NotNull(response.ResponseId);
        Assert.Equal(NewResponseStatus.Completed, response.GetResponseStatus());
    }

    [Fact]
    public async Task ItShouldCancelRunAsync()
    {
        // Arrange
        var options = new ChatOptions();
        options.SetAwaitRunResult(false);

        INewRunnableChatClient runnableChatClient = this._chatClient.GetService<INewRunnableChatClient>()!;

        var response = await runnableChatClient.GetResponseAsync("What is the capital of France.", options);

        // Act
        response = await runnableChatClient.CancelRunAsync(response.ResponseId!);

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

        var response = await runnableChatClient.GetResponseAsync("What is the capital of France.", options);

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
