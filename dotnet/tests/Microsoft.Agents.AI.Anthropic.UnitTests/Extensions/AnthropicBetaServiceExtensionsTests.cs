// Copyright (c) Microsoft. All rights reserved.

#pragma warning disable IDE0052 // Remove unread private members

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
using Moq;
using IBetaMessageService = Anthropic.Services.Beta.IMessageService;
using IMessageService = Anthropic.Services.IMessageService;

namespace Microsoft.Agents.AI.Anthropic.UnitTests.Extensions;

/// <summary>
/// Unit tests for the AnthropicClientExtensions class.
/// </summary>
public sealed class AnthropicBetaServiceExtensionsTests
{
    /// <summary>
    /// Verify that CreateAIAgent with clientFactory parameter correctly applies the factory.
    /// </summary>
    [Fact]
    public void CreateAIAgent_WithClientFactory_AppliesFactoryCorrectly()
    {
        // Arrange
        var chatClient = new TestAnthropicChatClient();
        var testChatClient = new TestChatClient(chatClient.Beta.AsIChatClient());

        // Act
        var agent = chatClient.Beta.CreateAIAgent(
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
        var agent = chatClient.Beta.CreateAIAgent(
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
        var testChatClient = new TestChatClient(chatClient.Beta.AsIChatClient());
        var options = new ChatClientAgentOptions
        {
            Name = "Test Agent",
            Description = "Test description",
            ChatOptions = new() { Instructions = "Test instructions" }
        };

        // Act
        var agent = chatClient.Beta.CreateAIAgent(
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
        var agent = chatClient.Beta.CreateAIAgent(
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
        var agent = chatClient.Beta.CreateAIAgent(
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
            ((IBetaService)null!).CreateAIAgent("test-model"));

        Assert.Equal("betaService", exception.ParamName);
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
            chatClient.Beta.CreateAIAgent((ChatClientAgentOptions)null!));

        Assert.Equal("options", exception.ParamName);
    }

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
            this.BetaService = new TestBetaService(this);
        }

        public HttpClient HttpClient { get => throw new NotImplementedException(); init => throw new NotImplementedException(); }
        public Uri BaseUrl { get => new("http://localhost"); init => throw new NotImplementedException(); }
        public bool ResponseValidation { get => throw new NotImplementedException(); init => throw new NotImplementedException(); }
        public int? MaxRetries { get => throw new NotImplementedException(); init => throw new NotImplementedException(); }
        public TimeSpan? Timeout { get => throw new NotImplementedException(); init => throw new NotImplementedException(); }
        public string? APIKey { get => throw new NotImplementedException(); init => throw new NotImplementedException(); }
        public string? AuthToken { get => throw new NotImplementedException(); init => throw new NotImplementedException(); }

        public IMessageService Messages => throw new NotImplementedException();

        public IModelService Models => throw new NotImplementedException();

        public IBetaService Beta => this.BetaService;

        public IBetaService BetaService { get; }

        IMessageService IAnthropicClient.Messages => new Mock<IMessageService>().Object;

        public Task<HttpResponse> Execute<T>(HttpRequest<T> request, CancellationToken cancellationToken = default) where T : ParamsBase
        {
            throw new NotImplementedException();
        }

        public IAnthropicClient WithOptions(Func<ClientOptions, ClientOptions> modifier)
        {
            throw new NotImplementedException();
        }

        private sealed class TestBetaService : IBetaService
        {
            private readonly IAnthropicClient _client;

            public TestBetaService(IAnthropicClient client)
            {
                this._client = client;
            }

            public global::Anthropic.Services.Beta.IModelService Models => throw new NotImplementedException();

            public global::Anthropic.Services.Beta.IFileService Files => throw new NotImplementedException();

            public global::Anthropic.Services.Beta.ISkillService Skills => throw new NotImplementedException();

            public IBetaMessageService Messages => new Mock<IBetaMessageService>().Object;

            public IBetaService WithOptions(Func<ClientOptions, ClientOptions> modifier)
            {
                throw new NotImplementedException();
            }
        }
    }
}
