// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using AgentConformance.IntegrationTests.Support;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.AI.Agents;
using OpenAI;
using Shared.IntegrationTests;

namespace OpenAIResponse.IntegrationTests;

public sealed class NewOpenAIResponsesChatClientAgentTests
{
    private static readonly OpenAIConfiguration s_config = TestConfiguration.LoadSection<OpenAIConfiguration>();

    [Theory]
    [InlineData(true)]
    [InlineData(false)]
    public async Task RunAsync_WithLongRunningResponsesEnabledViaOptions_ReturnsExpectedResponseAsync(bool enableLongRunningResponses)
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

        // Act
        AgentRunResponse response = await agent.RunAsync("What is the capital of France?", options: options);

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
    public async Task RunAsync_WithLongRunningResponsesEnabledAtInitialization_ReturnsExpectedResponseAsync(bool enableLongRunningResponses)
    {
        // Arrange
        using var agent = CreateAIAgent(enableLongRunningResponses: enableLongRunningResponses);

        // Act
        AgentRunResponse response = await agent.RunAsync("What is the capital of France?");

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
    public async Task RunAsync_HavingReturnedInitialResponse_AllowsCallerToPollAsync()
    {
        using var agent = CreateAIAgent(enableLongRunningResponses: true);

        // Part 1: Start the background run.
        AgentRunResponse response = await agent.RunAsync("What is the capital of France?");

        Assert.NotNull(response.ContinuationToken);

        // Part 2: Poll for completion.
        int attempts = 0;
        ChatClientAgentRunOptions options = new()
        {
            ChatOptions = new NewChatOptions()
        };

        while (response.ContinuationToken is { } token && ++attempts < 5)
        {
            options.ContinuationToken = token;

            response = await agent.RunAsync([], options: options);

            // Wait for the response to be processed
            await Task.Delay(2000);
        }

        Assert.Null(response.ContinuationToken);
        Assert.Contains("Paris", response.Text);
    }

    [Fact]
    public async Task RunAsync_WithFunctionCalling_AndLongRunningResponsesDisabled_CallsFunctionAsync()
    {
        // Arrange
        IList<AITool> tools = [AIFunctionFactory.Create(() => "5:43", new AIFunctionFactoryOptions { Name = "GetCurrentTime" })];

        using var agent = CreateAIAgent(enableLongRunningResponses: false, tools: tools);

        // Act
        AgentRunResponse response = await agent.RunAsync("What time is it?");

        // Assert
        Assert.Contains("5:43", response.Text);
        Assert.Null(response.ContinuationToken);
    }

    [Fact]
    public async Task RunAsync_WithOneFunction_HavingReturnedInitialResponse_AllowsCallerPollAsync()
    {
        // Part 1: Start the background run.
        IList<AITool> tools = [AIFunctionFactory.Create(() => "5:43", new AIFunctionFactoryOptions { Name = "GetCurrentTime" })];

        using var agent = CreateAIAgent(enableLongRunningResponses: true, tools: tools);

        AgentRunResponse response = await agent.RunAsync("What time is it?");

        Assert.NotNull(response.ContinuationToken);

        // Part 2: Poll for completion.
        int attempts = 0;

        ChatClientAgentRunOptions options = new()
        {
            ChatOptions = new NewChatOptions()
        };

        while (response.ContinuationToken is { } token && ++attempts < 5)
        {
            options.ContinuationToken = token;

            response = await agent.RunAsync([], options: options);

            // Wait for the response to be processed
            await Task.Delay(2000);
        }

        Assert.Contains("5:43", response.Text);
        Assert.Null(response.ContinuationToken);
    }

    [Fact]
    public async Task RunAsync_WithTwoFunctions_HavingReturnedInitialResponse_AllowsCallerPollAsync()
    {
        IList<AITool> tools = [
            AIFunctionFactory.Create(() => new DateTime(2025, 09, 16, 05, 43,00), new AIFunctionFactoryOptions { Name = "GetCurrentTime" }),
            AIFunctionFactory.Create((DateTime time, string location) => $"It's cloudy in {location} at {time}", new AIFunctionFactoryOptions { Name = "GetWeather" })
        ];

        using var agent = CreateAIAgent(enableLongRunningResponses: true, tools: tools);

        // Part 1: Start the background run.
        AgentRunResponse response = await agent.RunAsync("What's the weather in Paris right now? Include the time.");

        Assert.NotNull(response.ContinuationToken);

        // Part 2: Poll for completion.
        int attempts = 0;

        ChatClientAgentRunOptions options = new()
        {
            ChatOptions = new NewChatOptions()
        };

        while (response.ContinuationToken is { } token && ++attempts < 10)
        {
            options.ContinuationToken = token;

            response = await agent.RunAsync([], options: options);

            // Wait for the response to be processed
            await Task.Delay(2000);
        }

        Assert.Contains("5:43", response.Text);
        Assert.Contains("cloudy", response.Text);
        Assert.Null(response.ContinuationToken);
    }

    [Fact]
    public async Task CancelRunAsync_WhenCalled_CancelsRunAsync()
    {
        // Arrange
        using var agent = CreateAIAgent(enableLongRunningResponses: true);

        AgentRunResponse response = await agent.RunAsync("What is the capital of France?");

        // Act
        AgentRunResponse? cancelResponse = await agent.CancelRunAsync(response.ResponseId!);

        // Assert
        Assert.NotNull(cancelResponse);
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
