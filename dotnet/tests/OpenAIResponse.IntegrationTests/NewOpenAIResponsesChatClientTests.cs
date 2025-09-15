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

#pragma warning disable CA1859 // Use concrete types when possible for improved performance
    private readonly IChatClient _chatClient;
#pragma warning restore CA1859 // Use concrete types when possible for improved performance

    public NewOpenAIResponsesChatClientTests()
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
    public async Task GetResponseAsync_WithLongRunningResponsesEnabledViaOptions_ReturnsExpectedResponseAsync(bool enableLongRunningResponses)
    {
        // Arrange
        NewChatOptions options = new()
        {
            AllowLongRunningResponses = enableLongRunningResponses
        };

        // Act
        NewChatResponse response = (NewChatResponse)await this._chatClient.GetResponseAsync("What is the capital of France?", options);

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

    [Theory]
    [InlineData(true)]
    [InlineData(false)]
    public async Task GetResponseAsync_WithLongRunningResponsesEnabledAtInitialization_ReturnsExpectedResponseAsync(bool enableLongRunningResponses)
    {
        // Arrange
        using IChatClient client = this._openAIResponseClient
            .AsNewIChatClient(enableLongRunningResponses: enableLongRunningResponses)
            .AsBuilder()
            .UseFunctionInvocation()
            .Build();

        // Act
        NewChatResponse response = (NewChatResponse)await client.GetResponseAsync("What is the capital of France?");

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
        NewChatOptions options = new()
        {
            AllowLongRunningResponses = true
        };

        NewChatResponse response = (NewChatResponse)await this._chatClient.GetResponseAsync("What is the capital of France?", options);

        Assert.NotNull(response.ContinuationToken);

        // Part 2: Poll for completion.
        int attempts = 0;

        while (response.ContinuationToken is { } token && ++attempts < 5)
        {
            options.ContinuationToken = token;

            response = (NewChatResponse)await this._chatClient.GetResponseAsync([], options);

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
        NewChatOptions options = new()
        {
            AllowLongRunningResponses = false,
            Tools = [AIFunctionFactory.Create(() => "5:43", new AIFunctionFactoryOptions { Name = "GetCurrentTime" })]
        };

        // Act
        NewChatResponse response = (NewChatResponse)await this._chatClient.GetResponseAsync("What time is it?", options);

        // Assert
        Assert.Contains("5:43", response.Text);
        Assert.Null(response.ContinuationToken);
    }

    [Fact]
    public async Task GetResponseAsync_WithFunctionCalling_HavingReturnedInitialResponse_AllowsCallerPollAsync()
    {
        // Part 1: Start the background run.
        NewChatOptions options = new()
        {
            AllowLongRunningResponses = true,
            Tools = [AIFunctionFactory.Create(() => "5:43", new AIFunctionFactoryOptions { Name = "GetCurrentTime" })]
        };

        NewChatResponse response = (NewChatResponse)await this._chatClient.GetResponseAsync("What time is it?", options);

        Assert.NotNull(response.ContinuationToken);

        // Part 2: Poll for completion.
        int attempts = 0;

        while (response.ContinuationToken is { } token && ++attempts < 5)
        {
            options.ContinuationToken = token;

            response = (NewChatResponse)await this._chatClient.GetResponseAsync([], options);

            // Wait for the response to be processed
            await Task.Delay(2000);
        }

        Assert.Contains("5:43", response.Text);
        Assert.Null(response.ContinuationToken);
    }

    [Fact]
    public async Task CancelRunAsync_WhenCalled_CancelsRunAsync()
    {
        // Arrange
        NewChatOptions options = new()
        {
            AllowLongRunningResponses = true
        };

        NewChatResponse response = (NewChatResponse)await this._chatClient.GetResponseAsync("What is the capital of France?", options);

        ICancelableChatClient cancelableChatClient = this._chatClient.GetService<ICancelableChatClient>()!;

        // Act
        NewChatResponse? cancelResponse = (NewChatResponse?)await cancelableChatClient.CancelResponseAsync(response.ResponseId!);

        // Assert
        Assert.NotNull(cancelResponse);
    }

    public void Dispose()
    {
        this._chatClient?.Dispose();
    }
}
