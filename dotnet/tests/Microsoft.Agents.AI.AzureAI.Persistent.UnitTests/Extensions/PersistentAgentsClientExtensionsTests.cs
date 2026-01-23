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
    public async Task GetAIAgentAsync_WithClientFactory_AppliesFactoryCorrectlyAsync()
    {
        // Arrange
        var client = CreateFakePersistentAgentsClient();
        TestChatClient? testChatClient = null;

        // Act
        var agent = await client.GetAIAgentAsync(
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
    public async Task GetAIAgentAsync_WithoutClientFactory_WorksNormallyAsync()
    {
        // Arrange
        var client = CreateFakePersistentAgentsClient();

        // Act
        var agent = await client.GetAIAgentAsync(agentId: "test-agent-id");

        // Assert
        Assert.NotNull(agent);
        var retrievedTestClient = agent.GetService<TestChatClient>();
        Assert.Null(retrievedTestClient);
    }

    /// <summary>
    /// Verify that GetAIAgent with null clientFactory works normally.
    /// </summary>
    [Fact]
    public async Task GetAIAgentAsync_WithNullClientFactory_WorksNormallyAsync()
    {
        // Arrange
        PersistentAgentsClient client = CreateFakePersistentAgentsClient();

        // Act
        var agent = await client.GetAIAgentAsync(agentId: "test-agent-id", clientFactory: null);

        // Assert
        Assert.NotNull(agent);
        var retrievedTestClient = agent.GetService<TestChatClient>();
        Assert.Null(retrievedTestClient);
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
        var agent = client.AsAIAgent(response, options);

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
        var agent = client.AsAIAgent(persistentAgent, options);

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
        var agent = client.AsAIAgent(persistentAgent, options);

        // Assert
        Assert.NotNull(agent);
        Assert.Equal("Original Name", agent.Name);
        Assert.Equal("Original Description", agent.Description);
        Assert.Equal("Original Instructions", agent.Instructions);
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
        var agent = client.AsAIAgent(
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
            client.AsAIAgent(null!, options));

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
            client.AsAIAgent((PersistentAgent)null!, options));

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
            client.AsAIAgent(persistentAgent, (ChatClientAgentOptions)null!));

        Assert.Equal("options", exception.ParamName);
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
    public async Task CreateAIAgentAsync_WithClientFactoryAndServices_AppliesBothCorrectlyAsync()
    {
        // Arrange
        var client = CreateFakePersistentAgentsClient();
        var serviceProvider = new TestServiceProvider();
        TestChatClient? testChatClient = null;
        const string Model = "test-model";

        // Act
        var agent = await client.CreateAIAgentAsync(
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
    /// Verify that AsAIAgent with Response and ChatOptions throws ArgumentNullException when response is null.
    /// </summary>
    [Fact]
    public void AsAIAgent_WithNullResponseAndChatOptions_ThrowsArgumentNullException()
    {
        // Arrange
        PersistentAgentsClient client = CreateFakePersistentAgentsClient();

        // Act & Assert
        var exception = Assert.Throws<ArgumentNullException>(() =>
            client.AsAIAgent(persistentAgentResponse: null!, chatOptions: new ChatOptions()));

        Assert.Equal("persistentAgentResponse", exception.ParamName);
    }

    /// <summary>
    /// Verify that AsAIAgent with PersistentAgent and ChatOptions throws ArgumentNullException when client is null.
    /// </summary>
    [Fact]
    public void AsAIAgent_WithNullClientAndChatOptions_ThrowsArgumentNullException()
    {
        // Arrange
        PersistentAgent persistentAgent = ModelReaderWriter.Read<PersistentAgent>(BinaryData.FromString("""{"id": "agent_abc123"}"""))!;

        // Act & Assert
        var exception = Assert.Throws<ArgumentNullException>(() =>
            ((PersistentAgentsClient)null!).AsAIAgent(persistentAgent, chatOptions: new ChatOptions()));

        Assert.Equal("persistentAgentsClient", exception.ParamName);
    }

    /// <summary>
    /// Verify that AsAIAgent with PersistentAgent and ChatOptions throws ArgumentNullException when persistentAgent is null.
    /// </summary>
    [Fact]
    public void AsAIAgent_WithNullPersistentAgentAndChatOptions_ThrowsArgumentNullException()
    {
        // Arrange
        PersistentAgentsClient client = CreateFakePersistentAgentsClient();

        // Act & Assert
        var exception = Assert.Throws<ArgumentNullException>(() =>
            client.AsAIAgent((PersistentAgent)null!, chatOptions: new ChatOptions()));

        Assert.Equal("persistentAgentMetadata", exception.ParamName);
    }

    /// <summary>
    /// Verify that AsAIAgent with Response and ChatOptions propagates instructions from agent metadata when chatOptions is null.
    /// </summary>
    [Fact]
    public void AsAIAgent_WithResponseAndNullChatOptions_UsesAgentInstructions()
    {
        // Arrange
        PersistentAgentsClient client = CreateFakePersistentAgentsClient();
        PersistentAgent persistentAgent = ModelReaderWriter.Read<PersistentAgent>(BinaryData.FromString("""{"id": "agent_abc123", "name": "Test Agent", "instructions": "Agent Instructions"}"""))!;
        Response<PersistentAgent> response = Response.FromValue(persistentAgent, new FakeResponse());

        // Act
        ChatClientAgent agent = client.AsAIAgent(response, chatOptions: null);

        // Assert
        Assert.NotNull(agent);
        Assert.Equal("Agent Instructions", agent.Instructions);
    }

    /// <summary>
    /// Verify that AsAIAgent with Response and ChatOptions uses agent instructions when chatOptions.Instructions is null.
    /// </summary>
    [Fact]
    public void AsAIAgent_WithResponseAndChatOptionsWithNullInstructions_UsesAgentInstructions()
    {
        // Arrange
        PersistentAgentsClient client = CreateFakePersistentAgentsClient();
        PersistentAgent persistentAgent = ModelReaderWriter.Read<PersistentAgent>(BinaryData.FromString("""{"id": "agent_abc123", "name": "Test Agent", "instructions": "Agent Instructions"}"""))!;
        Response<PersistentAgent> response = Response.FromValue(persistentAgent, new FakeResponse());
        var chatOptions = new ChatOptions { Instructions = null };

        // Act
        ChatClientAgent agent = client.AsAIAgent(response, chatOptions);

        // Assert
        Assert.NotNull(agent);
        Assert.Equal("Agent Instructions", agent.Instructions);
    }

    /// <summary>
    /// Verify that AsAIAgent with Response and ChatOptions does not override chatOptions instructions when set.
    /// </summary>
    [Fact]
    public void AsAIAgent_WithResponseAndChatOptionsWithInstructions_UsesChatOptionsInstructions()
    {
        // Arrange
        PersistentAgentsClient client = CreateFakePersistentAgentsClient();
        PersistentAgent persistentAgent = ModelReaderWriter.Read<PersistentAgent>(BinaryData.FromString("""{"id": "agent_abc123", "name": "Test Agent", "instructions": "Agent Instructions"}"""))!;
        Response<PersistentAgent> response = Response.FromValue(persistentAgent, new FakeResponse());
        var chatOptions = new ChatOptions { Instructions = "ChatOptions Instructions" };

        // Act
        ChatClientAgent agent = client.AsAIAgent(response, chatOptions);

        // Assert
        Assert.NotNull(agent);
        Assert.Equal("ChatOptions Instructions", agent.Instructions);
    }

    /// <summary>
    /// Verify that AsAIAgent with PersistentAgent and ChatOptions applies clientFactory correctly.
    /// </summary>
    [Fact]
    public void AsAIAgent_WithPersistentAgentChatOptionsAndClientFactory_AppliesFactoryCorrectly()
    {
        // Arrange
        PersistentAgentsClient client = CreateFakePersistentAgentsClient();
        PersistentAgent persistentAgent = ModelReaderWriter.Read<PersistentAgent>(BinaryData.FromString("""{"id": "agent_abc123", "name": "Test Agent"}"""))!;
        TestChatClient? testChatClient = null;

        // Act
        ChatClientAgent agent = client.AsAIAgent(
            persistentAgent,
            chatOptions: null,
            clientFactory: (innerClient) => testChatClient = new TestChatClient(innerClient));

        // Assert
        Assert.NotNull(agent);
        TestChatClient? retrievedTestClient = agent.GetService<TestChatClient>();
        Assert.NotNull(retrievedTestClient);
        Assert.Same(testChatClient, retrievedTestClient);
    }

    /// <summary>
    /// Verify that GetAIAgentAsync with options throws ArgumentNullException when options is null.
    /// </summary>
    [Fact]
    public async Task GetAIAgentAsync_WithOptionsAndNullOptions_ThrowsArgumentNullExceptionAsync()
    {
        // Arrange
        PersistentAgentsClient client = CreateFakePersistentAgentsClient();

        // Act & Assert
        ArgumentNullException exception = await Assert.ThrowsAsync<ArgumentNullException>(() =>
            client.GetAIAgentAsync("agent_abc123", (ChatClientAgentOptions)null!));

        Assert.Equal("options", exception.ParamName);
    }

    /// <summary>
    /// Verify that AsAIAgent with options uses agent instructions when options.ChatOptions.Instructions is null.
    /// </summary>
    [Fact]
    public void AsAIAgent_WithOptionsAndNullChatOptionsInstructions_UsesAgentInstructions()
    {
        // Arrange
        PersistentAgentsClient client = CreateFakePersistentAgentsClient();
        PersistentAgent persistentAgent = ModelReaderWriter.Read<PersistentAgent>(BinaryData.FromString("""{"id": "agent_abc123", "name": "Agent Name", "instructions": "Agent Instructions"}"""))!;
        var options = new ChatClientAgentOptions { ChatOptions = new ChatOptions { Instructions = null } };

        // Act
        ChatClientAgent agent = client.AsAIAgent(persistentAgent, options);

        // Assert
        Assert.NotNull(agent);
        Assert.Equal("Agent Instructions", agent.Instructions);
    }

    /// <summary>
    /// Verify that CreateAIAgentAsync with HostedCodeInterpreterTool properly creates agent.
    /// </summary>
    [Fact]
    public async Task CreateAIAgentAsync_WithHostedCodeInterpreterTool_CreatesAgentWithToolAsync()
    {
        // Arrange
        PersistentAgentsClient client = CreateFakePersistentAgentsClient();
        const string Model = "test-model";
        var options = new ChatClientAgentOptions
        {
            Name = "Test Agent",
            ChatOptions = new ChatOptions
            {
                Instructions = "Test instructions",
                Tools = [new HostedCodeInterpreterTool()]
            }
        };

        // Act
        ChatClientAgent agent = await client.CreateAIAgentAsync(Model, options);

        // Assert
        Assert.NotNull(agent);
        Assert.Equal("Test Agent", agent.Name);
    }

    /// <summary>
    /// Verify that CreateAIAgentAsync with HostedCodeInterpreterTool with HostedFileContent input properly creates agent.
    /// </summary>
    [Fact]
    public async Task CreateAIAgentAsync_WithHostedCodeInterpreterToolAndHostedFileContent_CreatesAgentWithToolResourcesAsync()
    {
        // Arrange
        PersistentAgentsClient client = CreateFakePersistentAgentsClient();
        const string Model = "test-model";
        var codeInterpreterTool = new HostedCodeInterpreterTool
        {
            Inputs = [new HostedFileContent("test-file-id")]
        };
        var options = new ChatClientAgentOptions
        {
            Name = "Test Agent",
            ChatOptions = new ChatOptions
            {
                Instructions = "Test instructions",
                Tools = [codeInterpreterTool]
            }
        };

        // Act
        ChatClientAgent agent = await client.CreateAIAgentAsync(Model, options);

        // Assert
        Assert.NotNull(agent);
        Assert.Equal("Test Agent", agent.Name);
    }

    /// <summary>
    /// Verify that CreateAIAgentAsync with HostedFileSearchTool properly creates agent.
    /// </summary>
    [Fact]
    public async Task CreateAIAgentAsync_WithHostedFileSearchTool_CreatesAgentWithToolAsync()
    {
        // Arrange
        PersistentAgentsClient client = CreateFakePersistentAgentsClient();
        const string Model = "test-model";
        var options = new ChatClientAgentOptions
        {
            Name = "Test Agent",
            ChatOptions = new ChatOptions
            {
                Instructions = "Test instructions",
                Tools = [new HostedFileSearchTool()]
            }
        };

        // Act
        ChatClientAgent agent = await client.CreateAIAgentAsync(Model, options);

        // Assert
        Assert.NotNull(agent);
        Assert.Equal("Test Agent", agent.Name);
    }

    /// <summary>
    /// Verify that CreateAIAgentAsync with HostedFileSearchTool with HostedVectorStoreContent input properly creates agent.
    /// </summary>
    [Fact]
    public async Task CreateAIAgentAsync_WithHostedFileSearchToolAndHostedVectorStoreContent_CreatesAgentWithToolResourcesAsync()
    {
        // Arrange
        PersistentAgentsClient client = CreateFakePersistentAgentsClient();
        const string Model = "test-model";
        var fileSearchTool = new HostedFileSearchTool
        {
            MaximumResultCount = 10,
            Inputs = [new HostedVectorStoreContent("test-vector-store-id")]
        };
        var options = new ChatClientAgentOptions
        {
            Name = "Test Agent",
            ChatOptions = new ChatOptions
            {
                Instructions = "Test instructions",
                Tools = [fileSearchTool]
            }
        };

        // Act
        ChatClientAgent agent = await client.CreateAIAgentAsync(Model, options);

        // Assert
        Assert.NotNull(agent);
        Assert.Equal("Test Agent", agent.Name);
    }

    /// <summary>
    /// Verify that CreateAIAgentAsync with HostedWebSearchTool with connectionId properly creates agent.
    /// </summary>
    [Fact]
    public async Task CreateAIAgentAsync_WithHostedWebSearchToolAndConnectionId_CreatesAgentWithToolAsync()
    {
        // Arrange
        PersistentAgentsClient client = CreateFakePersistentAgentsClient();
        const string Model = "test-model";
        var webSearchTool = new HostedWebSearchTool(new Dictionary<string, object?>
        {
            { "connectionId", "test-connection-id" }
        });
        var options = new ChatClientAgentOptions
        {
            Name = "Test Agent",
            ChatOptions = new ChatOptions
            {
                Instructions = "Test instructions",
                Tools = [webSearchTool]
            }
        };

        // Act
        ChatClientAgent agent = await client.CreateAIAgentAsync(Model, options);

        // Assert
        Assert.NotNull(agent);
        Assert.Equal("Test Agent", agent.Name);
    }

    /// <summary>
    /// Verify that CreateAIAgentAsync with HostedWebSearchTool without connectionId falls to default case.
    /// </summary>
    [Fact]
    public async Task CreateAIAgentAsync_WithHostedWebSearchToolWithoutConnectionId_FallsToDefaultCaseAsync()
    {
        // Arrange
        PersistentAgentsClient client = CreateFakePersistentAgentsClient();
        const string Model = "test-model";
        var webSearchTool = new HostedWebSearchTool();
        var options = new ChatClientAgentOptions
        {
            Name = "Test Agent",
            ChatOptions = new ChatOptions
            {
                Instructions = "Test instructions",
                Tools = [webSearchTool]
            }
        };

        // Act
        ChatClientAgent agent = await client.CreateAIAgentAsync(Model, options);

        // Assert
        Assert.NotNull(agent);
        Assert.Equal("Test Agent", agent.Name);
    }

    /// <summary>
    /// Verify that CreateAIAgentAsync with function tools properly categorizes them as other tools.
    /// </summary>
    [Fact]
    public async Task CreateAIAgentAsync_WithFunctionTools_CategorizesAsOtherToolsAsync()
    {
        // Arrange
        PersistentAgentsClient client = CreateFakePersistentAgentsClient();
        const string Model = "test-model";
        AIFunction testFunction = AIFunctionFactory.Create(() => "test", "TestFunction", "A test function");
        var options = new ChatClientAgentOptions
        {
            Name = "Test Agent",
            ChatOptions = new ChatOptions
            {
                Instructions = "Test instructions",
                Tools = [testFunction]
            }
        };

        // Act
        ChatClientAgent agent = await client.CreateAIAgentAsync(Model, options);

        // Assert
        Assert.NotNull(agent);
        Assert.Equal("Test Agent", agent.Name);
    }

    /// <summary>
    /// Verify that CreateAIAgentAsync with multiple tools including functions properly creates agent.
    /// </summary>
    [Fact]
    public async Task CreateAIAgentAsync_WithMixedTools_CreatesAgentWithAllToolsAsync()
    {
        // Arrange
        PersistentAgentsClient client = CreateFakePersistentAgentsClient();
        const string Model = "test-model";
        AIFunction testFunction = AIFunctionFactory.Create(() => "test", "TestFunction", "A test function");
        var options = new ChatClientAgentOptions
        {
            Name = "Test Agent",
            ChatOptions = new ChatOptions
            {
                Instructions = "Test instructions",
                Tools = [new HostedCodeInterpreterTool(), new HostedFileSearchTool(), testFunction]
            }
        };

        // Act
        ChatClientAgent agent = await client.CreateAIAgentAsync(Model, options);

        // Assert
        Assert.NotNull(agent);
        Assert.Equal("Test Agent", agent.Name);
    }

    /// <summary>
    /// Verify that AsAIAgent with Response and Options throws ArgumentNullException when client is null.
    /// </summary>
    [Fact]
    public void AsAIAgent_WithNullClientResponseAndOptions_ThrowsArgumentNullException()
    {
        // Arrange
        PersistentAgent persistentAgent = ModelReaderWriter.Read<PersistentAgent>(BinaryData.FromString("""{"id": "agent_abc123"}"""))!;
        Response<PersistentAgent> response = Response.FromValue(persistentAgent, new FakeResponse());
        var options = new ChatClientAgentOptions();

        // Act & Assert
        ArgumentNullException exception = Assert.Throws<ArgumentNullException>(() =>
            ((PersistentAgentsClient)null!).AsAIAgent(response, options));

        Assert.Equal("persistentAgentsClient", exception.ParamName);
    }

    /// <summary>
    /// Verify that AsAIAgent with PersistentAgent and Options throws ArgumentNullException when client is null.
    /// </summary>
    [Fact]
    public void AsAIAgent_WithNullClientPersistentAgentAndOptions_ThrowsArgumentNullException()
    {
        // Arrange
        PersistentAgent persistentAgent = ModelReaderWriter.Read<PersistentAgent>(BinaryData.FromString("""{"id": "agent_abc123"}"""))!;
        var options = new ChatClientAgentOptions();

        // Act & Assert
        ArgumentNullException exception = Assert.Throws<ArgumentNullException>(() =>
            ((PersistentAgentsClient)null!).AsAIAgent(persistentAgent, options));

        Assert.Equal("persistentAgentsClient", exception.ParamName);
    }

    /// <summary>
    /// Verify that AsAIAgent with PersistentAgent and Options applies clientFactory correctly.
    /// </summary>
    [Fact]
    public void AsAIAgent_WithPersistentAgentOptionsAndClientFactory_AppliesFactoryCorrectly()
    {
        // Arrange
        PersistentAgentsClient client = CreateFakePersistentAgentsClient();
        PersistentAgent persistentAgent = ModelReaderWriter.Read<PersistentAgent>(BinaryData.FromString("""{"id": "agent_abc123", "name": "Test Agent"}"""))!;
        var options = new ChatClientAgentOptions { Name = "Test Agent" };
        TestChatClient? testChatClient = null;

        // Act
        ChatClientAgent agent = client.AsAIAgent(
            persistentAgent,
            options,
            clientFactory: (innerClient) => testChatClient = new TestChatClient(innerClient));

        // Assert
        Assert.NotNull(agent);
        Assert.Equal("Test Agent", agent.Name);
        TestChatClient? retrievedTestClient = agent.GetService<TestChatClient>();
        Assert.NotNull(retrievedTestClient);
        Assert.Same(testChatClient, retrievedTestClient);
    }

    /// <summary>
    /// Verify that AsAIAgent with Response and Options applies clientFactory correctly.
    /// </summary>
    [Fact]
    public void AsAIAgent_WithResponseOptionsAndClientFactory_AppliesFactoryCorrectly()
    {
        // Arrange
        PersistentAgentsClient client = CreateFakePersistentAgentsClient();
        PersistentAgent persistentAgent = ModelReaderWriter.Read<PersistentAgent>(BinaryData.FromString("""{"id": "agent_abc123", "name": "Test Agent"}"""))!;
        Response<PersistentAgent> response = Response.FromValue(persistentAgent, new FakeResponse());
        var options = new ChatClientAgentOptions { Name = "Test Agent" };
        TestChatClient? testChatClient = null;

        // Act
        ChatClientAgent agent = client.AsAIAgent(
            response,
            options,
            clientFactory: (innerClient) => testChatClient = new TestChatClient(innerClient));

        // Assert
        Assert.NotNull(agent);
        Assert.Equal("Test Agent", agent.Name);
        TestChatClient? retrievedTestClient = agent.GetService<TestChatClient>();
        Assert.NotNull(retrievedTestClient);
        Assert.Same(testChatClient, retrievedTestClient);
    }

    /// <summary>
    /// Verify that AsAIAgent with Response and ChatOptions applies clientFactory correctly.
    /// </summary>
    [Fact]
    public void AsAIAgent_WithResponseChatOptionsAndClientFactory_AppliesFactoryCorrectly()
    {
        // Arrange
        PersistentAgentsClient client = CreateFakePersistentAgentsClient();
        PersistentAgent persistentAgent = ModelReaderWriter.Read<PersistentAgent>(BinaryData.FromString("""{"id": "agent_abc123", "name": "Test Agent"}"""))!;
        Response<PersistentAgent> response = Response.FromValue(persistentAgent, new FakeResponse());
        TestChatClient? testChatClient = null;

        // Act
        ChatClientAgent agent = client.AsAIAgent(
            response,
            chatOptions: null,
            clientFactory: (innerClient) => testChatClient = new TestChatClient(innerClient));

        // Assert
        Assert.NotNull(agent);
        TestChatClient? retrievedTestClient = agent.GetService<TestChatClient>();
        Assert.NotNull(retrievedTestClient);
        Assert.Same(testChatClient, retrievedTestClient);
    }

    /// <summary>
    /// Verify that GetAIAgentAsync with options and clientFactory applies the factory correctly.
    /// </summary>
    [Fact]
    public async Task GetAIAgentAsync_WithOptionsAndClientFactory_AppliesFactoryCorrectlyAsync()
    {
        // Arrange
        PersistentAgentsClient client = CreateFakePersistentAgentsClient();
        TestChatClient? testChatClient = null;
        var options = new ChatClientAgentOptions { Name = "Test Agent" };

        // Act
        ChatClientAgent agent = await client.GetAIAgentAsync(
            agentId: "test-agent-id",
            options,
            clientFactory: (innerClient) => testChatClient = new TestChatClient(innerClient));

        // Assert
        Assert.NotNull(agent);
        TestChatClient? retrievedTestClient = agent.GetService<TestChatClient>();
        Assert.NotNull(retrievedTestClient);
        Assert.Same(testChatClient, retrievedTestClient);
    }

    /// <summary>
    /// Verify that GetAIAgentAsync with options and services passes services correctly.
    /// </summary>
    [Fact]
    public async Task GetAIAgentAsync_WithOptionsAndServices_PassesServicesToAgentAsync()
    {
        // Arrange
        PersistentAgentsClient client = CreateFakePersistentAgentsClient();
        var serviceProvider = new TestServiceProvider();
        var options = new ChatClientAgentOptions { Name = "Test Agent" };

        // Act
        ChatClientAgent agent = await client.GetAIAgentAsync("agent_abc123", options, services: serviceProvider);

        // Assert
        Assert.NotNull(agent);

        // Verify the IServiceProvider was passed through to the FunctionInvokingChatClient
        IChatClient? chatClient = agent.GetService<IChatClient>();
        Assert.NotNull(chatClient);
        FunctionInvokingChatClient? functionInvokingClient = chatClient.GetService<FunctionInvokingChatClient>();
        Assert.NotNull(functionInvokingClient);
        Assert.Same(serviceProvider, GetFunctionInvocationServices(functionInvokingClient));
    }

    /// <summary>
    /// Verify that CreateAIAgentAsync with options and services passes services correctly.
    /// </summary>
    [Fact]
    public async Task CreateAIAgentAsync_WithOptionsAndServices_PassesServicesToAgentAsync()
    {
        // Arrange
        PersistentAgentsClient client = CreateFakePersistentAgentsClient();
        var serviceProvider = new TestServiceProvider();
        const string Model = "test-model";
        var options = new ChatClientAgentOptions { Name = "Test Agent" };

        // Act
        ChatClientAgent agent = await client.CreateAIAgentAsync(Model, options, services: serviceProvider);

        // Assert
        Assert.NotNull(agent);

        // Verify the IServiceProvider was passed through to the FunctionInvokingChatClient
        IChatClient? chatClient = agent.GetService<IChatClient>();
        Assert.NotNull(chatClient);
        FunctionInvokingChatClient? functionInvokingClient = chatClient.GetService<FunctionInvokingChatClient>();
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
