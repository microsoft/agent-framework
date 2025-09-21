// Copyright (c) Microsoft. All rights reserved.

using System;
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
                BackgroundResponsesOptions = new BackgroundResponsesOptions
                {
                    Allow = enableLongRunningResponses
                },
            },
        };

        string responseText = "";
        string? firstContinuationToken = null;
        string? lastContinuationToken = null;

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

    [Fact]
    public async Task RunStreamingAsync_HavingReturnedInitialResponse_AllowsToContinueItAsync()
    {
        using var agent = CreateAIAgent();

        // Part 1: Start the background run and get the first part of the response.
        string? firstContinuationToken = null;
        string? lastContinuationToken = null;
        string responseText = "";

        ChatClientAgentRunOptions options = new()
        {
            ChatOptions = new NewChatOptions()
            {
                BackgroundResponsesOptions = new BackgroundResponsesOptions
                {
                    Allow = true
                },
            }
        };

        await foreach (var update in agent.RunStreamingAsync("What is the capital of France?", options: options))
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

        ChatClientAgentRunOptions options = new()
        {
            ChatOptions = new NewChatOptions()
            {
                BackgroundResponsesOptions = new BackgroundResponsesOptions
                {
                    Allow = false
                },
            }
        };

        using var agent = CreateAIAgent(tools: tools);

        // Arrange
        string responseText = "";

        // Act
        await foreach (var update in agent.RunStreamingAsync("What time is it?", options: options))
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

        using var agent = CreateAIAgent(tools: tools);

        ChatClientAgentRunOptions options = new()
        {
            ChatOptions = new NewChatOptions()
            {
                BackgroundResponsesOptions = new BackgroundResponsesOptions
                {
                    Allow = true
                },
            }
        };

        string responseText = "";

        await foreach (var update in agent.RunStreamingAsync("What time is it?", options: options))
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

        using var agent = CreateAIAgent(tools: tools);

        string responseText = "";

        ChatClientAgentRunOptions options = new()
        {
            ChatOptions = new NewChatOptions()
            {
                BackgroundResponsesOptions = new BackgroundResponsesOptions
                {
                    Allow = true
                },
            }
        };

        await foreach (var update in agent.RunStreamingAsync("What's the weather in Paris right now? Include the time.", options: options))
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

        using var agent = CreateAIAgent(tools: tools);

        // Part 1: Start the background run.
        string responseText = "";
        string? firstContinuationToken = null;
        string? lastContinuationToken = null;

        ChatClientAgentRunOptions options = new()
        {
            ChatOptions = new NewChatOptions()
            {
                BackgroundResponsesOptions = new BackgroundResponsesOptions
                {
                    Allow = true
                },
            }
        };

        await foreach (var update in agent.RunStreamingAsync("What time is it?", options: options))
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

        ChatClientAgentRunOptions options = new()
        {
            ChatOptions = new NewChatOptions()
            {
                BackgroundResponsesOptions = new BackgroundResponsesOptions
                {
                    Allow = true
                },
            }
        };

        using var agent = CreateAIAgent(tools: tools);

        // Part 1: Start the background run.
        string responseText = "";
        string? firstContinuationToken = null;
        string? lastContinuationToken = null;

        await foreach (var update in agent.RunStreamingAsync("What's the weather in Paris right now? Include the time.", options: options))
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
        using var agent = CreateAIAgent();

        // Arrange
        ChatClientAgentRunOptions options = new()
        {
            ChatOptions = new NewChatOptions()
            {
                BackgroundResponsesOptions = new BackgroundResponsesOptions
                {
                    Allow = true
                },
            }
        };

        IAsyncEnumerable<AgentRunResponseUpdate> streamingResponse = agent.RunStreamingAsync("What is the capital of France?", options: options);

        var update = (await streamingResponse.ElementAtAsync(0));

        // Act
        AgentRunResponse? response = await agent.CancelRunAsync(update.ResponseId!);

        // Assert
        Assert.NotNull(response);
        Assert.Empty(response.Messages);
        Assert.NotNull(response.ResponseId);
    }

    private static AIAgentTestProxy CreateAIAgent(string? name = "HelpfulAssistant", string? instructions = "You are a helpful assistant.", IList<AITool>? tools = null)
    {
        var openAIResponseClient = new OpenAIClient(s_config.ApiKey).GetOpenAIResponseClient(s_config.ChatModelId);

        var chatClient = new NewFunctionInvokingChatClient(openAIResponseClient.AsNewIChatClient());

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
