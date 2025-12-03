// Copyright (c) Microsoft. All rights reserved.

using System;
using System.ClientModel.Primitives;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Threading;
using System.Threading.Tasks;
using Azure;
using Azure.AI.Agents.Persistent;
using Azure.Core;
using Microsoft.Extensions.AI;
using Moq;

namespace Microsoft.Agents.AI.AzureAI.Persistent.UnitTests.Extensions;

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
    /// Verify that GetAIAgent with Response and options works correctly.
    /// </summary>
    [Fact]
    public void GetAIAgent_WithResponseAndOptions_WorksCorrectly()
    {
        // Arrange
        var client = CreateFakePersistentAgentsClient();
        var persistentAgent = ModelReaderWriter.Read<PersistentAgent>(BinaryData.FromString("""{"id": "agent_abc123", "name": "Original Name", "description": "Original Description", "instructions": "Original Instructions"}"""))!;
        var response = Response.FromValue(persistentAgent, new FakeResponse());

        var options = new ChatClientAgentOptions
        {
            Name = "Override Name",
            Description = "Override Description",
            ChatOptions = new() { Instructions = "Override Instructions" }
        };

        // Act
        var agent = client.GetAIAgent(response, options);

        // Assert
        Assert.NotNull(agent);
        Assert.Equal("Override Name", agent.Name);
        Assert.Equal("Override Description", agent.Description);
        Assert.Equal("Override Instructions", agent.Instructions);
    }

    /// <summary>
    /// Verify that GetAIAgent with PersistentAgent and options works correctly.
    /// </summary>
    [Fact]
    public void GetAIAgent_WithPersistentAgentAndOptions_WorksCorrectly()
    {
        // Arrange
        var client = CreateFakePersistentAgentsClient();
        var persistentAgent = ModelReaderWriter.Read<PersistentAgent>(BinaryData.FromString("""{"id": "agent_abc123", "name": "Original Name", "description": "Original Description", "instructions": "Original Instructions"}"""))!;

        var options = new ChatClientAgentOptions
        {
            Name = "Override Name",
            Description = "Override Description",
            ChatOptions = new() { Instructions = "Override Instructions" }
        };

        // Act
        var agent = client.GetAIAgent(persistentAgent, options);

        // Assert
        Assert.NotNull(agent);
        Assert.Equal("Override Name", agent.Name);
        Assert.Equal("Override Description", agent.Description);
        Assert.Equal("Override Instructions", agent.Instructions);
    }

    /// <summary>
    /// Verify that GetAIAgent with PersistentAgent and options falls back to agent metadata when options are null.
    /// </summary>
    [Fact]
    public void GetAIAgent_WithPersistentAgentAndOptionsWithNullFields_FallsBackToAgentMetadata()
    {
        // Arrange
        var client = CreateFakePersistentAgentsClient();
        var persistentAgent = ModelReaderWriter.Read<PersistentAgent>(BinaryData.FromString("""{"id": "agent_abc123", "name": "Original Name", "description": "Original Description", "instructions": "Original Instructions"}"""))!;

        var options = new ChatClientAgentOptions(); // Empty options

        // Act
        var agent = client.GetAIAgent(persistentAgent, options);

        // Assert
        Assert.NotNull(agent);
        Assert.Equal("Original Name", agent.Name);
        Assert.Equal("Original Description", agent.Description);
        Assert.Equal("Original Instructions", agent.Instructions);
    }

    /// <summary>
    /// Verify that GetAIAgent with agentId and options works correctly.
    /// </summary>
    [Fact]
    public void GetAIAgent_WithAgentIdAndOptions_WorksCorrectly()
    {
        // Arrange
        var client = CreateFakePersistentAgentsClient();
        const string AgentId = "agent_abc123";

        var options = new ChatClientAgentOptions
        {
            Name = "Override Name",
            Description = "Override Description",
            ChatOptions = new() { Instructions = "Override Instructions" }
        };

        // Act
        var agent = client.GetAIAgent(AgentId, options);

        // Assert
        Assert.NotNull(agent);
        Assert.Equal("Override Name", agent.Name);
        Assert.Equal("Override Description", agent.Description);
        Assert.Equal("Override Instructions", agent.Instructions);
    }

    /// <summary>
    /// Verify that GetAIAgentAsync with agentId and options works correctly.
    /// </summary>
    [Fact]
    public async Task GetAIAgentAsync_WithAgentIdAndOptions_WorksCorrectlyAsync()
    {
        // Arrange
        var client = CreateFakePersistentAgentsClient();
        const string AgentId = "agent_abc123";

        var options = new ChatClientAgentOptions
        {
            Name = "Override Name",
            Description = "Override Description",
            ChatOptions = new() { Instructions = "Override Instructions" }
        };

        // Act
        var agent = await client.GetAIAgentAsync(AgentId, options);

        // Assert
        Assert.NotNull(agent);
        Assert.Equal("Override Name", agent.Name);
        Assert.Equal("Override Description", agent.Description);
        Assert.Equal("Override Instructions", agent.Instructions);
    }

    /// <summary>
    /// Verify that GetAIAgent with clientFactory parameter correctly applies the factory.
    /// </summary>
    [Fact]
    public void GetAIAgent_WithOptionsAndClientFactory_AppliesFactoryCorrectly()
    {
        // Arrange
        var client = CreateFakePersistentAgentsClient();
        var persistentAgent = ModelReaderWriter.Read<PersistentAgent>(BinaryData.FromString("""{"id": "agent_abc123", "name": "Test Agent"}"""))!;
        var testChatClient = new TestChatClient(client.AsIChatClient("agent_abc123"));

        var options = new ChatClientAgentOptions
        {
            Name = "Test Agent"
        };

        // Act
        var agent = client.GetAIAgent(
            persistentAgent,
            options,
            clientFactory: (innerClient) => testChatClient);

        // Assert
        Assert.NotNull(agent);
        Assert.Equal("Test Agent", agent.Name);

        // Verify that the custom chat client can be retrieved from the agent's service collection
        var retrievedTestClient = agent.GetService<TestChatClient>();
        Assert.NotNull(retrievedTestClient);
        Assert.Same(testChatClient, retrievedTestClient);
    }

    /// <summary>
    /// Verify that GetAIAgent throws ArgumentNullException when response is null.
    /// </summary>
    [Fact]
    public void GetAIAgent_WithNullResponse_ThrowsArgumentNullException()
    {
        // Arrange
        var client = CreateFakePersistentAgentsClient();
        var options = new ChatClientAgentOptions();

        // Act & Assert
        var exception = Assert.Throws<ArgumentNullException>(() =>
            client.GetAIAgent((Response<PersistentAgent>)null!, options));

        Assert.Equal("persistentAgentResponse", exception.ParamName);
    }

    /// <summary>
    /// Verify that GetAIAgent throws ArgumentNullException when persistentAgent is null.
    /// </summary>
    [Fact]
    public void GetAIAgent_WithNullPersistentAgent_ThrowsArgumentNullException()
    {
        // Arrange
        var client = CreateFakePersistentAgentsClient();
        var options = new ChatClientAgentOptions();

        // Act & Assert
        var exception = Assert.Throws<ArgumentNullException>(() =>
            client.GetAIAgent((PersistentAgent)null!, options));

        Assert.Equal("persistentAgentMetadata", exception.ParamName);
    }

    /// <summary>
    /// Verify that GetAIAgent throws ArgumentNullException when options is null.
    /// </summary>
    [Fact]
    public void GetAIAgent_WithNullOptions_ThrowsArgumentNullException()
    {
        // Arrange
        var client = CreateFakePersistentAgentsClient();
        var persistentAgent = ModelReaderWriter.Read<PersistentAgent>(BinaryData.FromString("""{"id": "agent_abc123"}"""))!;

        // Act & Assert
        var exception = Assert.Throws<ArgumentNullException>(() =>
            client.GetAIAgent(persistentAgent, (ChatClientAgentOptions)null!));

        Assert.Equal("options", exception.ParamName);
    }

    /// <summary>
    /// Verify that GetAIAgent throws ArgumentException when agentId is empty.
    /// </summary>
    [Fact]
    public void GetAIAgent_WithOptionsAndEmptyAgentId_ThrowsArgumentException()
    {
        // Arrange
        var client = CreateFakePersistentAgentsClient();
        var options = new ChatClientAgentOptions();

        // Act & Assert
        var exception = Assert.Throws<ArgumentException>(() =>
            client.GetAIAgent(string.Empty, options));

        Assert.Equal("agentId", exception.ParamName);
    }

    /// <summary>
    /// Verify that GetAIAgentAsync throws ArgumentException when agentId is empty.
    /// </summary>
    [Fact]
    public async Task GetAIAgentAsync_WithOptionsAndEmptyAgentId_ThrowsArgumentExceptionAsync()
    {
        // Arrange
        var client = CreateFakePersistentAgentsClient();
        var options = new ChatClientAgentOptions();

        // Act & Assert
        var exception = await Assert.ThrowsAsync<ArgumentException>(() =>
            client.GetAIAgentAsync(string.Empty, options));

        Assert.Equal("agentId", exception.ParamName);
    }

    /// <summary>
    /// Verify that CreateAIAgent with options works correctly.
    /// </summary>
    [Fact]
    public void CreateAIAgent_WithOptions_WorksCorrectly()
    {
        // Arrange
        var client = CreateFakePersistentAgentsClient();
        const string Model = "test-model";

        var options = new ChatClientAgentOptions
        {
            Name = "Test Agent",
            Description = "Test description",
            ChatOptions = new() { Instructions = "Test instructions" }
        };

        // Act
        var agent = client.CreateAIAgent(Model, options);

        // Assert
        Assert.NotNull(agent);
        Assert.Equal("Test Agent", agent.Name);
        Assert.Equal("Test description", agent.Description);
        Assert.Equal("Test instructions", agent.Instructions);
    }

    /// <summary>
    /// Verify that CreateAIAgentAsync with options works correctly.
    /// </summary>
    [Fact]
    public async Task CreateAIAgentAsync_WithOptions_WorksCorrectlyAsync()
    {
        // Arrange
        var client = CreateFakePersistentAgentsClient();
        const string Model = "test-model";

        var options = new ChatClientAgentOptions
        {
            Name = "Test Agent",
            Description = "Test description",
            ChatOptions = new() { Instructions = "Test instructions" }
        };

        // Act
        var agent = await client.CreateAIAgentAsync(Model, options);

        // Assert
        Assert.NotNull(agent);
        Assert.Equal("Test Agent", agent.Name);
        Assert.Equal("Test description", agent.Description);
        Assert.Equal("Test instructions", agent.Instructions);
    }

    /// <summary>
    /// Verify that CreateAIAgent with options and clientFactory applies the factory correctly.
    /// </summary>
    [Fact]
    public void CreateAIAgent_WithOptionsAndClientFactory_AppliesFactoryCorrectly()
    {
        // Arrange
        var client = CreateFakePersistentAgentsClient();
        TestChatClient? testChatClient = null;
        const string Model = "test-model";

        var options = new ChatClientAgentOptions
        {
            Name = "Test Agent"
        };

        // Act
        var agent = client.CreateAIAgent(
            Model,
            options,
            clientFactory: (innerClient) => testChatClient = new TestChatClient(innerClient));

        // Assert
        Assert.NotNull(agent);
        Assert.Equal("Test Agent", agent.Name);

        // Verify that the custom chat client can be retrieved from the agent's service collection
        var retrievedTestClient = agent.GetService<TestChatClient>();
        Assert.NotNull(retrievedTestClient);
        Assert.Same(testChatClient, retrievedTestClient);
    }

    /// <summary>
    /// Verify that CreateAIAgentAsync with options and clientFactory applies the factory correctly.
    /// </summary>
    [Fact]
    public async Task CreateAIAgentAsync_WithOptionsAndClientFactory_AppliesFactoryCorrectlyAsync()
    {
        // Arrange
        var client = CreateFakePersistentAgentsClient();
        TestChatClient? testChatClient = null;
        const string Model = "test-model";

        var options = new ChatClientAgentOptions
        {
            Name = "Test Agent"
        };

        // Act
        var agent = await client.CreateAIAgentAsync(
            Model,
            options,
            clientFactory: (innerClient) => testChatClient = new TestChatClient(innerClient));

        // Assert
        Assert.NotNull(agent);
        Assert.Equal("Test Agent", agent.Name);

        // Verify that the custom chat client can be retrieved from the agent's service collection
        var retrievedTestClient = agent.GetService<TestChatClient>();
        Assert.NotNull(retrievedTestClient);
        Assert.Same(testChatClient, retrievedTestClient);
    }

    /// <summary>
    /// Verify that CreateAIAgent throws ArgumentNullException when options is null.
    /// </summary>
    [Fact]
    public void CreateAIAgent_WithNullOptions_ThrowsArgumentNullException()
    {
        // Arrange
        var client = CreateFakePersistentAgentsClient();

        // Act & Assert
        var exception = Assert.Throws<ArgumentNullException>(() =>
            client.CreateAIAgent("test-model", (ChatClientAgentOptions)null!));

        Assert.Equal("options", exception.ParamName);
    }

    /// <summary>
    /// Verify that CreateAIAgentAsync throws ArgumentNullException when options is null.
    /// </summary>
    [Fact]
    public async Task CreateAIAgentAsync_WithNullOptions_ThrowsArgumentNullExceptionAsync()
    {
        // Arrange
        var client = CreateFakePersistentAgentsClient();

        // Act & Assert
        var exception = await Assert.ThrowsAsync<ArgumentNullException>(() =>
            client.CreateAIAgentAsync("test-model", (ChatClientAgentOptions)null!));

        Assert.Equal("options", exception.ParamName);
    }

    /// <summary>
    /// Verify that CreateAIAgent throws ArgumentException when model is empty.
    /// </summary>
    [Fact]
    public void CreateAIAgent_WithEmptyModel_ThrowsArgumentException()
    {
        // Arrange
        var client = CreateFakePersistentAgentsClient();
        var options = new ChatClientAgentOptions();

        // Act & Assert
        var exception = Assert.Throws<ArgumentException>(() =>
            client.CreateAIAgent(string.Empty, options));

        Assert.Equal("model", exception.ParamName);
    }

    /// <summary>
    /// Verify that CreateAIAgentAsync throws ArgumentException when model is empty.
    /// </summary>
    [Fact]
    public async Task CreateAIAgentAsync_WithEmptyModel_ThrowsArgumentExceptionAsync()
    {
        // Arrange
        var client = CreateFakePersistentAgentsClient();
        var options = new ChatClientAgentOptions();

        // Act & Assert
        var exception = await Assert.ThrowsAsync<ArgumentException>(() =>
            client.CreateAIAgentAsync(string.Empty, options));

        Assert.Equal("model", exception.ParamName);
    }

    /// <summary>
    /// Verify that CreateAIAgent with services parameter correctly passes it through to the ChatClientAgent.
    /// </summary>
    [Fact]
    public void CreateAIAgent_WithServices_PassesServicesToAgent()
    {
        // Arrange
        var client = CreateFakePersistentAgentsClient();
        var serviceProvider = new TestServiceProvider();
        const string Model = "test-model";

        // Act
        var agent = client.CreateAIAgent(
            Model,
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
    /// Verify that CreateAIAgentAsync with services parameter correctly passes it through to the ChatClientAgent.
    /// </summary>
    [Fact]
    public async Task CreateAIAgentAsync_WithServices_PassesServicesToAgentAsync()
    {
        // Arrange
        var client = CreateFakePersistentAgentsClient();
        var serviceProvider = new TestServiceProvider();
        const string Model = "test-model";

        // Act
        var agent = await client.CreateAIAgentAsync(
            Model,
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
    /// Verify that GetAIAgent with services parameter correctly passes it through to the ChatClientAgent.
    /// </summary>
    [Fact]
    public void GetAIAgent_WithServices_PassesServicesToAgent()
    {
        // Arrange
        var client = CreateFakePersistentAgentsClient();
        var serviceProvider = new TestServiceProvider();

        // Act
        var agent = client.GetAIAgent("agent_abc123", services: serviceProvider);

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
    /// Verify that GetAIAgentAsync with services parameter correctly passes it through to the ChatClientAgent.
    /// </summary>
    [Fact]
    public async Task GetAIAgentAsync_WithServices_PassesServicesToAgentAsync()
    {
        // Arrange
        var client = CreateFakePersistentAgentsClient();
        var serviceProvider = new TestServiceProvider();

        // Act
        var agent = await client.GetAIAgentAsync("agent_abc123", services: serviceProvider);

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
    /// Verify that CreateAIAgent with both clientFactory and services works correctly.
    /// </summary>
    [Fact]
    public void CreateAIAgent_WithClientFactoryAndServices_AppliesBothCorrectly()
    {
        // Arrange
        var client = CreateFakePersistentAgentsClient();
        var serviceProvider = new TestServiceProvider();
        TestChatClient? testChatClient = null;
        const string Model = "test-model";

        // Act
        var agent = client.CreateAIAgent(
            Model,
            instructions: "Test instructions",
            name: "Test Agent",
            clientFactory: (innerClient) => testChatClient = new TestChatClient(innerClient),
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
    /// Uses reflection to access the FunctionInvocationServices property which is not public.
    /// </summary>
    private static IServiceProvider? GetFunctionInvocationServices(FunctionInvokingChatClient client)
    {
        var property = typeof(FunctionInvokingChatClient).GetProperty(
            "FunctionInvocationServices",
            BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic);
        return property?.GetValue(client) as IServiceProvider;
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

    /// <summary>
    /// A simple test IServiceProvider implementation for testing.
    /// </summary>
    private sealed class TestServiceProvider : IServiceProvider
    {
        public object? GetService(Type serviceType) => null;
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

        ((TypeInfo)typeof(PersistentAgentsClient)).DeclaredFields.First(f => f.Name == "_client")
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
