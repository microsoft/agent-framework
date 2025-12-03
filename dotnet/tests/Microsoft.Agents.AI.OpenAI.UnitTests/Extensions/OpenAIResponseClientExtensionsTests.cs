// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Reflection;
using System.Runtime.CompilerServices;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using OpenAI;
using OpenAI.Responses;

namespace Microsoft.Agents.AI.OpenAI.UnitTests.Extensions;

/// <summary>
/// Unit tests for the <see cref="OpenAIResponseClientExtensions"/> class.
/// </summary>
public sealed class OpenAIResponseClientExtensionsTests
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
    /// Creates a test OpenAIResponseClient implementation for testing.
    /// </summary>
    private sealed class TestOpenAIResponseClient : OpenAIResponseClient
    {
        public TestOpenAIResponseClient()
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
        var responseClient = new TestOpenAIResponseClient();
        var testChatClient = new TestChatClient(responseClient.AsIChatClient());

        // Act
        var agent = responseClient.CreateAIAgent(
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
    /// Verify that CreateAIAgent without clientFactory works normally.
    /// </summary>
    [Fact]
    public void CreateAIAgent_WithoutClientFactory_WorksNormally()
    {
        // Arrange
        var responseClient = new TestOpenAIResponseClient();

        // Act
        var agent = responseClient.CreateAIAgent(
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
        var responseClient = new TestOpenAIResponseClient();

        // Act
        var agent = responseClient.CreateAIAgent(
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
            ((OpenAIResponseClient)null!).CreateAIAgent());

        Assert.Equal("client", exception.ParamName);
    }

    /// <summary>
    /// Verify that CreateAIAgent with options throws ArgumentNullException when options is null.
    /// </summary>
    [Fact]
    public void CreateAIAgent_WithNullOptions_ThrowsArgumentNullException()
    {
        // Arrange
        var responseClient = new TestOpenAIResponseClient();

        // Act & Assert
        var exception = Assert.Throws<ArgumentNullException>(() =>
            responseClient.CreateAIAgent((ChatClientAgentOptions)null!));

        Assert.Equal("options", exception.ParamName);
    }

    /// <summary>
    /// Verify that CreateAIAgent with services parameter correctly passes it through to the ChatClientAgent.
    /// </summary>
    [Fact]
    public void CreateAIAgent_WithServices_PassesServicesToAgent()
    {
        // Arrange
        var responseClient = new TestOpenAIResponseClient();
        var serviceProvider = new TestServiceProvider();

        // Act
        var agent = responseClient.CreateAIAgent(
            instructions: "Test instructions",
            name: "Test Agent",
            services: serviceProvider);

        // Assert
        Assert.NotNull(agent);

        // Verify the IServiceProvider was passed through to the FunctionInvokingChatClient
        var chatClient = agent.GetService<IChatClient>();
        Assert.NotNull(chatClient);
        var functionInvokingClient = chatClient.GetService<FunctionInvokingChatClient>();
        Assert.NotNull(functionInvokingClient);
        Assert.Same(serviceProvider, GetFunctionInvocationServices(functionInvokingClient));
    }

    /// <summary>
    /// Verify that CreateAIAgent with options and services parameter correctly passes it through to the ChatClientAgent.
    /// </summary>
    [Fact]
    public void CreateAIAgent_WithOptionsAndServices_PassesServicesToAgent()
    {
        // Arrange
        var responseClient = new TestOpenAIResponseClient();
        var serviceProvider = new TestServiceProvider();
        var options = new ChatClientAgentOptions
        {
            Name = "Test Agent",
            ChatOptions = new() { Instructions = "Test instructions" }
        };

        // Act
        var agent = responseClient.CreateAIAgent(options, services: serviceProvider);

        // Assert
        Assert.NotNull(agent);
        Assert.Equal("Test Agent", agent.Name);

        // Verify the IServiceProvider was passed through to the FunctionInvokingChatClient
        var chatClient = agent.GetService<IChatClient>();
        Assert.NotNull(chatClient);
        var functionInvokingClient = chatClient.GetService<FunctionInvokingChatClient>();
        Assert.NotNull(functionInvokingClient);
        Assert.Same(serviceProvider, GetFunctionInvocationServices(functionInvokingClient));
    }

    /// <summary>
    /// Verify that CreateAIAgent with both clientFactory and services works correctly.
    /// </summary>
    [Fact]
    public void CreateAIAgent_WithClientFactoryAndServices_AppliesBothCorrectly()
    {
        // Arrange
        var responseClient = new TestOpenAIResponseClient();
        var serviceProvider = new TestServiceProvider();
        var testChatClient = new TestChatClient(responseClient.AsIChatClient());

        // Act
        var agent = responseClient.CreateAIAgent(
            instructions: "Test instructions",
            name: "Test Agent",
            clientFactory: (innerClient) => testChatClient,
            services: serviceProvider);

        // Assert
        Assert.NotNull(agent);

        // Verify the custom chat client was applied
        var retrievedTestClient = agent.GetService<TestChatClient>();
        Assert.NotNull(retrievedTestClient);
        Assert.Same(testChatClient, retrievedTestClient);

        // Verify the IServiceProvider was passed through
        var chatClient = agent.GetService<IChatClient>();
        Assert.NotNull(chatClient);
        var functionInvokingClient = chatClient.GetService<FunctionInvokingChatClient>();
        Assert.NotNull(functionInvokingClient);
        Assert.Same(serviceProvider, GetFunctionInvocationServices(functionInvokingClient));
    }

    /// <summary>
    /// A simple test IServiceProvider implementation for testing.
    /// </summary>
    private sealed class TestServiceProvider : IServiceProvider
    {
        public object? GetService(Type serviceType) => null;
    }

    /// <summary>
    /// Uses reflection to access the FunctionInvocationServices property which is not public.
    /// </summary>
    private static IServiceProvider? GetFunctionInvocationServices(FunctionInvokingChatClient client)
    {
        var property = typeof(FunctionInvokingChatClient).GetProperty(
            "FunctionInvocationServices",
            BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic);
        return property?.GetValue(client) as IServiceProvider;
    }
}
