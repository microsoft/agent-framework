// Copyright (c) Microsoft. All rights reserved.

using System;
using System.ClientModel;
using System.ClientModel.Primitives;
using System.IO;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using OpenAI;
using OpenAI.Assistants;

namespace Microsoft.Agents.AI.OpenAI.UnitTests.Extensions;

/// <summary>
/// Unit tests for the <see cref="OpenAIAssistantClientExtensions"/> class.
/// </summary>
public sealed class OpenAIAssistantClientExtensionsTests
{
    /// <summary>
    /// Verify that CreateAIAgent with clientFactory parameter correctly applies the factory.
    /// </summary>
    [Fact]
    public void CreateAIAgent_WithClientFactory_AppliesFactoryCorrectly()
    {
        // Arrange
        var assistantClient = new TestAssistantClient();
        var testChatClient = new TestChatClient(assistantClient.AsIChatClient("test-model"));
        const string ModelId = "test-model";

        // Act
        var agent = assistantClient.CreateAIAgent(
            ModelId,
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
        var assistantClient = new TestAssistantClient();
        TestChatClient? testChatClient = null;

        const string ModelId = "test-model";

        // Act
        var agent = assistantClient.CreateAIAgent(
            ModelId,
            instructions: "Test instructions",
            clientFactory: (innerClient) =>
                innerClient.AsBuilder()
                    .Use((innerClient) => testChatClient = new TestChatClient(innerClient))
                .Build());

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
        var assistantClient = new TestAssistantClient();
        var testChatClient = new TestChatClient(assistantClient.AsIChatClient("test-model"));
        const string ModelId = "test-model";
        var options = new ChatClientAgentOptions
        {
            Name = "Test Agent",
            Description = "Test description",
            Instructions = "Test instructions"
        };

        // Act
        var agent = assistantClient.CreateAIAgent(
            ModelId,
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
        var assistantClient = new TestAssistantClient();
        const string ModelId = "test-model";

        // Act
        var agent = assistantClient.CreateAIAgent(
            ModelId,
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
        var assistantClient = new TestAssistantClient();
        const string ModelId = "test-model";

        // Act
        var agent = assistantClient.CreateAIAgent(
            ModelId,
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
            ((AssistantClient)null!).CreateAIAgent("test-model"));

        Assert.Equal("client", exception.ParamName);
    }

    /// <summary>
    /// Verify that CreateAIAgent throws ArgumentNullException when model is null.
    /// </summary>
    [Fact]
    public void CreateAIAgent_WithNullModel_ThrowsArgumentNullException()
    {
        // Arrange
        var assistantClient = new TestAssistantClient();

        // Act & Assert
        var exception = Assert.Throws<ArgumentNullException>(() =>
            assistantClient.CreateAIAgent(null!));

        Assert.Equal("model", exception.ParamName);
    }

    /// <summary>
    /// Verify that CreateAIAgent with options throws ArgumentNullException when options is null.
    /// </summary>
    [Fact]
    public void CreateAIAgent_WithNullOptions_ThrowsArgumentNullException()
    {
        // Arrange
        var assistantClient = new TestAssistantClient();

        // Act & Assert
        var exception = Assert.Throws<ArgumentNullException>(() =>
            assistantClient.CreateAIAgent("test-model", (ChatClientAgentOptions)null!));

        Assert.Equal("options", exception.ParamName);
    }

    /// <summary>
    /// Creates a test AssistantClient implementation for testing.
    /// </summary>
    private sealed class TestAssistantClient : AssistantClient
    {
        public TestAssistantClient()
        {
        }

        public override ClientResult<Assistant> CreateAssistant(string model, AssistantCreationOptions? options = null, CancellationToken cancellationToken = default)
        {
            return ClientResult.FromValue(ModelReaderWriter.Read<Assistant>(BinaryData.FromString("""{"id": "asst_abc123"}""")), new FakePipelineResponse())!;
        }
    }

    private sealed class TestChatClient : DelegatingChatClient
    {
        public TestChatClient(IChatClient innerClient) : base(innerClient)
        {
        }
    }

    private sealed class FakePipelineResponse : PipelineResponse
    {
        public override int Status => throw new NotImplementedException();

        public override string ReasonPhrase => throw new NotImplementedException();

        public override Stream? ContentStream { get => throw new NotImplementedException(); set => throw new NotImplementedException(); }

        public override BinaryData Content => throw new NotImplementedException();

        protected override PipelineResponseHeaders HeadersCore => throw new NotImplementedException();

        public override BinaryData BufferContent(CancellationToken cancellationToken = default)
        {
            throw new NotImplementedException();
        }

        public override ValueTask<BinaryData> BufferContentAsync(CancellationToken cancellationToken = default)
        {
            throw new NotImplementedException();
        }

        public override void Dispose()
        {
            throw new NotImplementedException();
        }
    }
}
