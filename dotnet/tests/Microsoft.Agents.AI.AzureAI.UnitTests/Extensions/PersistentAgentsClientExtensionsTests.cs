// Copyright (c) Microsoft. All rights reserved.

using System;
using System.ClientModel.Primitives;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Azure;
using Azure.AI.Agents.Persistent;
using Azure.Core;
using Microsoft.Extensions.AI;
using Moq;

namespace Microsoft.Agents.AI.AzureAI.UnitTests.Extensions;

public sealed class PersistentAgentsClientExtensionsTests
{
    /// <summary>
    /// Verify that GetAIAgent throws ArgumentNullException when client is null.
    /// </summary>
    [Fact]
    public void GetAIAgent_WithNullClient_ThrowsArgumentNullException()
    {
        // Act & Assert
        var exception = Assert.Throws<ArgumentNullException>(() =>
            ((PersistentAgentsClient)null!).GetAIAgent("test-agent"));

        Assert.Equal("persistentAgentsClient", exception.ParamName);
    }

    /// <summary>
    /// Verify that GetAIAgent throws ArgumentException when agentId is null or whitespace.
    /// </summary>
    [Fact]
    public void GetAIAgent_WithNullOrWhitespaceAgentId_ThrowsArgumentException()
    {
        // Arrange
        var mockClient = new Mock<PersistentAgentsClient>();

        // Act & Assert - null agentId
        var exception1 = Assert.Throws<ArgumentException>(() =>
            mockClient.Object.GetAIAgent((string)null!));
        Assert.Equal("agentId", exception1.ParamName);

        // Act & Assert - empty agentId
        var exception2 = Assert.Throws<ArgumentException>(() =>
            mockClient.Object.GetAIAgent(""));
        Assert.Equal("agentId", exception2.ParamName);

        // Act & Assert - whitespace agentId
        var exception3 = Assert.Throws<ArgumentException>(() =>
            mockClient.Object.GetAIAgent("   "));
        Assert.Equal("agentId", exception3.ParamName);
    }

    /// <summary>
    /// Verify that GetAIAgentAsync throws ArgumentNullException when client is null.
    /// </summary>
    [Fact]
    public async Task GetAIAgentAsync_WithNullClient_ThrowsArgumentNullExceptionAsync()
    {
        // Act & Assert
        var exception = await Assert.ThrowsAsync<ArgumentNullException>(() =>
            ((PersistentAgentsClient)null!).GetAIAgentAsync("test-agent"));

        Assert.Equal("persistentAgentsClient", exception.ParamName);
    }

    /// <summary>
    /// Verify that GetAIAgentAsync throws ArgumentException when agentId is null or whitespace.
    /// </summary>
    [Fact]
    public async Task GetAIAgentAsync_WithNullOrWhitespaceAgentId_ThrowsArgumentExceptionAsync()
    {
        // Arrange
        var mockClient = new Mock<PersistentAgentsClient>();

        // Act & Assert - null agentId
        var exception1 = await Assert.ThrowsAsync<ArgumentException>(() =>
            mockClient.Object.GetAIAgentAsync(null!));
        Assert.Equal("agentId", exception1.ParamName);

        // Act & Assert - empty agentId
        var exception2 = await Assert.ThrowsAsync<ArgumentException>(() =>
            mockClient.Object.GetAIAgentAsync(""));
        Assert.Equal("agentId", exception2.ParamName);

        // Act & Assert - whitespace agentId
        var exception3 = await Assert.ThrowsAsync<ArgumentException>(() =>
            mockClient.Object.GetAIAgentAsync("   "));
        Assert.Equal("agentId", exception3.ParamName);
    }

    /// <summary>
    /// Verify that CreateAIAgent throws ArgumentNullException when client is null.
    /// </summary>
    [Fact]
    public void CreateAIAgent_WithNullClient_ThrowsArgumentNullException()
    {
        // Act & Assert
        var exception = Assert.Throws<ArgumentNullException>(() =>
            ((PersistentAgentsClient)null!).CreateAIAgent("test-model"));

        Assert.Equal("persistentAgentsClient", exception.ParamName);
    }

    /// <summary>
    /// Verify that CreateAIAgentAsync throws ArgumentNullException when client is null.
    /// </summary>
    [Fact]
    public async Task CreateAIAgentAsync_WithNullClient_ThrowsArgumentNullExceptionAsync()
    {
        // Act & Assert
        var exception = await Assert.ThrowsAsync<ArgumentNullException>(() =>
            ((PersistentAgentsClient)null!).CreateAIAgentAsync("test-model"));

        Assert.Equal("persistentAgentsClient", exception.ParamName);
    }

    /// <summary>
    /// Verify that GetAIAgent with clientFactory parameter correctly applies the factory.
    /// </summary>
    [Fact]
    public void GetAIAgent_WithClientFactory_AppliesFactoryCorrectly()
    {
        // Arrange
        var client = CreateFakePersistentAgentsClient();
        TestChatClient? testChatClient = null;

        // Act
        var agent = client.GetAIAgent(
            agentId: "test-agent-id",
            clientFactory: (innerClient) => testChatClient = new TestChatClient(innerClient));

        // Assert
        Assert.NotNull(agent);
        var retrievedTestClient = agent.GetService<TestChatClient>();
        Assert.NotNull(retrievedTestClient);
        Assert.Same(testChatClient, retrievedTestClient);
    }

    /// <summary>
    /// Verify that GetAIAgent without clientFactory works normally.
    /// </summary>
    [Fact]
    public void GetAIAgent_WithoutClientFactory_WorksNormally()
    {
        // Arrange
        var client = CreateFakePersistentAgentsClient();

        // Act
        var agent = client.GetAIAgent(agentId: "test-agent-id");

        // Assert
        Assert.NotNull(agent);
        var retrievedTestClient = agent.GetService<TestChatClient>();
        Assert.Null(retrievedTestClient);
    }

    /// <summary>
    /// Verify that GetAIAgent with null clientFactory works normally.
    /// </summary>
    [Fact]
    public void GetAIAgent_WithNullClientFactory_WorksNormally()
    {
        // Arrange
        PersistentAgentsClient client = CreateFakePersistentAgentsClient();

        // Act
        var agent = client.GetAIAgent(agentId: "test-agent-id", clientFactory: null);

        // Assert
        Assert.NotNull(agent);
        var retrievedTestClient = agent.GetService<TestChatClient>();
        Assert.Null(retrievedTestClient);
    }

    /// <summary>
    /// Verify that CreateAIAgent with clientFactory parameter correctly applies the factory.
    /// </summary>
    [Fact]
    public void CreateAIAgent_WithClientFactory_AppliesFactoryCorrectly()
    {
        // Arrange
        // Arrange
        var client = CreateFakePersistentAgentsClient();
        TestChatClient? testChatClient = null;

        // Act
        var agent = client.CreateAIAgent(
            model: "test-model",
            clientFactory: (innerClient) => testChatClient = new TestChatClient(innerClient));

        // Assert
        Assert.NotNull(agent);
        var retrievedTestClient = agent.GetService<TestChatClient>();
        Assert.NotNull(retrievedTestClient);
        Assert.Same(testChatClient, retrievedTestClient);
    }

    /// <summary>
    /// Verify that CreateAIAgentAsync with clientFactory parameter correctly applies the factory.
    /// </summary>
    [Fact]
    public async Task CreateAIAgentAsync_WithClientFactory_AppliesFactoryCorrectlyAsync()
    {
        // Arrange
        var client = CreateFakePersistentAgentsClient();
        TestChatClient? testChatClient = null;

        // Act
        var agent = await client.CreateAIAgentAsync(
            model: "test-model",
            clientFactory: (innerClient) => testChatClient = new TestChatClient(innerClient));

        // Assert
        Assert.NotNull(agent);
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
        var client = CreateFakePersistentAgentsClient();

        // Act
        var agent = client.CreateAIAgent(model: "test-model");

        // Assert
        Assert.NotNull(agent);
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
        var client = CreateFakePersistentAgentsClient();

        // Act
        var agent = client.CreateAIAgent(model: "test-model", clientFactory: null);

        // Assert
        Assert.NotNull(agent);
        var retrievedTestClient = agent.GetService<TestChatClient>();
        Assert.Null(retrievedTestClient);
    }

    /// <summary>
    /// Verify that CreateAIAgent without clientFactory works normally.
    /// </summary>
    [Fact]
    public async Task CreateAIAgentAsync_WithoutClientFactory_WorksNormallyAsync()
    {
        // Arrange
        var client = CreateFakePersistentAgentsClient();

        // Act
        var agent = await client.CreateAIAgentAsync(model: "test-model");

        // Assert
        Assert.NotNull(agent);
        var retrievedTestClient = agent.GetService<TestChatClient>();
        Assert.Null(retrievedTestClient);
    }

    /// <summary>
    /// Verify that CreateAIAgent with null clientFactory works normally.
    /// </summary>
    [Fact]
    public async Task CreateAIAgentAsync_WithNullClientFactory_WorksNormallyAsync()
    {
        // Arrange
        var client = CreateFakePersistentAgentsClient();

        // Act
        var agent = await client.CreateAIAgentAsync(model: "test-model", clientFactory: null);

        // Assert
        Assert.NotNull(agent);
        var retrievedTestClient = agent.GetService<TestChatClient>();
        Assert.Null(retrievedTestClient);
    }

    /// <summary>
    /// Test custom chat client that can be used to verify clientFactory functionality.
    /// </summary>
    private sealed class TestChatClient : DelegatingChatClient
    {
        public TestChatClient(IChatClient innerClient) : base(innerClient)
        {
        }
    }

    public sealed class FakePersistentAgentsAdministrationClient : PersistentAgentsAdministrationClient
    {
        public FakePersistentAgentsAdministrationClient()
        {
        }

        public override async Task<Response<PersistentAgent>> CreateAgentAsync(string model, string? name = null, string? description = null, string? instructions = null, IEnumerable<ToolDefinition>? tools = null, ToolResources? toolResources = null, float? temperature = null, float? topP = null, BinaryData? responseFormat = null, IReadOnlyDictionary<string, string>? metadata = null, CancellationToken cancellationToken = default)
            => await Task.FromResult(this.FakeResponse);

        public override Response<PersistentAgent> CreateAgent(string model, string? name = null, string? description = null, string? instructions = null, IEnumerable<ToolDefinition>? tools = null, ToolResources? toolResources = null, float? temperature = null, float? topP = null, BinaryData? responseFormat = null, IReadOnlyDictionary<string, string>? metadata = null, CancellationToken cancellationToken = default)
            => this.FakeResponse;

        public override Response<PersistentAgent> GetAgent(string assistantId, CancellationToken cancellationToken = default)
            => this.FakeResponse;

        public override async Task<Response<PersistentAgent>> GetAgentAsync(string assistantId, CancellationToken cancellationToken = default)
            => await Task.FromResult(this.FakeResponse);

        private Response<PersistentAgent> FakeResponse => Response.FromValue(ModelReaderWriter.Read<PersistentAgent>(BinaryData.FromString("""{"id": "agent_abc123"}""")), new FakeResponse())!;
    }

    private static PersistentAgentsClient CreateFakePersistentAgentsClient()
    {
        var client = new PersistentAgentsClient("https://any.com", DelegatedTokenCredential.Create((_, _) => new AccessToken()));

        ((System.Reflection.TypeInfo)typeof(PersistentAgentsClient)).DeclaredFields.First(f => f.Name == "_client")
            .SetValue(client, new FakePersistentAgentsAdministrationClient());
        return client;
    }

    private sealed class FakeResponse : Response
    {
        public override int Status => throw new NotImplementedException();

        public override string ReasonPhrase => throw new NotImplementedException();

        public override Stream? ContentStream { get => throw new NotImplementedException(); set => throw new NotImplementedException(); }
        public override string ClientRequestId { get => throw new NotImplementedException(); set => throw new NotImplementedException(); }

        public override void Dispose()
        {
            throw new NotImplementedException();
        }

        protected override bool ContainsHeader(string name)
        {
            throw new NotImplementedException();
        }

        protected override IEnumerable<HttpHeader> EnumerateHeaders()
        {
            throw new NotImplementedException();
        }

        protected override bool TryGetHeader(string name, out string value)
        {
            throw new NotImplementedException();
        }

        protected override bool TryGetHeaderValues(string name, out IEnumerable<string> values)
        {
            throw new NotImplementedException();
        }
    }
}
