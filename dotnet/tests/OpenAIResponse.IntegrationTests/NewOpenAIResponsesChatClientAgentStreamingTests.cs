// Copyright (c) Microsoft. All rights reserved.

using System;
using System.ClientModel;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using AgentConformance.IntegrationTests.Support;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.AI.Agents;
using OpenAI;
using OpenAI.Responses;
using Shared.IntegrationTests;

namespace OpenAIResponse.IntegrationTests;

public sealed class NewOpenAIResponsesChatClientAgentStreamingTests
{
    private static readonly OpenAIConfiguration s_config = TestConfiguration.LoadSection<OpenAIConfiguration>();

    [Theory]
    [InlineData(true)]
    [InlineData(false)]
    public async Task RunStreamingAsync_WithLonRunningResponsesEnabledViaOptions_ReturnsExpectedResponseAsync(bool enableLongRunningResponses)
    {
        // Arrange
        using var agent = CreateAIAgent();

        ChatClientAgentRunOptions options = new()
        {
            ChatOptions = new NewChatOptions
            {
                // Should we allow enabling long-running responses for agents via options?
                // Or only at initialization?
                AllowLongRunningResponses = enableLongRunningResponses
            },
        };

        string responseText = "";
        ContinuationToken? firstContinuationToken = null;
        ContinuationToken? lastContinuationToken = null;

        // Act
        await foreach (var update in agent.RunStreamingAsync("What is the capital of France?", options: options))
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
    public async Task RunStreamingAsync_WithLongRunningResponsesEnabledAtInitialization_ReturnsExpectedResponseAsync(bool enableLongRunningResponses)
    {
        // Arrange
        using var agent = CreateAIAgent(enableLongRunningResponses: enableLongRunningResponses);

        string responseText = "";
        ContinuationToken? firstContinuationToken = null;
        ContinuationToken? lastContinuationToken = null;

        // Act
        await foreach (var update in agent.RunStreamingAsync("What is the capital of France?"))
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
    public async Task RunStreamingAsync_HavingReturnedInitialResponse_AllowsToContinueItAsync()
    {
        using var agent = CreateAIAgent(enableLongRunningResponses: true);

        // Part 1: Start the background run and get the first part of the response.
        ContinuationToken? firstContinuationToken = null;
        ContinuationToken? lastContinuationToken = null;
        string responseText = "";

        await foreach (var update in agent.RunStreamingAsync("What is the capital of France?"))
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
        ChatClientAgentRunOptions options = new()
        {
            ChatOptions = new NewChatOptions(),
            ContinuationToken = firstContinuationToken
        };

        AgentRunResponseUpdate? firstUpdate = null;

        await foreach (var update in agent.RunStreamingAsync([], options: options))
        {
            firstUpdate ??= update;

            responseText += update;

            lastContinuationToken = update.ContinuationToken;
        }

        Assert.Contains("Paris", responseText);
        Assert.Null(lastContinuationToken);
        Assert.NotNull(firstUpdate?.RawRepresentation);
        Assert.Equal(1, ((StreamingResponseUpdate)((NewChatResponseUpdate)firstUpdate.RawRepresentation).RawRepresentation!).SequenceNumber);
    }

    [Fact]
    public async Task RunStreamingAsync_WithFunctionCalling_AndLongRunningResponsesDisabled_CallsFunctionAsync()
    {
        List<AITool> tools = [AIFunctionFactory.Create(() => "5:43", new AIFunctionFactoryOptions { Name = "GetCurrentTime" })];

        using var agent = CreateAIAgent(enableLongRunningResponses: false, tools: tools);

        // Arrange
        string responseText = "";

        // Act
        await foreach (var update in agent.RunStreamingAsync("What time is it?"))
        {
            responseText += update;

            Assert.Null(update.ContinuationToken);
        }

        // Assert
        Assert.Contains("5:43", responseText);
    }

    [Fact]
    public async Task RunStreamingAsync_WithOneFunction_AndLongRunningResponsesEnabled_AllowsToContinueItAsync()
    {
        List<AITool> tools = [AIFunctionFactory.Create(() => "5:43", new AIFunctionFactoryOptions { Name = "GetCurrentTime" })];

        using var agent = CreateAIAgent(enableLongRunningResponses: true, tools: tools);

        // Part 1: Start the background run.
        string responseText = "";

        await foreach (var update in agent.RunStreamingAsync("What time is it?"))
        {
            responseText += update;
        }

        Assert.Contains("5:43", responseText);
    }

    [Fact]
    public async Task RunStreamingAsync_WithTwoFunctions_AndLongRunningResponsesEnabled_AllowsToContinueItAsync()
    {
        List<AITool> tools = [
            AIFunctionFactory.Create(() => new DateTime(2025, 09, 16, 05, 43,00), new AIFunctionFactoryOptions { Name = "GetCurrentTime" }),
            AIFunctionFactory.Create((DateTime time, string location) => $"It's cloudy in {location} at {time}", new AIFunctionFactoryOptions { Name = "GetWeather" })
        ];

        using var agent = CreateAIAgent(enableLongRunningResponses: true, tools: tools);

        string responseText = "";

        await foreach (var update in agent.RunStreamingAsync("What's the weather in Paris right now? Include the time."))
        {
            responseText += update;
        }

        Assert.Contains("5:43", responseText);
        Assert.Contains("cloudy", responseText);
    }

    [Fact]
    public async Task RunStreamingAsync_WithOneFunction_HavingReturnedInitialResponse_AllowsToContinueItAsync()
    {
        List<AITool> tools = [AIFunctionFactory.Create(() => "5:43", new AIFunctionFactoryOptions { Name = "GetCurrentTime" })];

        using var agent = CreateAIAgent(enableLongRunningResponses: true, tools: tools);

        // Part 1: Start the background run.
        string responseText = "";
        ContinuationToken? firstContinuationToken = null;
        ContinuationToken? lastContinuationToken = null;

        await foreach (var update in agent.RunStreamingAsync("What time is it?"))
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
        ChatClientAgentRunOptions options = new()
        {
            ChatOptions = new NewChatOptions(),
            ContinuationToken = firstContinuationToken
        };

        await foreach (var update in agent.RunStreamingAsync([], options: options))
        {
            responseText += update;

            lastContinuationToken = update.ContinuationToken;
        }

        Assert.Contains("5:43", responseText);
        Assert.Null(lastContinuationToken);
    }

    [Fact]
    public async Task RunStreamingAsync_WithTwoFunctions_HavingReturnedInitialResponse_AllowsToContinueItAsync()
    {
        List<AITool> tools = [
            AIFunctionFactory.Create(() => new DateTime(2025, 09, 16, 05, 43,00), new AIFunctionFactoryOptions { Name = "GetCurrentTime" }),
            AIFunctionFactory.Create((DateTime time, string location) => $"It's cloudy in {location} at {time}", new AIFunctionFactoryOptions { Name = "GetWeather" })
        ];

        using var agent = CreateAIAgent(enableLongRunningResponses: true, tools: tools);

        // Part 1: Start the background run.
        string responseText = "";
        ContinuationToken? firstContinuationToken = null;
        ContinuationToken? lastContinuationToken = null;

        await foreach (var update in agent.RunStreamingAsync("What's the weather in Paris right now? Include the time."))
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
        ChatClientAgentRunOptions options = new()
        {
            ChatOptions = new NewChatOptions(),
            ContinuationToken = firstContinuationToken
        };

        await foreach (var update in agent.RunStreamingAsync([], options: options))
        {
            responseText += update;

            lastContinuationToken = update.ContinuationToken;
        }

        Assert.Contains("5:43", responseText);
        Assert.Contains("cloudy", responseText);
        Assert.Null(lastContinuationToken);
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
        using var agent = CreateAIAgent(enableLongRunningResponses: true);

        // Arrange
        IAsyncEnumerable<AgentRunResponseUpdate> streamingResponse = agent.RunStreamingAsync("What is the capital of France?");

        var update = (await streamingResponse.ElementAtAsync(0));

        // Act
        AgentRunResponse? response = await agent.CancelRunAsync(update.ResponseId!);

        // Assert
        Assert.NotNull(response);
        Assert.Empty(response.Messages);
        Assert.NotNull(response.ResponseId);
    }

    private static AIAgentTestProxy CreateAIAgent(bool? enableLongRunningResponses = null, string? name = "HelpfulAssistant", string? instructions = "You are a helpful assistant.", IList<AITool>? tools = null)
    {
        var openAIResponseClient = new OpenAIClient(s_config.ApiKey).GetOpenAIResponseClient(s_config.ChatModelId);

        var chatClient = new NewFunctionInvokingChatClient(openAIResponseClient.AsNewIChatClient(enableLongRunningResponses));

        var aiAgent = new ChatClientAgent(
            chatClient,
            options: new()
            {
                Name = name,
                Instructions = instructions,
                ChatOptions = new ChatOptions
                {
                    Tools = tools,
                    //RawRepresentationFactory = new Func<IChatClient, object>((_) => new ResponseCreationOptions() { StoredOutputEnabled = store })
                },
                UseProvidedChatClientAsIs = true
            });

        return new AIAgentTestProxy(aiAgent, chatClient);
    }

    private sealed class AIAgentTestProxy : AIAgent, IDisposable
    {
        private readonly AIAgent _innerAgent;
        private readonly IChatClient _innerChatClient;

        public AIAgentTestProxy(AIAgent aiAgent, IChatClient innerChatClient)
        {
            this._innerAgent = aiAgent;
            this._innerChatClient = innerChatClient;
        }

        public override Task<AgentRunResponse> RunAsync(IEnumerable<ChatMessage> messages, AgentThread? thread = null, AgentRunOptions? options = null, CancellationToken cancellationToken = default)
        {
            return this._innerAgent.RunAsync(messages, thread, options, cancellationToken);
        }

        public override IAsyncEnumerable<AgentRunResponseUpdate> RunStreamingAsync(IEnumerable<ChatMessage> messages, AgentThread? thread = null, AgentRunOptions? options = null, CancellationToken cancellationToken = default)
        {
            return this._innerAgent.RunStreamingAsync(messages, thread, options, cancellationToken);
        }

        public override Task<AgentRunResponse?> CancelRunAsync(string id, AgentCancelRunOptions? options = null, CancellationToken cancellationToken = default)
        {
            return this._innerAgent.CancelRunAsync(id, options, cancellationToken);
        }

        public override object? GetService(Type serviceType, object? serviceKey = null)
        {
            return this._innerAgent.GetService(serviceType, serviceKey);
        }

        public void Dispose()
        {
            this._innerChatClient.Dispose();
        }
    }
}
