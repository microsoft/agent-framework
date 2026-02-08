// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Net.Http;
using System.Runtime.CompilerServices;
using System.Threading;
using System.Threading.Tasks;
using Anthropic;
using Anthropic.Core;
using Anthropic.Services;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Anthropic.UnitTests.Extensions;

/// <summary>
/// Unit tests for the AnthropicClientExtensions class.
/// </summary>
public sealed class AnthropicClientExtensionsTests
{
    /// <summary>
    /// Test custom chat client that can be used to verify clientFactory functionality.
    /// </summary>
    private sealed class TestChatClient : IChatClient
    {
        private readonly IChatClient _innerClient;

        public TestChatClient(IChatClient innerClient)
        {
            this._innerClient = innerClient;
        }

        public Task<ChatResponse> GetResponseAsync(IEnumerable<ChatMessage> messages, ChatOptions? options = null, CancellationToken cancellationToken = default)
            => this._innerClient.GetResponseAsync(messages, options, cancellationToken);

        public async IAsyncEnumerable<ChatResponseUpdate> GetStreamingResponseAsync(
            IEnumerable<ChatMessage> messages, ChatOptions? options = null, [EnumeratorCancellation] CancellationToken cancellationToken = default)
        {
            await foreach (var update in this._innerClient.GetStreamingResponseAsync(messages, options, cancellationToken))
            {
                yield return update;
            }
        }

        public object? GetService(Type serviceType, object? serviceKey = null)
        {
            // Return this instance when requested
            if (serviceType == typeof(TestChatClient))
            {
                return this;
            }

            return this._innerClient.GetService(serviceType, serviceKey);
        }

        public void Dispose() => this._innerClient.Dispose();
    }

    /// <summary>
    /// Creates a test ChatClient implementation for testing.
    /// </summary>
    private sealed class TestAnthropicChatClient : IAnthropicClient
    {
        public TestAnthropicChatClient()
        {
        }

        public HttpClient HttpClient { get => throw new NotImplementedException(); init => throw new NotImplementedException(); }
        public string BaseUrl { get => "http://localhost"; init => throw new NotImplementedException(); }
        public bool ResponseValidation { get => throw new NotImplementedException(); init => throw new NotImplementedException(); }
        public int? MaxRetries { get => throw new NotImplementedException(); init => throw new NotImplementedException(); }
        public TimeSpan? Timeout { get => throw new NotImplementedException(); init => throw new NotImplementedException(); }
        public string? ApiKey { get => throw new NotImplementedException(); init => throw new NotImplementedException(); }
        public string? AuthToken { get => throw new NotImplementedException(); init => throw new NotImplementedException(); }

        public IAnthropicClientWithRawResponse WithRawResponse => throw new NotImplementedException();

        public IMessageService Messages => throw new NotImplementedException();

        public IModelService Models => throw new NotImplementedException();

        public IBetaService Beta => throw new NotImplementedException();

        public IAnthropicClient WithOptions(Func<ClientOptions, ClientOptions> modifier)
        {
            throw new NotImplementedException();
        }

        public void Dispose()
        {
        }
    }

    /// <summary>
    /// Verify that CreateAIAgent with clientFactory parameter correctly applies the factory.
    /// </summary>
    [Fact]
    public void CreateAIAgent_WithClientFactory_AppliesFactoryCorrectly()
    {
        // Arrange
        var chatClient = new TestAnthropicChatClient();
        var testChatClient = new TestChatClient(chatClient.AsIChatClient());

        // Act
        var agent = chatClient.AsAIAgent(
            model: "test-model",
            instructions: "Test instructions",
            name: "Test Agent",
            description: "Test description",
            clientFactory: (innerClient) => testChatClient);

        // Assert
        Assert.NotNull(agent);
        Assert.Equal("Test Agent", agent.Name);
        Assert.Equal("Test description", agent.Description);

        // Verify that the custom chat client can be retrieved from the agent's service collection
        var retrievedTestClient = agent.GetService<TestChatClient>();
        Assert.NotNull(retrievedTestClient);
        Assert.Same(testChatClient, retrievedTestClient);
    }

    /// <summary>
    /// Verify that CreateAIAgent with clientFactory using AsBuilder pattern works correctly.
    /// </summary>
    [Fact]
    public void CreateAIAgent_WithClientFactoryUsingAsBuilder_AppliesFactoryCorrectly()
    {
        // Arrange
        var chatClient = new TestAnthropicChatClient();
        TestChatClient? testChatClient = null;

        // Act
        var agent = chatClient.AsAIAgent(
            model: "test-model",
            instructions: "Test instructions",
            clientFactory: (innerClient) =>
                innerClient.AsBuilder().Use((innerClient) => testChatClient = new TestChatClient(innerClient)).Build());

        // Assert
        Assert.NotNull(agent);

        // Verify that the custom chat client can be retrieved from the agent's service collection
        var retrievedTestClient = agent.GetService<TestChatClient>();
        Assert.NotNull(retrievedTestClient);
        Assert.Same(testChatClient, retrievedTestClient);
    }

    /// <summary>
    /// Verify that CreateAIAgent with options and clientFactory parameter correctly applies the factory.
    /// </summary>
    [Fact]
    public void CreateAIAgent_WithOptionsAndClientFactory_AppliesFactoryCorrectly()
    {
        // Arrange
        var chatClient = new TestAnthropicChatClient();
        var testChatClient = new TestChatClient(chatClient.AsIChatClient());
        var options = new ChatClientAgentOptions
        {
            Name = "Test Agent",
            Description = "Test description",
            ChatOptions = new() { Instructions = "Test instructions" }
        };

        // Act
        var agent = chatClient.AsAIAgent(
            options,
            clientFactory: (innerClient) => testChatClient);

        // Assert
        Assert.NotNull(agent);
        Assert.Equal("Test Agent", agent.Name);
        Assert.Equal("Test description", agent.Description);

        // Verify that the custom chat client can be retrieved from the agent's service collection
        var retrievedTestClient = agent.GetService<TestChatClient>();
        Assert.NotNull(retrievedTestClient);
        Assert.Same(testChatClient, retrievedTestClient);
    }

    /// <summary>
    /// Verify that CreateAIAgent without clientFactory works normally.
    /// </summary>
    [Fact]
    public void CreateAIAgent_WithoutClientFactory_WorksNormally()
    {
        // Arrange
        var chatClient = new TestAnthropicChatClient();

        // Act
        var agent = chatClient.AsAIAgent(
            model: "test-model",
            instructions: "Test instructions",
            name: "Test Agent");

        // Assert
        Assert.NotNull(agent);
        Assert.Equal("Test Agent", agent.Name);

        // Verify that no TestChatClient is available since no factory was provided
        var retrievedTestClient = agent.GetService<TestChatClient>();
        Assert.Null(retrievedTestClient);
    }

    /// <summary>
    /// Verify that CreateAIAgent with null clientFactory works normally.
    /// </summary>
    [Fact]
    public void CreateAIAgent_WithNullClientFactory_WorksNormally()
    {
        // Arrange
        var chatClient = new TestAnthropicChatClient();

        // Act
        var agent = chatClient.AsAIAgent(
            model: "test-model",
            instructions: "Test instructions",
            name: "Test Agent",
            clientFactory: null);

        // Assert
        Assert.NotNull(agent);
        Assert.Equal("Test Agent", agent.Name);

        // Verify that no TestChatClient is available since no factory was provided
        var retrievedTestClient = agent.GetService<TestChatClient>();
        Assert.Null(retrievedTestClient);
    }

    /// <summary>
    /// Verify that CreateAIAgent throws ArgumentNullException when client is null.
    /// </summary>
    [Fact]
    public void CreateAIAgent_WithNullClient_ThrowsArgumentNullException()
    {
        // Act & Assert
        var exception = Assert.Throws<ArgumentNullException>(() =>
            ((TestAnthropicChatClient)null!).AsAIAgent("test-model"));

        Assert.Equal("client", exception.ParamName);
    }

    /// <summary>
    /// Verify that CreateAIAgent with options throws ArgumentNullException when options is null.
    /// </summary>
    [Fact]
    public void CreateAIAgent_WithNullOptions_ThrowsArgumentNullException()
    {
        // Arrange
        var chatClient = new TestAnthropicChatClient();

        // Act & Assert
        var exception = Assert.Throws<ArgumentNullException>(() =>
            chatClient.AsAIAgent((ChatClientAgentOptions)null!));

        Assert.Equal("options", exception.ParamName);
    }

    /// <summary>
    /// Verify that CreateAIAgent with tools correctly assigns tools to ChatOptions.
    /// </summary>
    [Fact]
    public void CreateAIAgent_WithTools_AssignsToolsCorrectly()
    {
        // Arrange
        var chatClient = new TestAnthropicChatClient();
        IList<AITool> tools = [AIFunctionFactory.Create(() => "test result", "TestFunction", "A test function")];

        // Act
        var agent = chatClient.AsAIAgent(
            model: "test-model",
            name: "Test Agent",
            tools: tools);

        // Assert
        Assert.NotNull(agent);
        Assert.Equal("Test Agent", agent.Name);
        // When tools are provided, ChatOptions is created but instructions remain null
        Assert.Null(agent.Instructions);

        // Verify that tools are registered in the FunctionInvokingChatClient
        var functionInvokingClient = agent.GetService<FunctionInvokingChatClient>();
        Assert.NotNull(functionInvokingClient);
        Assert.NotNull(functionInvokingClient.AdditionalTools);
        Assert.Contains(functionInvokingClient.AdditionalTools, t => t is AIFunction func && func.Name == "TestFunction");
    }

    /// <summary>
    /// Verify that CreateAIAgent with explicit defaultMaxTokens uses the provided value.
    /// </summary>
    [Fact]
    public async Task CreateAIAgent_WithExplicitMaxTokens_UsesProvidedValueAsync()
    {
        // Arrange
        int capturedMaxTokens = 0;
        var handler = new CapturingHttpHandler(request =>
        {
            // Parse the request body to capture max_tokens
            var content = request.Content?.ReadAsStringAsync().GetAwaiter().GetResult();
            if (content is not null)
            {
                var json = System.Text.Json.JsonDocument.Parse(content);
                if (json.RootElement.TryGetProperty("max_tokens", out var maxTokens))
                {
                    capturedMaxTokens = maxTokens.GetInt32();
                }
            }
        });

        var client = new AnthropicClient
        {
            HttpClient = new HttpClient(handler) { BaseAddress = new Uri("http://localhost") },
            ApiKey = "test-key"
        };

        // Act
        var agent = client.AsAIAgent(
            model: "claude-haiku-4-5",
            name: "Test Agent",
            defaultMaxTokens: 8192);

        // Invoke the agent to trigger the request
        var session = await agent.CreateSessionAsync();
        try
        {
            await agent.RunAsync("Test message", session);
        }
        catch
        {
            // Expected to fail since we're using a test handler
        }

        // Assert
        Assert.Equal(8192, capturedMaxTokens);
    }

    /// <summary>
    /// HTTP handler that captures requests for verification.
    /// </summary>
    private sealed class CapturingHttpHandler : HttpMessageHandler
    {
        private readonly Action<HttpRequestMessage> _captureRequest;

        public CapturingHttpHandler(Action<HttpRequestMessage> captureRequest)
        {
            this._captureRequest = captureRequest;
        }

        protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
        {
            this._captureRequest(request);
            return Task.FromResult(new HttpResponseMessage(System.Net.HttpStatusCode.BadRequest)
            {
                Content = new StringContent("{\"error\": \"test\"}")
            });
        }
    }

    /// <summary>
    /// Verify that CreateAIAgent with tools and instructions correctly assigns both.
    /// </summary>
    [Fact]
    public void CreateAIAgent_WithToolsAndInstructions_AssignsBothCorrectly()
    {
        // Arrange
        var chatClient = new TestAnthropicChatClient();
        IList<AITool> tools = [AIFunctionFactory.Create(() => "test result", "TestFunction", "A test function")];

        // Act
        var agent = chatClient.AsAIAgent(
            model: "test-model",
            name: "Test Agent",
            instructions: "Test instructions",
            tools: tools);

        // Assert
        Assert.NotNull(agent);
        Assert.Equal("Test Agent", agent.Name);
        Assert.Equal("Test instructions", agent.Instructions);

        // Verify that tools are registered in the FunctionInvokingChatClient
        var functionInvokingClient = agent.GetService<FunctionInvokingChatClient>();
        Assert.NotNull(functionInvokingClient);
        Assert.NotNull(functionInvokingClient.AdditionalTools);
        Assert.Contains(functionInvokingClient.AdditionalTools, t => t is AIFunction func && func.Name == "TestFunction");
    }

    /// <summary>
    /// Verify that CreateAIAgent with empty tools list does not assign tools.
    /// </summary>
    [Fact]
    public void CreateAIAgent_WithEmptyTools_DoesNotAssignTools()
    {
        // Arrange
        var chatClient = new TestAnthropicChatClient();
        IList<AITool> tools = [];

        // Act
        var agent = chatClient.AsAIAgent(
            model: "test-model",
            name: "Test Agent",
            tools: tools);

        // Assert
        Assert.NotNull(agent);
        Assert.Equal("Test Agent", agent.Name);
        // With empty tools and no instructions, agent instructions remain null
        Assert.Null(agent.Instructions);

        // Verify that FunctionInvokingChatClient has no additional tools assigned
        var functionInvokingClient = agent.GetService<FunctionInvokingChatClient>();
        Assert.NotNull(functionInvokingClient);
        Assert.True(functionInvokingClient.AdditionalTools is null or { Count: 0 });
    }

    /// <summary>
    /// Verify that CreateAIAgent with null instructions does not set instructions.
    /// </summary>
    [Fact]
    public void CreateAIAgent_WithNullInstructions_DoesNotSetInstructions()
    {
        // Arrange
        var chatClient = new TestAnthropicChatClient();

        // Act
        var agent = chatClient.AsAIAgent(
            model: "test-model",
            name: "Test Agent",
            instructions: null);

        // Assert
        Assert.NotNull(agent);
        Assert.Equal("Test Agent", agent.Name);
        Assert.Null(agent.Instructions);
    }

    /// <summary>
    /// Verify that CreateAIAgent with whitespace instructions does not set instructions.
    /// </summary>
    [Fact]
    public void CreateAIAgent_WithWhitespaceInstructions_DoesNotSetInstructions()
    {
        // Arrange
        var chatClient = new TestAnthropicChatClient();

        // Act
        var agent = chatClient.AsAIAgent(
            model: "test-model",
            name: "Test Agent",
            instructions: "   ");

        // Assert
        Assert.NotNull(agent);
        Assert.Equal("Test Agent", agent.Name);
        Assert.Null(agent.Instructions);
    }
}
