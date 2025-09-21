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
    public async Task GetStreamingResponseAsync_WithLonRunningResponsesEnabledViaOptions_ReturnsExpectedResponseAsync(bool enableLongRunningResponses)
    {
        // Arrange
        NewChatOptions options = new()
        {
            BackgroundResponsesOptions = new BackgroundResponsesOptions
            {
                Allow = enableLongRunningResponses
            },
        };

        string responseText = "";
        string? firstContinuationToken = null;
        string? lastContinuationToken = null;

        // Act
        await foreach (var update in this._chatClient.GetStreamingResponseAsync("What is the capital of France?", options).Select(u => (NewChatResponseUpdate)u))
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
        NewChatOptions options = new()
        {
            BackgroundResponsesOptions = new BackgroundResponsesOptions
            {
                Allow = true
            },
        };

        string? firstContinuationToken = null;
        string? lastContinuationToken = null;
        string responseText = "";

        await foreach (var update in this._chatClient.GetStreamingResponseAsync("What is the capital of France?", options).Select(u => (NewChatResponseUpdate)u))
        {
            responseText += update;

            // Capture continuation token of the first event so we can continue getting
            // the rest of the events starting from the same point in the test below.
            firstContinuationToken = update.ContinuationToken;

            break;
        }

        Assert.NotNull(firstContinuationToken);
        Assert.NotNull(responseText);

        // Part 2: Continue getting the rest of the response from the saved point represented by the continuation token.
        options.ContinuationToken = firstContinuationToken;
        NewChatResponseUpdate? firstContinuationUpdate = null;

        await foreach (var update in this._chatClient.GetStreamingResponseAsync([], options).Select(u => (NewChatResponseUpdate)u))
        {
            firstContinuationUpdate ??= update;

            responseText += update;

            lastContinuationToken = update.ContinuationToken;
        }

        Assert.Contains("Paris", responseText);
        Assert.Null(lastContinuationToken);
        Assert.NotNull(firstContinuationUpdate?.RawRepresentation);
        Assert.Equal(1, ((StreamingResponseUpdate)firstContinuationUpdate.RawRepresentation).SequenceNumber);
    }

    [Fact]
    public async Task GetStreamingResponseAsync_WithFunctionCalling_AndLongRunningResponsesDisabled_CallsFunctionAsync()
    {
        // Arrange
        NewChatOptions options = new()
        {
            BackgroundResponsesOptions = new BackgroundResponsesOptions
            {
                Allow = false
            },
            Tools = [AIFunctionFactory.Create(() => "5:43", new AIFunctionFactoryOptions { Name = "GetCurrentTime" })]
        };

        string responseText = "";

        // Act
        await foreach (var update in this._chatClient.GetStreamingResponseAsync("What time is it?", options).Select(u => (NewChatResponseUpdate)u))
        {
            responseText += update;

            Assert.Null(update.ContinuationToken);
        }

        // Assert
        Assert.Contains("5:43", responseText);
    }

    [Fact]
    public async Task GetStreamingResponseAsync_WithOneFunction_AndLongRunningResponsesEnabled_AllowsToContinueItAsync()
    {
        // Part 1: Start the background run.
        NewChatOptions options = new()
        {
            BackgroundResponsesOptions = new BackgroundResponsesOptions
            {
                Allow = true
            },
            Tools = [AIFunctionFactory.Create(() => "5:43", new AIFunctionFactoryOptions { Name = "GetCurrentTime" })]
        };

        string responseText = "";

        await foreach (var update in this._chatClient.GetStreamingResponseAsync("What time is it?", options).Select(u => (NewChatResponseUpdate)u))
        {
            responseText += update;
        }

        Assert.Contains("5:43", responseText);
    }

    [Fact]
    public async Task GetStreamingResponseAsync_WithTwoFunctions_AndLongRunningResponsesEnabled_AllowsToContinueItAsync()
    {
        // Part 1: Start the background run.
        NewChatOptions options = new()
        {
            BackgroundResponsesOptions = new BackgroundResponsesOptions
            {
                Allow = true
            },
            Tools = [
                AIFunctionFactory.Create(() => new DateTime(2025, 09, 16, 05, 43,00), new AIFunctionFactoryOptions { Name = "GetCurrentTime" }),
                AIFunctionFactory.Create((DateTime time, string location) => $"It's cloudy in {location} at {time}", new AIFunctionFactoryOptions { Name = "GetWeather" })
            ]
        };

        string responseText = "";

        await foreach (var update in this._chatClient.GetStreamingResponseAsync("What's the weather in Paris right now? Include the time.", options).Select(u => (NewChatResponseUpdate)u))
        {
            responseText += update;
        }

        Assert.Contains("5:43", responseText);
        Assert.Contains("cloudy", responseText);
    }

    [Fact]
    public async Task GetStreamingResponseAsync_WithOneFunction_HavingReturnedInitialResponse_AllowsToContinueItAsync()
    {
        // Part 1: Start the background run.
        NewChatOptions options = new()
        {
            BackgroundResponsesOptions = new BackgroundResponsesOptions
            {
                Allow = true
            },
            Tools = [AIFunctionFactory.Create(() => "5:43", new AIFunctionFactoryOptions { Name = "GetCurrentTime" })]
        };

        string responseText = "";
        string? firstContinuationToken = null;
        string? lastContinuationToken = null;

        await foreach (var update in this._chatClient.GetStreamingResponseAsync("What time is it?", options).Select(u => (NewChatResponseUpdate)u))
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

        await foreach (var update in this._chatClient.GetStreamingResponseAsync([], options).Select(u => (NewChatResponseUpdate)u))
        {
            responseText += update;

            lastContinuationToken = update.ContinuationToken;
        }

        Assert.Contains("5:43", responseText);
        Assert.Null(lastContinuationToken);
    }

    [Fact]
    public async Task GetStreamingResponseAsync_WithTwoFunctions_HavingReturnedInitialResponse_AllowsToContinueItAsync()
    {
        // Part 1: Start the background run.
        NewChatOptions options = new()
        {
            BackgroundResponsesOptions = new BackgroundResponsesOptions
            {
                Allow = true
            },
            Tools = [
                AIFunctionFactory.Create(() => new DateTime(2025, 09, 16, 05, 43,00), new AIFunctionFactoryOptions { Name = "GetCurrentTime" }),
                AIFunctionFactory.Create((DateTime time, string location) => $"It's cloudy in {location} at {time}", new AIFunctionFactoryOptions { Name = "GetWeather" })
            ]
        };

        string responseText = "";
        string? firstContinuationToken = null;
        string? lastContinuationToken = null;

        await foreach (var update in this._chatClient.GetStreamingResponseAsync("What's the weather in Paris right now? Include the time.", options).Select(u => (NewChatResponseUpdate)u))
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

        await foreach (var update in this._chatClient.GetStreamingResponseAsync([], options).Select(u => (NewChatResponseUpdate)u))
        {
            responseText += update;

            lastContinuationToken = update.ContinuationToken;
        }

        Assert.Contains("5:43", responseText);
        Assert.Contains("cloudy", responseText);
        Assert.Null(lastContinuationToken);
    }

    [Fact]
    public async Task GetStreamingResponseAsync_WithFunctionCallingInterrupted_AllowsToContinueItAsync()
    {
        // Part 1: Start the background run.
        NewChatOptions options = new()
        {
            BackgroundResponsesOptions = new BackgroundResponsesOptions
            {
                Allow = true
            },
            Tools = [AIFunctionFactory.Create(() => "5:43", new AIFunctionFactoryOptions { Name = "GetCurrentTime" })]
        };

        string? continuationToken = null;

        await foreach (var update in this._chatClient.GetStreamingResponseAsync("What time is it?", options).Select(u => (NewChatResponseUpdate)u))
        {
            // Stop processing updates as soon as we see the function call update received
            if (update.RawRepresentation is StreamingResponseOutputItemAddedUpdate)
            {
                // Capture the continuation token so we can continue getting
                continuationToken = update.ContinuationToken;
                break;
            }
        }

        Assert.NotNull(continuationToken);

        // Part 2: Continue getting the rest of the response from the saved point using a new client that does not have the previous state containing the first part of function call.
        using var chatClient = new NewFunctionInvokingChatClient(this._openAIResponseClient.AsNewIChatClient());

        string responseText = "";
        options.ContinuationToken = continuationToken;

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
        NewChatOptions options = new()
        {
            BackgroundResponsesOptions = new BackgroundResponsesOptions
            {
                Allow = true
            },
        };

        IAsyncEnumerable<NewChatResponseUpdate> streamingResponse = this._chatClient.GetStreamingResponseAsync("What is the capital of France?", options).Select(u => (NewChatResponseUpdate)u);

        var update = (await streamingResponse.ElementAtAsync(0));

        ICancelableChatClient cancelableChatClient = this._chatClient.GetService<ICancelableChatClient>()!;

        // Act
        NewChatResponse? response = (NewChatResponse?)await cancelableChatClient.CancelResponseAsync(update.ResponseId!);

        // Assert
        Assert.NotNull(response);
        Assert.Empty(response.Messages);
        Assert.NotNull(response.ResponseId);
    }

    public void Dispose()
    {
        this._chatClient?.Dispose();
    }
}
