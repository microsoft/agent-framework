// Copyright (c) Microsoft. All rights reserved.

using System;
using System.ClientModel;
using System.ClientModel.Primitives;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Net;
using System.Net.Http;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Azure.AI.Projects;
using Azure.AI.Projects.OpenAI;
using Microsoft.Extensions.AI;
using Moq;
using OpenAI.Responses;

namespace Microsoft.Agents.AI.AzureAI.UnitTests;

/// <summary>
/// Unit tests for the <see cref="AzureAIProjectChatClientExtensions"/> class.
/// </summary>
public sealed class AzureAIProjectChatClientExtensionsTests
{
    #region GetAIAgent(AIProjectClient, AgentRecord) Tests

    /// <summary>
    /// Verify that GetAIAgent throws ArgumentNullException when AIProjectClient is null.
    /// </summary>
    [Fact]
    public void GetAIAgent_WithAgentRecord_WithNullClient_ThrowsArgumentNullException()
    {
        // Arrange
        AIProjectClient? client = null;
        AgentRecord agentRecord = this.CreateTestAgentRecord();

        // Act & Assert
        var exception = Assert.Throws<ArgumentNullException>(() =>
            client!.GetAIAgent(agentRecord));

        Assert.Equal("aiProjectClient", exception.ParamName);
    }

    /// <summary>
    /// Verify that GetAIAgent throws ArgumentNullException when agentRecord is null.
    /// </summary>
    [Fact]
    public void GetAIAgent_WithAgentRecord_WithNullAgentRecord_ThrowsArgumentNullException()
    {
        // Arrange
        var mockClient = new Mock<AIProjectClient>();

        // Act & Assert
        var exception = Assert.Throws<ArgumentNullException>(() =>
            mockClient.Object.GetAIAgent((AgentRecord)null!));

        Assert.Equal("agentRecord", exception.ParamName);
    }

    /// <summary>
    /// Verify that GetAIAgent with AgentRecord creates a valid agent.
    /// </summary>
    [Fact]
    public void GetAIAgent_WithAgentRecord_CreatesValidAgent()
    {
        // Arrange
        AIProjectClient client = this.CreateTestAgentClient();
        AgentRecord agentRecord = this.CreateTestAgentRecord();

        // Act
        var agent = client.GetAIAgent(agentRecord);

        // Assert
        Assert.NotNull(agent);
        Assert.Equal("agent_abc123", agent.Name);
    }

    /// <summary>
    /// Verify that GetAIAgent with AgentRecord and clientFactory applies the factory.
    /// </summary>
    [Fact]
    public void GetAIAgent_WithAgentRecord_WithClientFactory_AppliesFactoryCorrectly()
    {
        // Arrange
        AIProjectClient client = this.CreateTestAgentClient();
        AgentRecord agentRecord = this.CreateTestAgentRecord();
        TestChatClient? testChatClient = null;

        // Act
        var agent = client.GetAIAgent(
            agentRecord,
            clientFactory: (innerClient) => testChatClient = new TestChatClient(innerClient));

        // Assert
        Assert.NotNull(agent);
        var retrievedTestClient = agent.GetService<TestChatClient>();
        Assert.NotNull(retrievedTestClient);
        Assert.Same(testChatClient, retrievedTestClient);
    }

    #endregion

    #region GetAIAgent(AIProjectClient, AgentVersion) Tests

    /// <summary>
    /// Verify that GetAIAgent throws ArgumentNullException when AIProjectClient is null.
    /// </summary>
    [Fact]
    public void GetAIAgent_WithAgentVersion_WithNullClient_ThrowsArgumentNullException()
    {
        // Arrange
        AIProjectClient? client = null;
        AgentVersion agentVersion = this.CreateTestAgentVersion();

        // Act & Assert
        var exception = Assert.Throws<ArgumentNullException>(() =>
            client!.GetAIAgent(agentVersion));

        Assert.Equal("aiProjectClient", exception.ParamName);
    }

    /// <summary>
    /// Verify that GetAIAgent throws ArgumentNullException when agentVersion is null.
    /// </summary>
    [Fact]
    public void GetAIAgent_WithAgentVersion_WithNullAgentVersion_ThrowsArgumentNullException()
    {
        // Arrange
        var mockClient = new Mock<AIProjectClient>();

        // Act & Assert
        var exception = Assert.Throws<ArgumentNullException>(() =>
            mockClient.Object.GetAIAgent((AgentVersion)null!));

        Assert.Equal("agentVersion", exception.ParamName);
    }

    /// <summary>
    /// Verify that GetAIAgent with AgentVersion creates a valid agent.
    /// </summary>
    [Fact]
    public void GetAIAgent_WithAgentVersion_CreatesValidAgent()
    {
        // Arrange
        AIProjectClient client = this.CreateTestAgentClient();
        AgentVersion agentVersion = this.CreateTestAgentVersion();

        // Act
        var agent = client.GetAIAgent(agentVersion);

        // Assert
        Assert.NotNull(agent);
        Assert.Equal("agent_abc123", agent.Name);
    }

    /// <summary>
    /// Verify that GetAIAgent with AgentVersion and clientFactory applies the factory.
    /// </summary>
    [Fact]
    public void GetAIAgent_WithAgentVersion_WithClientFactory_AppliesFactoryCorrectly()
    {
        // Arrange
        AIProjectClient client = this.CreateTestAgentClient();
        AgentVersion agentVersion = this.CreateTestAgentVersion();
        TestChatClient? testChatClient = null;

        // Act
        var agent = client.GetAIAgent(
            agentVersion,
            clientFactory: (innerClient) => testChatClient = new TestChatClient(innerClient));

        // Assert
        Assert.NotNull(agent);
        var retrievedTestClient = agent.GetService<TestChatClient>();
        Assert.NotNull(retrievedTestClient);
        Assert.Same(testChatClient, retrievedTestClient);
    }

    /// <summary>
    /// Verify that GetAIAgent with requireInvocableTools=true enforces invocable tools.
    /// </summary>
    [Fact]
    public void GetAIAgent_WithAgentVersion_WithRequireInvocableToolsTrue_EnforcesInvocableTools()
    {
        // Arrange
        AIProjectClient client = this.CreateTestAgentClient();
        AgentVersion agentVersion = this.CreateTestAgentVersion();
        var tools = new List<AITool>
        {
            AIFunctionFactory.Create(() => "test", "test_function", "A test function")
        };

        // Act
        var agent = client.GetAIAgent(agentVersion, tools: tools);

        // Assert
        Assert.NotNull(agent);
        Assert.IsType<ChatClientAgent>(agent);
    }

    /// <summary>
    /// Verify that GetAIAgent with requireInvocableTools=false allows declarative functions.
    /// </summary>
    [Fact]
    public void GetAIAgent_WithAgentVersion_WithRequireInvocableToolsFalse_AllowsDeclarativeFunctions()
    {
        // Arrange
        AIProjectClient client = this.CreateTestAgentClient();
        AgentVersion agentVersion = this.CreateTestAgentVersion();

        // Act - should not throw even without tools when requireInvocableTools is false
        var agent = client.GetAIAgent(agentVersion);

        // Assert
        Assert.NotNull(agent);
        Assert.IsType<ChatClientAgent>(agent);
    }

    #endregion

    #region GetAIAgent(AIProjectClient, ChatClientAgentOptions) Tests

    /// <summary>
    /// Verify that GetAIAgent with ChatClientAgentOptions throws ArgumentNullException when client is null.
    /// </summary>
    [Fact]
    public void GetAIAgent_WithOptions_WithNullClient_ThrowsArgumentNullException()
    {
        // Arrange
        AIProjectClient? client = null;
        var options = new ChatClientAgentOptions { Name = "test-agent" };

        // Act & Assert
        var exception = Assert.Throws<ArgumentNullException>(() =>
            client!.GetAIAgent(options));

        Assert.Equal("aiProjectClient", exception.ParamName);
    }

    /// <summary>
    /// Verify that GetAIAgent with ChatClientAgentOptions throws ArgumentNullException when options is null.
    /// </summary>
    [Fact]
    public void GetAIAgent_WithOptions_WithNullOptions_ThrowsArgumentNullException()
    {
        // Arrange
        var mockClient = new Mock<AIProjectClient>();

        // Act & Assert
        var exception = Assert.Throws<ArgumentNullException>(() =>
            mockClient.Object.GetAIAgent((ChatClientAgentOptions)null!));

        Assert.Equal("options", exception.ParamName);
    }

    /// <summary>
    /// Verify that GetAIAgent with ChatClientAgentOptions throws ArgumentException when options.Name is null.
    /// </summary>
    [Fact]
    public void GetAIAgent_WithOptions_WithoutName_ThrowsArgumentException()
    {
        // Arrange
        AIProjectClient client = this.CreateTestAgentClient();
        var options = new ChatClientAgentOptions();

        // Act & Assert
        var exception = Assert.Throws<ArgumentException>(() =>
            client.GetAIAgent(options));

        Assert.Contains("Agent name must be provided", exception.Message);
    }

    /// <summary>
    /// Verify that GetAIAgent with ChatClientAgentOptions creates a valid agent.
    /// </summary>
    [Fact]
    public void GetAIAgent_WithOptions_CreatesValidAgent()
    {
        // Arrange
        AIProjectClient client = this.CreateTestAgentClient(agentName: "test-agent");
        var options = new ChatClientAgentOptions { Name = "test-agent" };

        // Act
        var agent = client.GetAIAgent(options);

        // Assert
        Assert.NotNull(agent);
        Assert.Equal("test-agent", agent.Name);
    }

    /// <summary>
    /// Verify that GetAIAgent with ChatClientAgentOptions and clientFactory applies the factory.
    /// </summary>
    [Fact]
    public void GetAIAgent_WithOptions_WithClientFactory_AppliesFactoryCorrectly()
    {
        // Arrange
        AIProjectClient client = this.CreateTestAgentClient(agentName: "test-agent");
        var options = new ChatClientAgentOptions { Name = "test-agent" };
        TestChatClient? testChatClient = null;

        // Act
        var agent = client.GetAIAgent(
            options,
            clientFactory: (innerClient) => testChatClient = new TestChatClient(innerClient));

        // Assert
        Assert.NotNull(agent);
        var retrievedTestClient = agent.GetService<TestChatClient>();
        Assert.NotNull(retrievedTestClient);
        Assert.Same(testChatClient, retrievedTestClient);
    }

    #endregion

    #region GetAIAgentAsync(AIProjectClient, ChatClientAgentOptions) Tests

    /// <summary>
    /// Verify that GetAIAgentAsync with ChatClientAgentOptions throws ArgumentNullException when client is null.
    /// </summary>
    [Fact]
    public async Task GetAIAgentAsync_WithOptions_WithNullClient_ThrowsArgumentNullExceptionAsync()
    {
        // Arrange
        AIProjectClient? client = null;
        var options = new ChatClientAgentOptions { Name = "test-agent" };

        // Act & Assert
        var exception = await Assert.ThrowsAsync<ArgumentNullException>(() =>
            client!.GetAIAgentAsync(options));

        Assert.Equal("aiProjectClient", exception.ParamName);
    }

    /// <summary>
    /// Verify that GetAIAgentAsync with ChatClientAgentOptions throws ArgumentNullException when options is null.
    /// </summary>
    [Fact]
    public async Task GetAIAgentAsync_WithOptions_WithNullOptions_ThrowsArgumentNullExceptionAsync()
    {
        // Arrange
        var mockClient = new Mock<AIProjectClient>();

        // Act & Assert
        var exception = await Assert.ThrowsAsync<ArgumentNullException>(() =>
            mockClient.Object.GetAIAgentAsync((ChatClientAgentOptions)null!));

        Assert.Equal("options", exception.ParamName);
    }

    /// <summary>
    /// Verify that GetAIAgentAsync with ChatClientAgentOptions creates a valid agent.
    /// </summary>
    [Fact]
    public async Task GetAIAgentAsync_WithOptions_CreatesValidAgentAsync()
    {
        // Arrange
        AIProjectClient client = this.CreateTestAgentClient(agentName: "test-agent");
        var options = new ChatClientAgentOptions { Name = "test-agent" };

        // Act
        var agent = await client.GetAIAgentAsync(options);

        // Assert
        Assert.NotNull(agent);
        Assert.Equal("test-agent", agent.Name);
    }

    #endregion

    #region GetAIAgent(AIProjectClient, string) Tests

    /// <summary>
    /// Verify that GetAIAgent throws ArgumentNullException when AIProjectClient is null.
    /// </summary>
    [Fact]
    public void GetAIAgent_ByName_WithNullClient_ThrowsArgumentNullException()
    {
        // Arrange
        AIProjectClient? client = null;

        // Act & Assert
        var exception = Assert.Throws<ArgumentNullException>(() =>
            client!.GetAIAgent("test-agent"));

        Assert.Equal("aiProjectClient", exception.ParamName);
    }

    /// <summary>
    /// Verify that GetAIAgent throws ArgumentNullException when name is null.
    /// </summary>
    [Fact]
    public void GetAIAgent_ByName_WithNullName_ThrowsArgumentNullException()
    {
        // Arrange
        var mockClient = new Mock<AIProjectClient>();

        // Act & Assert
        var exception = Assert.Throws<ArgumentNullException>(() =>
            mockClient.Object.GetAIAgent((string)null!));

        Assert.Equal("name", exception.ParamName);
    }

    /// <summary>
    /// Verify that GetAIAgent throws ArgumentException when name is empty.
    /// </summary>
    [Fact]
    public void GetAIAgent_ByName_WithEmptyName_ThrowsArgumentException()
    {
        // Arrange
        var mockClient = new Mock<AIProjectClient>();

        // Act & Assert
        var exception = Assert.Throws<ArgumentException>(() =>
            mockClient.Object.GetAIAgent(string.Empty));

        Assert.Equal("name", exception.ParamName);
    }

    /// <summary>
    /// Verify that GetAIAgent throws InvalidOperationException when agent is not found.
    /// </summary>
    [Fact]
    public void GetAIAgent_ByName_WithNonExistentAgent_ThrowsInvalidOperationException()
    {
        // Arrange
        var mockAgentOperations = new Mock<AIProjectAgentsOperations>();
        mockAgentOperations
            .Setup(c => c.GetAgent(It.IsAny<string>(), It.IsAny<RequestOptions>()))
            .Returns(ClientResult.FromOptionalValue((AgentRecord)null!, new MockPipelineResponse(200, BinaryData.FromString("null"))));

        var mockClient = new Mock<AIProjectClient>();
        mockClient.SetupGet(x => x.Agents).Returns(mockAgentOperations.Object);
        mockClient.Setup(x => x.GetConnection(It.IsAny<string>())).Returns(new ClientConnection("fake-connection-id", "http://localhost", ClientPipeline.Create(), CredentialKind.None));

        // Act & Assert
        var exception = Assert.Throws<InvalidOperationException>(() =>
            mockClient.Object.GetAIAgent("non-existent-agent"));

        Assert.Contains("not found", exception.Message);
    }

    #endregion

    #region GetAIAgentAsync(AIProjectClient, string) Tests

    /// <summary>
    /// Verify that GetAIAgentAsync throws ArgumentNullException when AIProjectClient is null.
    /// </summary>
    [Fact]
    public async Task GetAIAgentAsync_ByName_WithNullClient_ThrowsArgumentNullExceptionAsync()
    {
        // Arrange
        AIProjectClient? client = null;

        // Act & Assert
        var exception = await Assert.ThrowsAsync<ArgumentNullException>(() =>
            client!.GetAIAgentAsync("test-agent"));

        Assert.Equal("aiProjectClient", exception.ParamName);
    }

    /// <summary>
    /// Verify that GetAIAgentAsync throws ArgumentNullException when name is null.
    /// </summary>
    [Fact]
    public async Task GetAIAgentAsync_ByName_WithNullName_ThrowsArgumentNullExceptionAsync()
    {
        // Arrange
        var mockClient = new Mock<AIProjectClient>();

        // Act & Assert
        var exception = await Assert.ThrowsAsync<ArgumentNullException>(() =>
            mockClient.Object.GetAIAgentAsync(name: null!));

        Assert.Equal("name", exception.ParamName);
    }

    /// <summary>
    /// Verify that GetAIAgentAsync throws InvalidOperationException when agent is not found.
    /// </summary>
    [Fact]
    public async Task GetAIAgentAsync_ByName_WithNonExistentAgent_ThrowsInvalidOperationExceptionAsync()
    {
        // Arrange
        var mockAgentOperations = new Mock<AIProjectAgentsOperations>();
        mockAgentOperations
            .Setup(c => c.GetAgentAsync(It.IsAny<string>(), It.IsAny<RequestOptions>()))
            .ReturnsAsync(ClientResult.FromOptionalValue((AgentRecord)null!, new MockPipelineResponse(200, BinaryData.FromString("null"))));

        var mockClient = new Mock<AIProjectClient>();
        mockClient.SetupGet(c => c.Agents).Returns(mockAgentOperations.Object);
        mockClient.Setup(x => x.GetConnection(It.IsAny<string>())).Returns(new ClientConnection("fake-connection-id", "http://localhost", ClientPipeline.Create(), CredentialKind.None));

        // Act & Assert
        var exception = await Assert.ThrowsAsync<InvalidOperationException>(() =>
            mockClient.Object.GetAIAgentAsync("non-existent-agent"));

        Assert.Contains("not found", exception.Message);
    }

    #endregion

    #region GetAIAgent(AIProjectClient, AgentRecord) with tools Tests

    /// <summary>
    /// Verify that GetAIAgent with additional tools when the definition has no tools does not throw and results in an agent with no tools.
    /// </summary>
    [Fact]
    public void GetAIAgent_WithAgentRecordAndAdditionalTools_WhenDefinitionHasNoTools_ShouldNotThrow()
    {
        // Arrange
        AIProjectClient client = this.CreateTestAgentClient();
        AgentRecord agentRecord = this.CreateTestAgentRecord();
        var tools = new List<AITool>
        {
            AIFunctionFactory.Create(() => "test", "test_function", "A test function")
        };

        // Act
        var agent = client.GetAIAgent(agentRecord, tools: tools);

        // Assert
        Assert.NotNull(agent);
        Assert.IsType<ChatClientAgent>(agent);
        var chatClient = agent.GetService<IChatClient>();
        Assert.NotNull(chatClient);
        var agentVersion = chatClient.GetService<AgentVersion>();
        Assert.NotNull(agentVersion);
        var definition = Assert.IsType<PromptAgentDefinition>(agentVersion.Definition);
        Assert.Empty(definition.Tools);
    }

    /// <summary>
    /// Verify that GetAIAgent with null tools works correctly.
    /// </summary>
    [Fact]
    public void GetAIAgent_WithAgentRecordAndNullTools_WorksCorrectly()
    {
        // Arrange
        AIProjectClient client = this.CreateTestAgentClient();
        AgentRecord agentRecord = this.CreateTestAgentRecord();

        // Act
        var agent = client.GetAIAgent(agentRecord, tools: null);

        // Assert
        Assert.NotNull(agent);
        Assert.Equal("agent_abc123", agent.Name);
    }

    #endregion

    #region GetAIAgentAsync(AIProjectClient, string) with tools Tests

    /// <summary>
    /// Verify that GetAIAgentAsync with tools parameter creates an agent.
    /// </summary>
    [Fact]
    public async Task GetAIAgentAsync_WithNameAndTools_CreatesAgentAsync()
    {
        // Arrange
        AIProjectClient client = this.CreateTestAgentClient();
        var tools = new List<AITool>
        {
            AIFunctionFactory.Create(() => "test", "test_function", "A test function")
        };

        // Act
        var agent = await client.GetAIAgentAsync("test-agent", tools: tools);

        // Assert
        Assert.NotNull(agent);
        Assert.IsType<ChatClientAgent>(agent);
    }

    #endregion

    #region CreateAIAgent(AIProjectClient, string, string) Tests

    /// <summary>
    /// Verify that CreateAIAgent throws ArgumentNullException when AIProjectClient is null.
    /// </summary>
    [Fact]
    public void CreateAIAgent_WithBasicParams_WithNullClient_ThrowsArgumentNullException()
    {
        // Arrange
        AIProjectClient? client = null;

        // Act & Assert
        var exception = Assert.Throws<ArgumentNullException>(() =>
            client!.CreateAIAgent("test-agent", "model", "instructions"));

        Assert.Equal("aiProjectClient", exception.ParamName);
    }

    /// <summary>
    /// Verify that CreateAIAgent throws ArgumentNullException when name is null.
    /// </summary>
    [Fact]
    public void CreateAIAgent_WithBasicParams_WithNullName_ThrowsArgumentNullException()
    {
        // Arrange
        var mockClient = new Mock<AIProjectClient>();

        // Act & Assert
        var exception = Assert.Throws<ArgumentNullException>(() =>
            mockClient.Object.CreateAIAgent(null!, "model", "instructions"));

        Assert.Equal("name", exception.ParamName);
    }

    #endregion

    #region CreateAIAgent(AIProjectClient, string, AgentDefinition) Tests

    /// <summary>
    /// Verify that CreateAIAgent throws ArgumentNullException when AIProjectClient is null.
    /// </summary>
    [Fact]
    public void CreateAIAgent_WithAgentDefinition_WithNullClient_ThrowsArgumentNullException()
    {
        // Arrange
        AIProjectClient? client = null;
        var definition = new PromptAgentDefinition("test-model");
        var options = new AgentVersionCreationOptions(definition);

        // Act & Assert
        var exception = Assert.Throws<ArgumentNullException>(() =>
            client!.CreateAIAgent("test-agent", options));

        Assert.Equal("aiProjectClient", exception.ParamName);
    }

    /// <summary>
    /// Verify that CreateAIAgent throws ArgumentNullException when name is null.
    /// </summary>
    [Fact]
    public void CreateAIAgent_WithAgentDefinition_WithNullName_ThrowsArgumentNullException()
    {
        // Arrange
        var mockClient = new Mock<AIProjectClient>();
        var definition = new PromptAgentDefinition("test-model");
        var options = new AgentVersionCreationOptions(definition);

        // Act & Assert
        var exception = Assert.Throws<ArgumentNullException>(() =>
            mockClient.Object.CreateAIAgent(null!, options));

        Assert.Equal("name", exception.ParamName);
    }

    /// <summary>
    /// Verify that CreateAIAgent throws ArgumentNullException when creationOptions is null.
    /// </summary>
    [Fact]
    public void CreateAIAgent_WithAgentDefinition_WithNullDefinition_ThrowsArgumentNullException()
    {
        // Arrange
        var mockClient = new Mock<AIProjectClient>();

        // Act & Assert
        var exception = Assert.Throws<ArgumentNullException>(() =>
            mockClient.Object.CreateAIAgent("test-agent", (AgentVersionCreationOptions)null!));

        Assert.Equal("creationOptions", exception.ParamName);
    }

    #endregion

    #region CreateAIAgent(AIProjectClient, ChatClientAgentOptions, string) Tests

    /// <summary>
    /// Verify that CreateAIAgent throws ArgumentNullException when AIProjectClient is null.
    /// </summary>
    [Fact]
    public void CreateAIAgent_WithOptions_WithNullClient_ThrowsArgumentNullException()
    {
        // Arrange
        AIProjectClient? client = null;
        var options = new ChatClientAgentOptions { Name = "test-agent" };

        // Act & Assert
        var exception = Assert.Throws<ArgumentNullException>(() =>
            client!.CreateAIAgent("model", options));

        Assert.Equal("aiProjectClient", exception.ParamName);
    }

    /// <summary>
    /// Verify that CreateAIAgent throws ArgumentNullException when options is null.
    /// </summary>
    [Fact]
    public void CreateAIAgent_WithOptions_WithNullOptions_ThrowsArgumentNullException()
    {
        // Arrange
        var mockClient = new Mock<AIProjectClient>();

        // Act & Assert
        var exception = Assert.Throws<ArgumentNullException>(() =>
            mockClient.Object.CreateAIAgent("model", (ChatClientAgentOptions)null!));

        Assert.Equal("options", exception.ParamName);
    }

    /// <summary>
    /// Verify that CreateAIAgent throws ArgumentNullException when model is null.
    /// </summary>
    [Fact]
    public void CreateAIAgent_WithOptions_WithNullModel_ThrowsArgumentNullException()
    {
        // Arrange
        var mockClient = new Mock<AIProjectClient>();
        var options = new ChatClientAgentOptions { Name = "test-agent" };

        // Act & Assert
        var exception = Assert.Throws<ArgumentNullException>(() =>
            mockClient.Object.CreateAIAgent(null!, options));

        Assert.Equal("model", exception.ParamName);
    }

    /// <summary>
    /// Verify that CreateAIAgent throws ArgumentNullException when options.Name is null.
    /// </summary>
    [Fact]
    public void CreateAIAgent_WithOptions_WithoutName_ThrowsException()
    {
        // Arrange
        AIProjectClient client = this.CreateTestAgentClient();
        var options = new ChatClientAgentOptions();

        // Act & Assert
        var exception = Assert.Throws<ArgumentException>(() =>
            client.CreateAIAgent("test-model", options));

        Assert.Contains("Agent name must be provided", exception.Message);
    }

    /// <summary>
    /// Verify that CreateAIAgent with model and options creates a valid agent.
    /// </summary>
    [Fact]
    public void CreateAIAgent_WithModelAndOptions_CreatesValidAgent()
    {
        // Arrange
        AIProjectClient client = this.CreateTestAgentClient(agentName: "test-agent", instructions: "Test instructions");
        var options = new ChatClientAgentOptions
        {
            Name = "test-agent",
            ChatOptions = new() { Instructions = "Test instructions" }
        };

        // Act
        var agent = client.CreateAIAgent("test-model", options);

        // Assert
        Assert.NotNull(agent);
        Assert.Equal("test-agent", agent.Name);
        Assert.Equal("Test instructions", agent.Instructions);
    }

    /// <summary>
    /// Verify that CreateAIAgent with model and options and clientFactory applies the factory.
    /// </summary>
    [Fact]
    public void CreateAIAgent_WithModelAndOptions_WithClientFactory_AppliesFactoryCorrectly()
    {
        // Arrange
        AIProjectClient client = this.CreateTestAgentClient(agentName: "test-agent", instructions: "Test instructions");
        var options = new ChatClientAgentOptions
        {
            Name = "test-agent",
            ChatOptions = new() { Instructions = "Test instructions" }
        };
        TestChatClient? testChatClient = null;

        // Act
        var agent = client.CreateAIAgent(
            "test-model",
            options,
            clientFactory: (innerClient) => testChatClient = new TestChatClient(innerClient));

        // Assert
        Assert.NotNull(agent);
        var retrievedTestClient = agent.GetService<TestChatClient>();
        Assert.NotNull(retrievedTestClient);
        Assert.Same(testChatClient, retrievedTestClient);
    }

    /// <summary>
    /// Verify that CreateAIAgentAsync with model and options creates a valid agent.
    /// </summary>
    [Fact]
    public async Task CreateAIAgentAsync_WithModelAndOptions_CreatesValidAgentAsync()
    {
        // Arrange
        AIProjectClient client = this.CreateTestAgentClient(agentName: "test-agent", instructions: "Test instructions");
        var options = new ChatClientAgentOptions
        {
            Name = "test-agent",
            ChatOptions = new() { Instructions = "Test instructions" }
        };

        // Act
        var agent = await client.CreateAIAgentAsync("test-model", options);

        // Assert
        Assert.NotNull(agent);
        Assert.Equal("test-agent", agent.Name);
        Assert.Equal("Test instructions", agent.Instructions);
    }

    /// <summary>
    /// Verify that CreateAIAgentAsync with model and options and clientFactory applies the factory.
    /// </summary>
    [Fact]
    public async Task CreateAIAgentAsync_WithModelAndOptions_WithClientFactory_AppliesFactoryCorrectlyAsync()
    {
        // Arrange
        AIProjectClient client = this.CreateTestAgentClient(agentName: "test-agent", instructions: "Test instructions");
        var options = new ChatClientAgentOptions
        {
            Name = "test-agent",
            ChatOptions = new() { Instructions = "Test instructions" }
        };
        TestChatClient? testChatClient = null;

        // Act
        var agent = await client.CreateAIAgentAsync(
            "test-model",
            options,
            clientFactory: (innerClient) => testChatClient = new TestChatClient(innerClient));

        // Assert
        Assert.NotNull(agent);
        var retrievedTestClient = agent.GetService<TestChatClient>();
        Assert.NotNull(retrievedTestClient);
        Assert.Same(testChatClient, retrievedTestClient);
    }

    #endregion

    #region CreateAIAgentAsync(AIProjectClient, string, AgentDefinition) Tests

    /// <summary>
    /// Verify that CreateAIAgentAsync throws ArgumentNullException when AIProjectClient is null.
    /// </summary>
    [Fact]
    public async Task CreateAIAgentAsync_WithAgentDefinition_WithNullClient_ThrowsArgumentNullExceptionAsync()
    {
        // Arrange
        AIProjectClient? client = null;
        var definition = new PromptAgentDefinition("test-model");
        var options = new AgentVersionCreationOptions(definition);

        // Act & Assert
        var exception = await Assert.ThrowsAsync<ArgumentNullException>(() =>
            client!.CreateAIAgentAsync("agent-name", options));

        Assert.Equal("aiProjectClient", exception.ParamName);
    }

    /// <summary>
    /// Verify that CreateAIAgentAsync throws ArgumentNullException when creationOptions is null.
    /// </summary>
    [Fact]
    public async Task CreateAIAgentAsync_WithAgentDefinition_WithNullDefinition_ThrowsArgumentNullExceptionAsync()
    {
        // Arrange
        var mockClient = new Mock<AIProjectClient>();

        // Act & Assert
        var exception = await Assert.ThrowsAsync<ArgumentNullException>(() =>
            mockClient.Object.CreateAIAgentAsync(name: "agent-name", null!));

        Assert.Equal("creationOptions", exception.ParamName);
    }

    #endregion

    #region Tool Validation Tests

    /// <summary>
    /// Verify that CreateAIAgent creates an agent successfully.
    /// </summary>
    [Fact]
    public void CreateAIAgent_WithDefinition_CreatesAgentSuccessfully()
    {
        // Arrange
        AIProjectClient client = this.CreateTestAgentClient();
        var definition = new PromptAgentDefinition("test-model") { Instructions = "Test" };
        var options = new AgentVersionCreationOptions(definition);

        // Act
        var agent = client.CreateAIAgent("test-agent", options);

        // Assert
        Assert.NotNull(agent);
        Assert.IsType<ChatClientAgent>(agent);
    }

    /// <summary>
    /// Verify that CreateAIAgent without tools parameter creates an agent successfully.
    /// </summary>
    [Fact]
    public void CreateAIAgent_WithoutToolsParameter_CreatesAgentSuccessfully()
    {
        // Arrange
        var definition = new PromptAgentDefinition("test-model") { Instructions = "Test" };

        var definitionResponse = GeneratePromptDefinitionResponse(definition, null);
        AIProjectClient client = this.CreateTestAgentClient(agentName: "test-agent", agentDefinitionResponse: definitionResponse);

        var options = new AgentVersionCreationOptions(definition);

        // Act
        var agent = client.CreateAIAgent("test-agent", options);

        // Assert
        Assert.NotNull(agent);
        Assert.IsType<ChatClientAgent>(agent);
    }

    /// <summary>
    /// Verify that CreateAIAgent without tools in definition creates an agent successfully.
    /// </summary>
    [Fact]
    public void CreateAIAgent_WithoutToolsInDefinition_CreatesAgentSuccessfully()
    {
        // Arrange
        var definition = new PromptAgentDefinition("test-model") { Instructions = "Test" };
        AIProjectClient client = this.CreateTestAgentClient(agentName: "test-agent", agentDefinitionResponse: definition);

        var options = new AgentVersionCreationOptions(definition);

        // Act
        var agent = client.CreateAIAgent("test-agent", options);

        // Assert
        Assert.NotNull(agent);
        Assert.IsType<ChatClientAgent>(agent);
    }

    /// <summary>
    /// Verify that CreateAIAgent uses tools from the definition when no separate tools parameter is provided.
    /// </summary>
    [Fact]
    public void CreateAIAgent_WithDefinitionTools_UsesDefinitionTools()
    {
        // Arrange
        var definition = new PromptAgentDefinition("test-model") { Instructions = "Test" };

        // Add a function tool to the definition
        definition.Tools.Add(ResponseTool.CreateFunctionTool("required_tool", BinaryData.FromString("{}"), strictModeEnabled: false));

        // Create a response definition with the same tool
        var definitionResponse = GeneratePromptDefinitionResponse(definition, definition.Tools.Select(t => t.AsAITool()).ToList());
        AIProjectClient client = this.CreateTestAgentClient(agentName: "test-agent", agentDefinitionResponse: definitionResponse);

        var options = new AgentVersionCreationOptions(definition);

        // Act
        var agent = client.CreateAIAgent("test-agent", options);

        // Assert
        Assert.NotNull(agent);
        Assert.IsType<ChatClientAgent>(agent);
        var agentVersion = agent.GetService<AgentVersion>();
        Assert.NotNull(agentVersion);
        if (agentVersion.Definition is PromptAgentDefinition promptDef)
        {
            Assert.NotEmpty(promptDef.Tools);
            Assert.Single(promptDef.Tools);
            Assert.Equal("required_tool", (promptDef.Tools.First() as FunctionTool)?.FunctionName);
        }
    }

    /// <summary>
    /// Verify that CreateAIAgentAsync when AI Tools are provided, uses them for the definition via http request.
    /// </summary>
    [Fact]
    public async Task CreateAIAgentAsync_WithNameAndAITools_SendsToolDefinitionViaHttpAsync()
    {
        // Arrange
        using var httpHandler = new HttpHandlerAssert(async (request) =>
        {
            if (request.Content is not null)
            {
                var requestBody = await request.Content.ReadAsStringAsync().ConfigureAwait(false);

                Assert.Contains("required_tool", requestBody);
            }

            return new HttpResponseMessage(HttpStatusCode.OK) { Content = new StringContent(TestDataUtil.GetAgentVersionResponseJson(), Encoding.UTF8, "application/json") };
        });

#pragma warning disable CA5399
        using var httpClient = new HttpClient(httpHandler);
#pragma warning restore CA5399

        var client = new AIProjectClient(new Uri("https://test.openai.azure.com/"), new FakeAuthenticationTokenProvider(), new() { Transport = new HttpClientPipelineTransport(httpClient) });

        // Act
        var agent = await client.CreateAIAgentAsync(
            name: "test-agent",
            model: "test-model",
            instructions: "Test",
            tools: [AIFunctionFactory.Create(() => true, "required_tool")]);

        // Assert
        Assert.NotNull(agent);
        Assert.IsType<ChatClientAgent>(agent);
        var agentVersion = agent.GetService<AgentVersion>();
        Assert.NotNull(agentVersion);
        Assert.IsType<PromptAgentDefinition>(agentVersion.Definition);
    }

    /// <summary>
    /// Verify that CreateAIAgent when AI Tools are provided, uses them for the definition via http request.
    /// </summary>
    [Fact]
    public void CreateAIAgent_WithNameAndAITools_SendsToolDefinitionViaHttp()
    {
        // Arrange
        using var httpHandler = new HttpHandlerAssert((request) =>
        {
            if (request.Content is not null)
            {
#pragma warning disable VSTHRD002 // Avoid problematic synchronous waits
                var requestBody = request.Content.ReadAsStringAsync().GetAwaiter().GetResult();
#pragma warning restore VSTHRD002 // Avoid problematic synchronous waits

                Assert.Contains("required_tool", requestBody);
            }

            return new HttpResponseMessage(HttpStatusCode.OK) { Content = new StringContent(TestDataUtil.GetAgentVersionResponseJson(), Encoding.UTF8, "application/json") };
        });

#pragma warning disable CA5399
        using var httpClient = new HttpClient(httpHandler);
#pragma warning restore CA5399

        var client = new AIProjectClient(new Uri("https://test.openai.azure.com/"), new FakeAuthenticationTokenProvider(), new() { Transport = new HttpClientPipelineTransport(httpClient) });

        // Act
        var agent = client.CreateAIAgent(
            name: "test-agent",
            model: "test-model",
            instructions: "Test",
            tools: [AIFunctionFactory.Create(() => true, "required_tool")]);

        // Assert
        Assert.NotNull(agent);
        Assert.IsType<ChatClientAgent>(agent);
        var agentVersion = agent.GetService<AgentVersion>();
        Assert.NotNull(agentVersion);
        Assert.IsType<PromptAgentDefinition>(agentVersion.Definition);
    }

    /// <summary>
    /// Verify that CreateAIAgent without tools creates an agent successfully.
    /// </summary>
    [Fact]
    public void CreateAIAgent_WithoutTools_CreatesAgentSuccessfully()
    {
        // Arrange
        var definition = new PromptAgentDefinition("test-model");

        var agentDefinitionResponse = GeneratePromptDefinitionResponse(definition, null);
        AIProjectClient client = this.CreateTestAgentClient(agentName: "test-agent", agentDefinitionResponse: agentDefinitionResponse);

        var options = new AgentVersionCreationOptions(definition);

        // Act
        var agent = client.CreateAIAgent("test-agent", options);

        // Assert
        Assert.NotNull(agent);
        Assert.IsType<ChatClientAgent>(agent);
    }

    /// <summary>
    /// Verify that when providing AITools with GetAIAgent, any additional tool that doesn't match the tools in agent definition are ignored.
    /// </summary>
    [Fact]
    public void GetAIAgent_AdditionalAITools_WhenNotInTheDefinitionAreIgnored()
    {
        // Arrange
        AIProjectClient client = this.CreateTestAgentClient();
        var agentVersion = this.CreateTestAgentVersion();

        // Manually add tools to the definition to simulate inline tools
        if (agentVersion.Definition is PromptAgentDefinition promptDef)
        {
            promptDef.Tools.Add(ResponseTool.CreateFunctionTool("inline_tool", BinaryData.FromString("{}"), strictModeEnabled: false));
        }

        var invocableInlineAITool = AIFunctionFactory.Create(() => "test", "inline_tool", "An invocable AIFunction for the inline function");
        var shouldBeIgnoredTool = AIFunctionFactory.Create(() => "test", "additional_tool", "An additional test function that should be ignored");

        // Act & Assert
        var agent = client.GetAIAgent(agentVersion, tools: [invocableInlineAITool, shouldBeIgnoredTool]);
        Assert.NotNull(agent);
        var version = agent.GetService<AgentVersion>();
        Assert.NotNull(version);
        var definition = Assert.IsType<PromptAgentDefinition>(version.Definition);
        Assert.NotEmpty(definition.Tools);
        Assert.NotNull(GetAgentChatOptions(agent));
        Assert.NotNull(GetAgentChatOptions(agent)!.Tools);
        Assert.Single(GetAgentChatOptions(agent)!.Tools!);
        Assert.Equal("inline_tool", (definition.Tools.First() as FunctionTool)?.FunctionName);
    }

    #endregion

    #region Inline Tools vs Parameter Tools Tests

    /// <summary>
    /// Verify that tools passed as parameters are accepted by GetAIAgent.
    /// </summary>
    [Fact]
    public void GetAIAgent_WithParameterTools_AcceptsTools()
    {
        // Arrange
        AIProjectClient client = this.CreateTestAgentClient();
        AgentRecord agentRecord = this.CreateTestAgentRecord();
        var tools = new List<AITool>
        {
            AIFunctionFactory.Create(() => "tool1", "param_tool_1", "First parameter tool"),
            AIFunctionFactory.Create(() => "tool2", "param_tool_2", "Second parameter tool")
        };

        // Act
        var agent = client.GetAIAgent(agentRecord, tools: tools);

        // Assert
        Assert.NotNull(agent);
        Assert.IsType<ChatClientAgent>(agent);
        var chatClient = agent.GetService<IChatClient>();
        Assert.NotNull(chatClient);
        var agentVersion = chatClient.GetService<AgentVersion>();
        Assert.NotNull(agentVersion);
    }

    /// <summary>
    /// Verify that CreateAIAgent with tools in definition creates an agent successfully.
    /// </summary>
    [Fact]
    public void CreateAIAgent_WithDefinitionTools_CreatesAgentSuccessfully()
    {
        // Arrange
        var definition = new PromptAgentDefinition("test-model") { Instructions = "Test instructions" };
        definition.Tools.Add(ResponseTool.CreateFunctionTool("create_tool", BinaryData.FromString("{}"), strictModeEnabled: false));

        // Simulate agent definition response with the tools
        var definitionResponse = GeneratePromptDefinitionResponse(definition, definition.Tools.Select(t => t.AsAITool()).ToList());

        AIProjectClient client = this.CreateTestAgentClient(agentDefinitionResponse: definitionResponse);

        var options = new AgentVersionCreationOptions(definition);

        // Act
        var agent = client.CreateAIAgent("test-agent", options);

        // Assert
        Assert.NotNull(agent);
        Assert.IsType<ChatClientAgent>(agent);
        var agentVersion = agent.GetService<AgentVersion>();
        Assert.NotNull(agentVersion);
        if (agentVersion.Definition is PromptAgentDefinition promptDef)
        {
            Assert.NotEmpty(promptDef.Tools);
            Assert.Single(promptDef.Tools);
        }
    }

    /// <summary>
    /// Verify that CreateAIAgent creates an agent successfully when definition has a mix of custom and hosted tools.
    /// </summary>
    [Fact]
    public void CreateAIAgent_WithMixedToolsInDefinition_CreatesAgentSuccessfully()
    {
        // Arrange
        var definition = new PromptAgentDefinition("test-model") { Instructions = "Test instructions" };
        definition.Tools.Add(ResponseTool.CreateFunctionTool("create_tool", BinaryData.FromString("{}"), strictModeEnabled: false));
        definition.Tools.Add(new HostedWebSearchTool().GetService<ResponseTool>() ?? new HostedWebSearchTool().AsOpenAIResponseTool());
        definition.Tools.Add(new HostedFileSearchTool().GetService<ResponseTool>() ?? new HostedFileSearchTool().AsOpenAIResponseTool());

        // Simulate agent definition response with the tools
        var definitionResponse = new PromptAgentDefinition("test-model") { Instructions = "Test instructions" };
        foreach (var tool in definition.Tools)
        {
            definitionResponse.Tools.Add(tool);
        }

        AIProjectClient client = this.CreateTestAgentClient(agentDefinitionResponse: definitionResponse);

        var options = new AgentVersionCreationOptions(definition);

        // Act
        var agent = client.CreateAIAgent("test-agent", options);

        // Assert
        Assert.NotNull(agent);
        Assert.IsType<ChatClientAgent>(agent);
        var agentVersion = agent.GetService<AgentVersion>();
        Assert.NotNull(agentVersion);
        if (agentVersion.Definition is PromptAgentDefinition promptDef)
        {
            Assert.NotEmpty(promptDef.Tools);
            Assert.Equal(3, promptDef.Tools.Count);
        }
    }

    /// <summary>
    /// Verifies that CreateAIAgent uses tools from definition when they are ResponseTool instances, resulting in successful agent creation.
    /// </summary>
    [Fact]
    public void CreateAIAgent_WithResponseToolsInDefinition_CreatesAgentSuccessfully()
    {
        // Arrange
        var definition = new PromptAgentDefinition("test-model") { Instructions = "Test instructions" };

        var fabricToolOptions = new FabricDataAgentToolOptions();
        fabricToolOptions.ProjectConnections.Add(new ToolProjectConnection("connection-id"));

        var sharepointOptions = new SharePointGroundingToolOptions();
        sharepointOptions.ProjectConnections.Add(new ToolProjectConnection("connection-id"));

        var structuredOutputs = new StructuredOutputDefinition("name", "description", BinaryData.FromString(AIJsonUtilities.CreateJsonSchema(new { id = "test" }.GetType()).ToString()), false);

        // Add tools to the definition
        definition.Tools.Add(ResponseTool.CreateFunctionTool("create_tool", BinaryData.FromString("{}"), strictModeEnabled: false));
        definition.Tools.Add((ResponseTool)AgentTool.CreateBingCustomSearchTool(new BingCustomSearchToolParameters([new BingCustomSearchConfiguration("connection-id", "instance-name")])));
        definition.Tools.Add((ResponseTool)AgentTool.CreateBrowserAutomationTool(new BrowserAutomationToolParameters(new BrowserAutomationToolConnectionParameters("id"))));
        definition.Tools.Add(AgentTool.CreateA2ATool(new Uri("https://test-uri.microsoft.com")));
        definition.Tools.Add((ResponseTool)AgentTool.CreateBingGroundingTool(new BingGroundingSearchToolOptions([new BingGroundingSearchConfiguration("connection-id")])));
        definition.Tools.Add((ResponseTool)AgentTool.CreateMicrosoftFabricTool(fabricToolOptions));
        definition.Tools.Add((ResponseTool)AgentTool.CreateOpenApiTool(new OpenAPIFunctionDefinition("name", BinaryData.FromString(OpenAPISpec), new OpenAPIAnonymousAuthenticationDetails())));
        definition.Tools.Add((ResponseTool)AgentTool.CreateSharepointTool(sharepointOptions));
        definition.Tools.Add((ResponseTool)AgentTool.CreateStructuredOutputsTool(structuredOutputs));
        definition.Tools.Add((ResponseTool)AgentTool.CreateAzureAISearchTool(new AzureAISearchToolOptions([new AzureAISearchToolIndex() { IndexName = "name" }])));

        // Generate agent definition response with the tools
        var definitionResponse = GeneratePromptDefinitionResponse(definition, definition.Tools.Select(t => t.AsAITool()).ToList());

        AIProjectClient client = this.CreateTestAgentClient(agentDefinitionResponse: definitionResponse);

        var options = new AgentVersionCreationOptions(definition);

        // Act
        var agent = client.CreateAIAgent("test-agent", options);

        // Assert
        Assert.NotNull(agent);
        Assert.IsType<ChatClientAgent>(agent);
        var agentVersion = agent.GetService<AgentVersion>();
        Assert.NotNull(agentVersion);
        if (agentVersion.Definition is PromptAgentDefinition promptDef)
        {
            Assert.NotEmpty(promptDef.Tools);
            Assert.Equal(10, promptDef.Tools.Count);
        }
    }

    /// <summary>
    /// Verify that CreateAIAgent with string parameters and tools creates an agent.
    /// </summary>
    [Fact]
    public void CreateAIAgent_WithStringParamsAndTools_CreatesAgent()
    {
        // Arrange
        var tools = new List<AITool>
        {
            AIFunctionFactory.Create(() => "weather", "string_param_tool", "Tool from string params")
        };

        var definitionResponse = GeneratePromptDefinitionResponse(new PromptAgentDefinition("test-model") { Instructions = "Test instructions" }, tools);

        AIProjectClient client = this.CreateTestAgentClient(agentName: "test-agent", agentDefinitionResponse: definitionResponse);

        // Act
        var agent = client.CreateAIAgent(
            "test-agent",
            "test-model",
            "Test instructions",
            tools: tools);

        // Assert
        Assert.NotNull(agent);
        Assert.IsType<ChatClientAgent>(agent);
        var agentVersion = agent.GetService<AgentVersion>();
        Assert.NotNull(agentVersion);
        if (agentVersion.Definition is PromptAgentDefinition promptDef)
        {
            Assert.NotEmpty(promptDef.Tools);
            Assert.Single(promptDef.Tools);
        }
    }

    /// <summary>
    /// Verify that CreateAIAgentAsync with tools in definition creates an agent.
    /// </summary>
    [Fact]
    public async Task CreateAIAgentAsync_WithDefinitionTools_CreatesAgentAsync()
    {
        // Arrange
        AIProjectClient client = this.CreateTestAgentClient();
        var definition = new PromptAgentDefinition("test-model") { Instructions = "Test instructions" };
        definition.Tools.Add(ResponseTool.CreateFunctionTool("async_tool", BinaryData.FromString("{}"), strictModeEnabled: false));

        var options = new AgentVersionCreationOptions(definition);

        // Act
        var agent = await client.CreateAIAgentAsync("test-agent", options);

        // Assert
        Assert.NotNull(agent);
        Assert.IsType<ChatClientAgent>(agent);
    }

    /// <summary>
    /// Verify that GetAIAgentAsync with tools parameter creates an agent.
    /// </summary>
    [Fact]
    public async Task GetAIAgentAsync_WithToolsParameter_CreatesAgentAsync()
    {
        // Arrange
        AIProjectClient client = this.CreateTestAgentClient();
        var tools = new List<AITool>
        {
            AIFunctionFactory.Create(() => "async_get_result", "async_get_tool", "An async get tool")
        };

        // Act
        var agent = await client.GetAIAgentAsync("test-agent", tools: tools);

        // Assert
        Assert.NotNull(agent);
        Assert.IsType<ChatClientAgent>(agent);
    }

    #endregion

    #region Declarative Function Handling Tests

    /// <summary>
    /// Verify that CreateAIAgent accepts declarative functions from definition.
    /// </summary>
    [Fact]
    public void CreateAIAgent_WithDeclarativeFunctionInDefinition_AcceptsDeclarativeFunction()
    {
        // Arrange
        AIProjectClient client = this.CreateTestAgentClient();
        var definition = new PromptAgentDefinition("test-model") { Instructions = "Test" };

        // Create a declarative function (not invocable) using AIFunctionFactory.CreateDeclaration
        using var doc = JsonDocument.Parse("{}");
        var declarativeFunction = AIFunctionFactory.CreateDeclaration("test_function", "A test function", doc.RootElement);

        // Add to definition
        definition.Tools.Add(declarativeFunction.AsOpenAIResponseTool() ?? throw new InvalidOperationException());

        var options = new AgentVersionCreationOptions(definition);

        // Act
        var agent = client.CreateAIAgent("test-agent", options);

        // Assert
        Assert.NotNull(agent);
        Assert.IsType<ChatClientAgent>(agent);
    }

    /// <summary>
    /// Verify that CreateAIAgent accepts declarative functions from definition.
    /// </summary>
    [Fact]
    public void CreateAIAgent_WithDeclarativeFunctionFromDefinition_AcceptsDeclarativeFunction()
    {
        // Arrange
        var definition = new PromptAgentDefinition("test-model") { Instructions = "Test" };

        // Create a declarative function (not invocable) using AIFunctionFactory.CreateDeclaration
        using var doc = JsonDocument.Parse("{}");
        var declarativeFunction = AIFunctionFactory.CreateDeclaration("test_function", "A test function", doc.RootElement);

        // Add to definition
        definition.Tools.Add(declarativeFunction.AsOpenAIResponseTool() ?? throw new InvalidOperationException());

        // Generate response with the declarative function
        var definitionResponse = new PromptAgentDefinition("test-model") { Instructions = "Test" };
        definitionResponse.Tools.Add(declarativeFunction.AsOpenAIResponseTool() ?? throw new InvalidOperationException());

        AIProjectClient client = this.CreateTestAgentClient(agentName: "test-agent", agentDefinitionResponse: definitionResponse);

        var options = new AgentVersionCreationOptions(definition);

        // Act
        var agent = client.CreateAIAgent("test-agent", options);

        // Assert
        Assert.NotNull(agent);
        Assert.IsType<ChatClientAgent>(agent);
    }

    /// <summary>
    /// Verify that CreateAIAgent accepts FunctionTools from definition.
    /// </summary>
    [Fact]
    public void CreateAIAgent_WithFunctionToolsInDefinition_AcceptsDeclarativeFunction()
    {
        // Arrange
        var functionTool = ResponseTool.CreateFunctionTool(
            functionName: "get_user_name",
            functionParameters: BinaryData.FromString("{}"),
            strictModeEnabled: false,
            functionDescription: "Gets the user's name, as used for friendly address."
        );

        var definition = new PromptAgentDefinition("test-model") { Instructions = "Test" };
        definition.Tools.Add(functionTool);

        // Generate response with the declarative function
        var definitionResponse = new PromptAgentDefinition("test-model") { Instructions = "Test" };
        definitionResponse.Tools.Add(functionTool);

        AIProjectClient client = this.CreateTestAgentClient(agentName: "test-agent", agentDefinitionResponse: definitionResponse);

        var options = new AgentVersionCreationOptions(definition);

        // Act
        var agent = client.CreateAIAgent("test-agent", options);

        // Assert
        Assert.NotNull(agent);
        Assert.IsType<ChatClientAgent>(agent);
        var definitionFromAgent = Assert.IsType<PromptAgentDefinition>(agent.GetService<AgentVersion>()?.Definition);
        Assert.Single(definitionFromAgent.Tools);
    }

    /// <summary>
    /// Verify that CreateAIAgentAsync accepts FunctionTools from definition.
    /// </summary>
    [Fact]
    public async Task CreateAIAgentAsync_WithFunctionToolsInDefinition_AcceptsDeclarativeFunctionAsync()
    {
        // Arrange
        var functionTool = ResponseTool.CreateFunctionTool(
            functionName: "get_user_name",
            functionParameters: BinaryData.FromString("{}"),
            strictModeEnabled: false,
            functionDescription: "Gets the user's name, as used for friendly address."
        );

        var definition = new PromptAgentDefinition("test-model") { Instructions = "Test" };
        definition.Tools.Add(functionTool);

        // Generate response with the declarative function
        var definitionResponse = new PromptAgentDefinition("test-model") { Instructions = "Test" };
        definitionResponse.Tools.Add(functionTool);

        AIProjectClient client = this.CreateTestAgentClient(agentName: "test-agent", agentDefinitionResponse: definitionResponse);

        var options = new AgentVersionCreationOptions(definition);

        // Act
        var agent = await client.CreateAIAgentAsync("test-agent", options);

        // Assert
        Assert.NotNull(agent);
        Assert.IsType<ChatClientAgent>(agent);
    }

    /// <summary>
    /// Verify that CreateAIAgentAsync accepts declarative functions from definition.
    /// </summary>
    [Fact]
    public async Task CreateAIAgentAsync_WithDeclarativeFunctionFromDefinition_AcceptsDeclarativeFunctionAsync()
    {
        // Arrange
        AIProjectClient client = this.CreateTestAgentClient();
        var definition = new PromptAgentDefinition("test-model") { Instructions = "Test" };

        // Create a declarative function (not invocable) using AIFunctionFactory.CreateDeclaration
        using var doc = JsonDocument.Parse("{}");
        var declarativeFunction = AIFunctionFactory.CreateDeclaration("test_function", "A test function", doc.RootElement);

        // Add to definition
        definition.Tools.Add(declarativeFunction.AsOpenAIResponseTool() ?? throw new InvalidOperationException());

        var options = new AgentVersionCreationOptions(definition);

        // Act
        var agent = await client.CreateAIAgentAsync("test-agent", options);

        // Assert
        Assert.NotNull(agent);
        Assert.IsType<ChatClientAgent>(agent);
    }

    /// <summary>
    /// Verify that CreateAIAgentAsync accepts declarative functions from definition.
    /// </summary>
    [Fact]
    public async Task CreateAIAgentAsync_WithDeclarativeFunctionInDefinition_AcceptsDeclarativeFunctionAsync()
    {
        // Arrange
        var definition = new PromptAgentDefinition("test-model") { Instructions = "Test" };

        // Create a declarative function (not invocable) using AIFunctionFactory.CreateDeclaration
        using var doc = JsonDocument.Parse("{}");
        var declarativeFunction = AIFunctionFactory.CreateDeclaration("test_function", "A test function", doc.RootElement);

        // Add to definition
        definition.Tools.Add(declarativeFunction.AsOpenAIResponseTool() ?? throw new InvalidOperationException());

        // Generate response with the declarative function
        var definitionResponse = new PromptAgentDefinition("test-model") { Instructions = "Test" };
        definitionResponse.Tools.Add(declarativeFunction.AsOpenAIResponseTool() ?? throw new InvalidOperationException());

        AIProjectClient client = this.CreateTestAgentClient(agentName: "test-agent", agentDefinitionResponse: definitionResponse);

        var options = new AgentVersionCreationOptions(definition);

        // Act
        var agent = await client.CreateAIAgentAsync("test-agent", options);

        // Assert
        Assert.NotNull(agent);
        Assert.IsType<ChatClientAgent>(agent);
    }

    #endregion

    #region Options Generation Validation Tests

    /// <summary>
    /// Verify that ChatClientAgentOptions are generated correctly without tools.
    /// </summary>
    [Fact]
    public void CreateAIAgent_GeneratesCorrectChatClientAgentOptions()
    {
        // Arrange
        var definition = new PromptAgentDefinition("test-model") { Instructions = "Test instructions" };

        var definitionResponse = GeneratePromptDefinitionResponse(definition, null);
        AIProjectClient client = this.CreateTestAgentClient(agentName: "test-agent", agentDefinitionResponse: definitionResponse);

        var options = new AgentVersionCreationOptions(definition);

        // Act
        var agent = client.CreateAIAgent("test-agent", options);

        // Assert
        Assert.NotNull(agent);
        var agentVersion = agent.GetService<AgentVersion>();
        Assert.NotNull(agentVersion);
        Assert.Equal("test-agent", agentVersion.Name);
        Assert.Equal("Test instructions", (agentVersion.Definition as PromptAgentDefinition)?.Instructions);
    }

    /// <summary>
    /// Verify that ChatClientAgentOptions preserve custom properties from input options.
    /// </summary>
    [Fact]
    public void GetAIAgent_WithOptions_PreservesCustomProperties()
    {
        // Arrange
        AIProjectClient client = this.CreateTestAgentClient(agentName: "test-agent", instructions: "Custom instructions", description: "Custom description");
        var options = new ChatClientAgentOptions
        {
            Name = "test-agent",
            Description = "Custom description",
            ChatOptions = new ChatOptions { Instructions = "Custom instructions" }
        };

        // Act
        var agent = client.GetAIAgent(options);

        // Assert
        Assert.NotNull(agent);
        Assert.Equal("test-agent", agent.Name);
        Assert.Equal("Custom instructions", agent.Instructions);
        Assert.Equal("Custom description", agent.Description);
    }

    /// <summary>
    /// Verify that CreateAIAgent with options generates correct ChatClientAgentOptions with tools.
    /// </summary>
    [Fact]
    public void CreateAIAgent_WithOptionsAndTools_GeneratesCorrectOptions()
    {
        // Arrange
        var tools = new List<AITool>
        {
            AIFunctionFactory.Create(() => "result", "option_tool", "A tool from options")
        };

        var definitionResponse = GeneratePromptDefinitionResponse(
            new PromptAgentDefinition("test-model") { Instructions = "Test" },
            tools);

        AIProjectClient client = this.CreateTestAgentClient(agentName: "test-agent", agentDefinitionResponse: definitionResponse);

        var options = new ChatClientAgentOptions
        {
            Name = "test-agent",
            ChatOptions = new ChatOptions { Instructions = "Test", Tools = tools }
        };

        // Act
        var agent = client.CreateAIAgent("test-model", options);

        // Assert
        Assert.NotNull(agent);
        var agentVersion = agent.GetService<AgentVersion>();
        Assert.NotNull(agentVersion);
        if (agentVersion.Definition is PromptAgentDefinition promptDef)
        {
            Assert.NotEmpty(promptDef.Tools);
            Assert.Single(promptDef.Tools);
        }
    }

    #endregion

    #region AgentName Validation Tests

    /// <summary>
    /// Verify that GetAIAgent throws ArgumentException when agent name is invalid.
    /// </summary>
    [Theory]
    [MemberData(nameof(InvalidAgentNameTestData.GetInvalidAgentNames), MemberType = typeof(InvalidAgentNameTestData))]
    public void GetAIAgent_ByName_WithInvalidAgentName_ThrowsArgumentException(string invalidName)
    {
        // Arrange
        var mockClient = new Mock<AIProjectClient>();

        // Act & Assert
        var exception = Assert.Throws<ArgumentException>(() =>
            mockClient.Object.GetAIAgent(invalidName));

        Assert.Equal("name", exception.ParamName);
        Assert.Contains("Agent name must be 1-63 characters long", exception.Message);
    }

    /// <summary>
    /// Verify that GetAIAgentAsync throws ArgumentException when agent name is invalid.
    /// </summary>
    [Theory]
    [MemberData(nameof(InvalidAgentNameTestData.GetInvalidAgentNames), MemberType = typeof(InvalidAgentNameTestData))]
    public async Task GetAIAgentAsync_ByName_WithInvalidAgentName_ThrowsArgumentExceptionAsync(string invalidName)
    {
        // Arrange
        var mockClient = new Mock<AIProjectClient>();

        // Act & Assert
        var exception = await Assert.ThrowsAsync<ArgumentException>(() =>
            mockClient.Object.GetAIAgentAsync(invalidName));

        Assert.Equal("name", exception.ParamName);
        Assert.Contains("Agent name must be 1-63 characters long", exception.Message);
    }

    /// <summary>
    /// Verify that GetAIAgent with ChatClientAgentOptions throws ArgumentException when agent name is invalid.
    /// </summary>
    [Theory]
    [MemberData(nameof(InvalidAgentNameTestData.GetInvalidAgentNames), MemberType = typeof(InvalidAgentNameTestData))]
    public void GetAIAgent_WithOptions_WithInvalidAgentName_ThrowsArgumentException(string invalidName)
    {
        // Arrange
        AIProjectClient client = this.CreateTestAgentClient();
        var options = new ChatClientAgentOptions { Name = invalidName };

        // Act & Assert
        var exception = Assert.Throws<ArgumentException>(() =>
            client.GetAIAgent(options));

        Assert.Equal("name", exception.ParamName);
        Assert.Contains("Agent name must be 1-63 characters long", exception.Message);
    }

    /// <summary>
    /// Verify that GetAIAgentAsync with ChatClientAgentOptions throws ArgumentException when agent name is invalid.
    /// </summary>
    [Theory]
    [MemberData(nameof(InvalidAgentNameTestData.GetInvalidAgentNames), MemberType = typeof(InvalidAgentNameTestData))]
    public async Task GetAIAgentAsync_WithOptions_WithInvalidAgentName_ThrowsArgumentExceptionAsync(string invalidName)
    {
        // Arrange
        AIProjectClient client = this.CreateTestAgentClient();
        var options = new ChatClientAgentOptions { Name = invalidName };

        // Act & Assert
        var exception = await Assert.ThrowsAsync<ArgumentException>(() =>
            client.GetAIAgentAsync(options));

        Assert.Equal("name", exception.ParamName);
        Assert.Contains("Agent name must be 1-63 characters long", exception.Message);
    }

    /// <summary>
    /// Verify that CreateAIAgent throws ArgumentException when agent name is invalid.
    /// </summary>
    [Theory]
    [MemberData(nameof(InvalidAgentNameTestData.GetInvalidAgentNames), MemberType = typeof(InvalidAgentNameTestData))]
    public void CreateAIAgent_WithBasicParams_WithInvalidAgentName_ThrowsArgumentException(string invalidName)
    {
        // Arrange
        var mockClient = new Mock<AIProjectClient>();

        // Act & Assert
        var exception = Assert.Throws<ArgumentException>(() =>
            mockClient.Object.CreateAIAgent(invalidName, "model", "instructions"));

        Assert.Equal("name", exception.ParamName);
        Assert.Contains("Agent name must be 1-63 characters long", exception.Message);
    }

    /// <summary>
    /// Verify that CreateAIAgentAsync throws ArgumentException when agent name is invalid.
    /// </summary>
    [Theory]
    [MemberData(nameof(InvalidAgentNameTestData.GetInvalidAgentNames), MemberType = typeof(InvalidAgentNameTestData))]
    public async Task CreateAIAgentAsync_WithBasicParams_WithInvalidAgentName_ThrowsArgumentExceptionAsync(string invalidName)
    {
        // Arrange
        var mockClient = new Mock<AIProjectClient>();

        // Act & Assert
        var exception = await Assert.ThrowsAsync<ArgumentException>(() =>
            mockClient.Object.CreateAIAgentAsync(invalidName, "model", "instructions"));

        Assert.Equal("name", exception.ParamName);
        Assert.Contains("Agent name must be 1-63 characters long", exception.Message);
    }

    /// <summary>
    /// Verify that CreateAIAgent with AgentVersionCreationOptions throws ArgumentException when agent name is invalid.
    /// </summary>
    [Theory]
    [MemberData(nameof(InvalidAgentNameTestData.GetInvalidAgentNames), MemberType = typeof(InvalidAgentNameTestData))]
    public void CreateAIAgent_WithAgentDefinition_WithInvalidAgentName_ThrowsArgumentException(string invalidName)
    {
        // Arrange
        var mockClient = new Mock<AIProjectClient>();
        var definition = new PromptAgentDefinition("test-model");
        var options = new AgentVersionCreationOptions(definition);

        // Act & Assert
        var exception = Assert.Throws<ArgumentException>(() =>
            mockClient.Object.CreateAIAgent(invalidName, options));

        Assert.Equal("name", exception.ParamName);
        Assert.Contains("Agent name must be 1-63 characters long", exception.Message);
    }

    /// <summary>
    /// Verify that CreateAIAgentAsync with AgentVersionCreationOptions throws ArgumentException when agent name is invalid.
    /// </summary>
    [Theory]
    [MemberData(nameof(InvalidAgentNameTestData.GetInvalidAgentNames), MemberType = typeof(InvalidAgentNameTestData))]
    public async Task CreateAIAgentAsync_WithAgentDefinition_WithInvalidAgentName_ThrowsArgumentExceptionAsync(string invalidName)
    {
        // Arrange
        var mockClient = new Mock<AIProjectClient>();
        var definition = new PromptAgentDefinition("test-model");
        var options = new AgentVersionCreationOptions(definition);

        // Act & Assert
        var exception = await Assert.ThrowsAsync<ArgumentException>(() =>
            mockClient.Object.CreateAIAgentAsync(invalidName, options));

        Assert.Equal("name", exception.ParamName);
        Assert.Contains("Agent name must be 1-63 characters long", exception.Message);
    }

    /// <summary>
    /// Verify that CreateAIAgent with ChatClientAgentOptions throws ArgumentException when agent name is invalid.
    /// </summary>
    [Theory]
    [MemberData(nameof(InvalidAgentNameTestData.GetInvalidAgentNames), MemberType = typeof(InvalidAgentNameTestData))]
    public void CreateAIAgent_WithOptions_WithInvalidAgentName_ThrowsArgumentException(string invalidName)
    {
        // Arrange
        AIProjectClient client = this.CreateTestAgentClient();
        var options = new ChatClientAgentOptions { Name = invalidName };

        // Act & Assert
        var exception = Assert.Throws<ArgumentException>(() =>
            client.CreateAIAgent("test-model", options));

        Assert.Equal("name", exception.ParamName);
        Assert.Contains("Agent name must be 1-63 characters long", exception.Message);
    }

    /// <summary>
    /// Verify that CreateAIAgentAsync with ChatClientAgentOptions throws ArgumentException when agent name is invalid.
    /// </summary>
    [Theory]
    [MemberData(nameof(InvalidAgentNameTestData.GetInvalidAgentNames), MemberType = typeof(InvalidAgentNameTestData))]
    public async Task CreateAIAgentAsync_WithOptions_WithInvalidAgentName_ThrowsArgumentExceptionAsync(string invalidName)
    {
        // Arrange
        AIProjectClient client = this.CreateTestAgentClient();
        var options = new ChatClientAgentOptions { Name = invalidName };

        // Act & Assert
        var exception = await Assert.ThrowsAsync<ArgumentException>(() =>
            client.CreateAIAgentAsync("test-model", options));

        Assert.Equal("name", exception.ParamName);
        Assert.Contains("Agent name must be 1-63 characters long", exception.Message);
    }

    /// <summary>
    /// Verify that GetAIAgent with AgentReference throws ArgumentException when agent name is invalid.
    /// </summary>
    [Theory]
    [MemberData(nameof(InvalidAgentNameTestData.GetInvalidAgentNames), MemberType = typeof(InvalidAgentNameTestData))]
    public void GetAIAgent_WithAgentReference_WithInvalidAgentName_ThrowsArgumentException(string invalidName)
    {
        // Arrange
        var mockClient = new Mock<AIProjectClient>();
        var agentReference = new AgentReference(invalidName, "1");

        // Act & Assert
        var exception = Assert.Throws<ArgumentException>(() =>
            mockClient.Object.GetAIAgent(agentReference));

        Assert.Equal("name", exception.ParamName);
        Assert.Contains("Agent name must be 1-63 characters long", exception.Message);
    }

    #endregion

    #region AzureAIChatClient Behavior Tests

    /// <summary>
    /// Verify that the underlying chat client created by extension methods can be wrapped with clientFactory.
    /// </summary>
    [Fact]
    public void GetAIAgent_WithClientFactory_WrapsUnderlyingChatClient()
    {
        // Arrange
        AIProjectClient client = this.CreateTestAgentClient();
        AgentRecord agentRecord = this.CreateTestAgentRecord();
        int factoryCallCount = 0;

        // Act
        var agent = client.GetAIAgent(
            agentRecord,
            clientFactory: (innerClient) =>
            {
                factoryCallCount++;
                return new TestChatClient(innerClient);
            });

        // Assert
        Assert.NotNull(agent);
        Assert.Equal(1, factoryCallCount);
        var wrappedClient = agent.GetService<TestChatClient>();
        Assert.NotNull(wrappedClient);
    }

    /// <summary>
    /// Verify that clientFactory is called with the correct underlying chat client.
    /// </summary>
    [Fact]
    public void CreateAIAgent_WithClientFactory_ReceivesCorrectUnderlyingClient()
    {
        // Arrange
        AIProjectClient client = this.CreateTestAgentClient();
        var definition = new PromptAgentDefinition("test-model") { Instructions = "Test" };
        IChatClient? receivedClient = null;

        var options = new AgentVersionCreationOptions(definition);

        // Act
        var agent = client.CreateAIAgent(
            "test-agent",
            options,
            clientFactory: (innerClient) =>
            {
                receivedClient = innerClient;
                return new TestChatClient(innerClient);
            });

        // Assert
        Assert.NotNull(agent);
        Assert.NotNull(receivedClient);
        var wrappedClient = agent.GetService<TestChatClient>();
        Assert.NotNull(wrappedClient);
    }

    /// <summary>
    /// Verify that multiple clientFactory calls create independent wrapped clients.
    /// </summary>
    [Fact]
    public void GetAIAgent_MultipleCallsWithClientFactory_CreatesIndependentClients()
    {
        // Arrange
        AIProjectClient client = this.CreateTestAgentClient();
        AgentRecord agentRecord = this.CreateTestAgentRecord();

        // Act
        var agent1 = client.GetAIAgent(
            agentRecord,
            clientFactory: (innerClient) => new TestChatClient(innerClient));

        var agent2 = client.GetAIAgent(
            agentRecord,
            clientFactory: (innerClient) => new TestChatClient(innerClient));

        // Assert
        Assert.NotNull(agent1);
        Assert.NotNull(agent2);
        var client1 = agent1.GetService<TestChatClient>();
        var client2 = agent2.GetService<TestChatClient>();
        Assert.NotNull(client1);
        Assert.NotNull(client2);
        Assert.NotSame(client1, client2);
    }

    /// <summary>
    /// Verify that agent created with clientFactory maintains agent properties.
    /// </summary>
    [Fact]
    public void CreateAIAgent_WithClientFactory_PreservesAgentProperties()
    {
        // Arrange
        const string AgentName = "test-agent";
        const string Model = "test-model";
        const string Instructions = "Test instructions";
        AIProjectClient client = this.CreateTestAgentClient(AgentName, Instructions);

        // Act
        var agent = client.CreateAIAgent(
            AgentName,
            Model,
            Instructions,
            clientFactory: (innerClient) => new TestChatClient(innerClient));

        // Assert
        Assert.NotNull(agent);
        Assert.Equal(AgentName, agent.Name);
        Assert.Equal(Instructions, agent.Instructions);
        var wrappedClient = agent.GetService<TestChatClient>();
        Assert.NotNull(wrappedClient);
    }

    /// <summary>
    /// Verify that agent created with clientFactory is created successfully.
    /// </summary>
    [Fact]
    public void CreateAIAgent_WithClientFactory_CreatesAgentSuccessfully()
    {
        // Arrange
        var definition = new PromptAgentDefinition("test-model") { Instructions = "Test" };

        var agentDefinitionResponse = GeneratePromptDefinitionResponse(definition, null);
        AIProjectClient client = this.CreateTestAgentClient(agentName: "test-agent", agentDefinitionResponse: agentDefinitionResponse);

        var options = new AgentVersionCreationOptions(definition);

        // Act
        var agent = client.CreateAIAgent(
            "test-agent",
            options,
            clientFactory: (innerClient) => new TestChatClient(innerClient));

        // Assert
        Assert.NotNull(agent);
        var wrappedClient = agent.GetService<TestChatClient>();
        Assert.NotNull(wrappedClient);
        var agentVersion = agent.GetService<AgentVersion>();
        Assert.NotNull(agentVersion);
    }

    #endregion

    #region User-Agent Header Tests

    /// <summary>
    /// Verify that GetAIAgent(string name) passes RequestOptions to the Protocol method.
    /// </summary>
    [Fact]
    public void GetAIAgent_WithStringName_PassesRequestOptionsToProtocol()
    {
        // Arrange
        RequestOptions? capturedRequestOptions = null;

        var mockAgentOperations = new Mock<AIProjectAgentsOperations>();
        mockAgentOperations
            .Setup(x => x.GetAgent(It.IsAny<string>(), It.IsAny<RequestOptions>()))
            .Callback<string, RequestOptions>((name, options) => capturedRequestOptions = options)
            .Returns(ClientResult.FromResponse(new MockPipelineResponse(200, BinaryData.FromString(TestDataUtil.GetAgentResponseJson()))));

        var mockAgentClient = new Mock<AIProjectClient>(new Uri("https://test.openai.azure.com/"), new FakeAuthenticationTokenProvider());
        mockAgentClient.SetupGet(x => x.Agents).Returns(mockAgentOperations.Object);
        mockAgentClient.Setup(x => x.GetConnection(It.IsAny<string>())).Returns(new ClientConnection("fake-connection-id", "http://localhost", ClientPipeline.Create(), CredentialKind.None));

        // Act
        var agent = mockAgentClient.Object.GetAIAgent("test-agent");

        // Assert
        Assert.NotNull(agent);
        Assert.NotNull(capturedRequestOptions);
    }

    /// <summary>
    /// Verify that GetAIAgentAsync(string name) passes RequestOptions to the Protocol method.
    /// </summary>
    [Fact]
    public async Task GetAIAgentAsync_WithStringName_PassesRequestOptionsToProtocolAsync()
    {
        // Arrange
        RequestOptions? capturedRequestOptions = null;

        var mockAgentOperations = new Mock<AIProjectAgentsOperations>();
        mockAgentOperations
            .Setup(x => x.GetAgentAsync(It.IsAny<string>(), It.IsAny<RequestOptions>()))
            .Callback<string, RequestOptions>((name, options) => capturedRequestOptions = options)
            .Returns(Task.FromResult(ClientResult.FromResponse(new MockPipelineResponse(200, BinaryData.FromString(TestDataUtil.GetAgentResponseJson())))));

        var mockAgentClient = new Mock<AIProjectClient>(new Uri("https://test.openai.azure.com/"), new FakeAuthenticationTokenProvider());
        mockAgentClient.SetupGet(x => x.Agents).Returns(mockAgentOperations.Object);
        mockAgentClient.Setup(x => x.GetConnection(It.IsAny<string>())).Returns(new ClientConnection("fake-connection-id", "http://localhost", ClientPipeline.Create(), CredentialKind.None));
        // Act
        var agent = await mockAgentClient.Object.GetAIAgentAsync("test-agent");

        // Assert
        Assert.NotNull(agent);
        Assert.NotNull(capturedRequestOptions);
    }

    /// <summary>
    /// Verify that CreateAIAgent(string model, ChatClientAgentOptions options) passes RequestOptions to the Protocol method.
    /// </summary>
    [Fact]
    public void CreateAIAgent_WithChatClientAgentOptions_PassesRequestOptionsToProtocol()
    {
        // Arrange
        RequestOptions? capturedRequestOptions = null;

        var mockAgentOperations = new Mock<AIProjectAgentsOperations>();
        mockAgentOperations
            .Setup(x => x.CreateAgentVersion(It.IsAny<string>(), It.IsAny<BinaryContent>(), It.IsAny<RequestOptions>()))
            .Callback<string, BinaryContent, RequestOptions>((name, content, options) => capturedRequestOptions = options)
            .Returns(ClientResult.FromResponse(new MockPipelineResponse(200, BinaryData.FromString(TestDataUtil.GetAgentVersionResponseJson()))));

        var mockAgentClient = new Mock<AIProjectClient>(new Uri("https://test.openai.azure.com/"), new FakeAuthenticationTokenProvider());
        mockAgentClient.SetupGet(x => x.Agents).Returns(mockAgentOperations.Object);
        mockAgentClient.Setup(x => x.GetConnection(It.IsAny<string>())).Returns(new ClientConnection("fake-connection-id", "http://localhost", ClientPipeline.Create(), CredentialKind.None));

        var agentOptions = new ChatClientAgentOptions { Name = "test-agent" };

        // Act
        var agent = mockAgentClient.Object.CreateAIAgent("gpt-4", agentOptions);

        // Assert
        Assert.NotNull(agent);
        Assert.NotNull(capturedRequestOptions);
    }

    /// <summary>
    /// Verify that CreateAIAgentAsync(string model, ChatClientAgentOptions options) passes RequestOptions to the Protocol method.
    /// </summary>
    [Fact]
    public async Task CreateAIAgentAsync_WithChatClientAgentOptions_PassesRequestOptionsToProtocolAsync()
    {
        // Arrange
        RequestOptions? capturedRequestOptions = null;

        var mockAgentOperations = new Mock<AIProjectAgentsOperations>();
        mockAgentOperations
            .Setup(x => x.CreateAgentVersionAsync(It.IsAny<string>(), It.IsAny<BinaryContent>(), It.IsAny<RequestOptions>()))
            .Callback<string, BinaryContent, RequestOptions>((name, content, options) => capturedRequestOptions = options)
            .Returns(Task.FromResult(ClientResult.FromResponse(new MockPipelineResponse(200, BinaryData.FromString(TestDataUtil.GetAgentVersionResponseJson())))));

        var mockAgentClient = new Mock<AIProjectClient>(new Uri("https://test.openai.azure.com/"), new FakeAuthenticationTokenProvider());
        mockAgentClient.SetupGet(x => x.Agents).Returns(mockAgentOperations.Object);
        mockAgentClient.Setup(x => x.GetConnection(It.IsAny<string>())).Returns(new ClientConnection("fake-connection-id", "http://localhost", ClientPipeline.Create(), CredentialKind.None));

        var agentOptions = new ChatClientAgentOptions { Name = "test-agent" };

        // Act
        var agent = await mockAgentClient.Object.CreateAIAgentAsync("gpt-4", agentOptions);

        // Assert
        Assert.NotNull(agent);
        Assert.NotNull(capturedRequestOptions);
    }

    /// <summary>
    /// Verifies that the user-agent header is added to both synchronous and asynchronous requests made by agent creation methods.
    /// </summary>
    [Fact]
    public async Task CreateAIAgent_UserAgentHeaderAddedToRequestsAsync()
    {
        using var httpHandler = new HttpHandlerAssert(request =>
        {
            Assert.Equal("POST", request.Method.Method);
            Assert.Contains("MEAI", request.Headers.UserAgent.ToString());

            return new HttpResponseMessage(HttpStatusCode.OK) { Content = new StringContent(TestDataUtil.GetAgentResponseJson(), Encoding.UTF8, "application/json") };
        });

#pragma warning disable CA5399
        using var httpClient = new HttpClient(httpHandler);
#pragma warning restore CA5399

        // Arrange
        var aiProjectClient = new AIProjectClient(new Uri("https://test.openai.azure.com/"), new FakeAuthenticationTokenProvider(), new() { Transport = new HttpClientPipelineTransport(httpClient) });

        var agentOptions = new ChatClientAgentOptions { Name = "test-agent" };

        // Act
        var agent1 = aiProjectClient.CreateAIAgent("test", agentOptions);
        var agent2 = await aiProjectClient.CreateAIAgentAsync("test", agentOptions);

        // Assert
        Assert.NotNull(agent1);
        Assert.NotNull(agent2);
    }

    /// <summary>
    /// Verifies that the user-agent header is added to both synchronous and asynchronous GetAIAgent requests.
    /// </summary>
    [Fact]
    public async Task GetAIAgent_UserAgentHeaderAddedToRequestsAsync()
    {
        using var httpHandler = new HttpHandlerAssert(request =>
        {
            Assert.Equal("GET", request.Method.Method);
            Assert.Contains("MEAI", request.Headers.UserAgent.ToString());

            return new HttpResponseMessage(HttpStatusCode.OK) { Content = new StringContent(TestDataUtil.GetAgentResponseJson(), Encoding.UTF8, "application/json") };
        });

#pragma warning disable CA5399
        using var httpClient = new HttpClient(httpHandler);
#pragma warning restore CA5399

        // Arrange
        var aiProjectClient = new AIProjectClient(new Uri("https://test.openai.azure.com/"), new FakeAuthenticationTokenProvider(), new() { Transport = new HttpClientPipelineTransport(httpClient) });

        // Act
        var agent1 = aiProjectClient.GetAIAgent("test");
        var agent2 = await aiProjectClient.GetAIAgentAsync("test");

        // Assert
        Assert.NotNull(agent1);
        Assert.NotNull(agent2);
    }

    #endregion

    #region GetAIAgent(AIProjectClient, AgentReference) Tests

    /// <summary>
    /// Verify that GetAIAgent throws ArgumentNullException when AIProjectClient is null.
    /// </summary>
    [Fact]
    public void GetAIAgent_WithAgentReference_WithNullClient_ThrowsArgumentNullException()
    {
        // Arrange
        AIProjectClient? client = null;
        var agentReference = new AgentReference("test-name", "1");

        // Act & Assert
        var exception = Assert.Throws<ArgumentNullException>(() =>
            client!.GetAIAgent(agentReference));

        Assert.Equal("aiProjectClient", exception.ParamName);
    }

    /// <summary>
    /// Verify that GetAIAgent throws ArgumentNullException when agentReference is null.
    /// </summary>
    [Fact]
    public void GetAIAgent_WithAgentReference_WithNullAgentReference_ThrowsArgumentNullException()
    {
        // Arrange
        var mockClient = new Mock<AIProjectClient>();

        // Act & Assert
        var exception = Assert.Throws<ArgumentNullException>(() =>
            mockClient.Object.GetAIAgent((AgentReference)null!));

        Assert.Equal("agentReference", exception.ParamName);
    }

    /// <summary>
    /// Verify that GetAIAgent with AgentReference creates a valid agent.
    /// </summary>
    [Fact]
    public void GetAIAgent_WithAgentReference_CreatesValidAgent()
    {
        // Arrange
        AIProjectClient client = this.CreateTestAgentClient();
        var agentReference = new AgentReference("test-name", "1");

        // Act
        var agent = client.GetAIAgent(agentReference);

        // Assert
        Assert.NotNull(agent);
        Assert.Equal("test-name", agent.Name);
        Assert.Equal("test-name:1", agent.Id);
    }

    /// <summary>
    /// Verify that GetAIAgent with AgentReference and clientFactory applies the factory.
    /// </summary>
    [Fact]
    public void GetAIAgent_WithAgentReference_WithClientFactory_AppliesFactoryCorrectly()
    {
        // Arrange
        AIProjectClient client = this.CreateTestAgentClient();
        var agentReference = new AgentReference("test-name", "1");
        TestChatClient? testChatClient = null;

        // Act
        var agent = client.GetAIAgent(
            agentReference,
            clientFactory: (innerClient) => testChatClient = new TestChatClient(innerClient));

        // Assert
        Assert.NotNull(agent);
        var retrievedTestClient = agent.GetService<TestChatClient>();
        Assert.NotNull(retrievedTestClient);
        Assert.Same(testChatClient, retrievedTestClient);
    }

    /// <summary>
    /// Verify that GetAIAgent with AgentReference sets the agent ID correctly.
    /// </summary>
    [Fact]
    public void GetAIAgent_WithAgentReference_SetsAgentIdCorrectly()
    {
        // Arrange
        AIProjectClient client = this.CreateTestAgentClient();
        var agentReference = new AgentReference("test-name", "2");

        // Act
        var agent = client.GetAIAgent(agentReference);

        // Assert
        Assert.NotNull(agent);
        Assert.Equal("test-name:2", agent.Id);
    }

    /// <summary>
    /// Verify that GetAIAgent with AgentReference and tools includes the tools in ChatOptions.
    /// </summary>
    [Fact]
    public void GetAIAgent_WithAgentReference_WithTools_IncludesToolsInChatOptions()
    {
        // Arrange
        AIProjectClient client = this.CreateTestAgentClient();
        var agentReference = new AgentReference("test-name", "1");
        var tools = new List<AITool>
        {
            AIFunctionFactory.Create(() => "test", "test_function", "A test function")
        };

        // Act
        var agent = client.GetAIAgent(agentReference, tools: tools);

        // Assert
        Assert.NotNull(agent);
        var chatOptions = GetAgentChatOptions(agent);
        Assert.NotNull(chatOptions);
        Assert.NotNull(chatOptions.Tools);
        Assert.Single(chatOptions.Tools);
    }

    #endregion

    #region GetService<AgentRecord> Tests

    /// <summary>
    /// Verify that GetService returns AgentRecord for agents created from AgentRecord.
    /// </summary>
    [Fact]
    public void GetService_WithAgentRecord_ReturnsAgentRecord()
    {
        // Arrange
        AIProjectClient client = this.CreateTestAgentClient();
        AgentRecord agentRecord = this.CreateTestAgentRecord();

        // Act
        var agent = client.GetAIAgent(agentRecord);
        var retrievedRecord = agent.GetService<AgentRecord>();

        // Assert
        Assert.NotNull(retrievedRecord);
        Assert.Equal(agentRecord.Id, retrievedRecord.Id);
    }

    /// <summary>
    /// Verify that GetService returns null for AgentRecord when agent is created from AgentReference.
    /// </summary>
    [Fact]
    public void GetService_WithAgentReference_ReturnsNullForAgentRecord()
    {
        // Arrange
        AIProjectClient client = this.CreateTestAgentClient();
        var agentReference = new AgentReference("test-name", "1");

        // Act
        var agent = client.GetAIAgent(agentReference);
        var retrievedRecord = agent.GetService<AgentRecord>();

        // Assert
        Assert.Null(retrievedRecord);
    }

    #endregion

    #region GetService<AgentVersion> Tests

    /// <summary>
    /// Verify that GetService returns AgentVersion for agents created from AgentVersion.
    /// </summary>
    [Fact]
    public void GetService_WithAgentVersion_ReturnsAgentVersion()
    {
        // Arrange
        AIProjectClient client = this.CreateTestAgentClient();
        AgentVersion agentVersion = this.CreateTestAgentVersion();

        // Act
        var agent = client.GetAIAgent(agentVersion);
        var retrievedVersion = agent.GetService<AgentVersion>();

        // Assert
        Assert.NotNull(retrievedVersion);
        Assert.Equal(agentVersion.Id, retrievedVersion.Id);
    }

    /// <summary>
    /// Verify that GetService returns null for AgentVersion when agent is created from AgentReference.
    /// </summary>
    [Fact]
    public void GetService_WithAgentReference_ReturnsNullForAgentVersion()
    {
        // Arrange
        AIProjectClient client = this.CreateTestAgentClient();
        var agentReference = new AgentReference("test-name", "1");

        // Act
        var agent = client.GetAIAgent(agentReference);
        var retrievedVersion = agent.GetService<AgentVersion>();

        // Assert
        Assert.Null(retrievedVersion);
    }

    #endregion

    #region ChatClientMetadata Tests

    /// <summary>
    /// Verify that ChatClientMetadata is properly populated for agents created from AgentRecord.
    /// </summary>
    [Fact]
    public void ChatClientMetadata_WithAgentRecord_IsPopulatedCorrectly()
    {
        // Arrange
        AIProjectClient client = this.CreateTestAgentClient();
        AgentRecord agentRecord = this.CreateTestAgentRecord();

        // Act
        var agent = client.GetAIAgent(agentRecord);
        var metadata = agent.GetService<ChatClientMetadata>();

        // Assert
        Assert.NotNull(metadata);
        Assert.NotNull(metadata.DefaultModelId);
    }

    /// <summary>
    /// Verify that ChatClientMetadata.DefaultModelId is set from PromptAgentDefinition model property.
    /// </summary>
    [Fact]
    public void ChatClientMetadata_WithPromptAgentDefinition_SetsDefaultModelIdFromModel()
    {
        // Arrange
        AIProjectClient client = this.CreateTestAgentClient();
        var definition = new PromptAgentDefinition("gpt-4-turbo")
        {
            Instructions = "Test instructions"
        };
        AgentRecord agentRecord = this.CreateTestAgentRecord(definition);

        // Act
        var agent = client.GetAIAgent(agentRecord);
        var metadata = agent.GetService<ChatClientMetadata>();

        // Assert
        Assert.NotNull(metadata);
        // The metadata should contain the model information from the agent definition
        Assert.NotNull(metadata.DefaultModelId);
        Assert.Equal("gpt-4-turbo", metadata.DefaultModelId);
    }

    /// <summary>
    /// Verify that ChatClientMetadata is properly populated for agents created from AgentVersion.
    /// </summary>
    [Fact]
    public void ChatClientMetadata_WithAgentVersion_IsPopulatedCorrectly()
    {
        // Arrange
        AIProjectClient client = this.CreateTestAgentClient();
        AgentVersion agentVersion = this.CreateTestAgentVersion();

        // Act
        var agent = client.GetAIAgent(agentVersion);
        var metadata = agent.GetService<ChatClientMetadata>();

        // Assert
        Assert.NotNull(metadata);
        Assert.NotNull(metadata.DefaultModelId);
        Assert.Equal((agentVersion.Definition as PromptAgentDefinition)!.Model, metadata.DefaultModelId);
    }

    #endregion

    #region AgentReference Availability Tests

    /// <summary>
    /// Verify that GetService returns AgentReference for agents created from AgentReference.
    /// </summary>
    [Fact]
    public void GetService_WithAgentReference_ReturnsAgentReference()
    {
        // Arrange
        AIProjectClient client = this.CreateTestAgentClient();
        var agentReference = new AgentReference("test-agent", "1.0");

        // Act
        var agent = client.GetAIAgent(agentReference);
        var retrievedReference = agent.GetService<AgentReference>();

        // Assert
        Assert.NotNull(retrievedReference);
        Assert.Equal("test-agent", retrievedReference.Name);
        Assert.Equal("1.0", retrievedReference.Version);
    }

    /// <summary>
    /// Verify that GetService returns null for AgentReference when agent is created from AgentRecord.
    /// </summary>
    [Fact]
    public void GetService_WithAgentRecord_ReturnsAlsoAgentReference()
    {
        // Arrange
        AIProjectClient client = this.CreateTestAgentClient();
        AgentRecord agentRecord = this.CreateTestAgentRecord();

        // Act
        var agent = client.GetAIAgent(agentRecord);
        var retrievedReference = agent.GetService<AgentReference>();

        // Assert
        Assert.NotNull(retrievedReference);
        Assert.Equal(agentRecord.Name, retrievedReference.Name);
    }

    /// <summary>
    /// Verify that GetService returns null for AgentReference when agent is created from AgentVersion.
    /// </summary>
    [Fact]
    public void GetService_WithAgentVersion_ReturnsAlsoAgentReference()
    {
        // Arrange
        AIProjectClient client = this.CreateTestAgentClient();
        AgentVersion agentVersion = this.CreateTestAgentVersion();

        // Act
        var agent = client.GetAIAgent(agentVersion);
        var retrievedReference = agent.GetService<AgentReference>();

        // Assert
        Assert.NotNull(retrievedReference);
        Assert.Equal(agentVersion.Name, retrievedReference.Name);
    }

    /// <summary>
    /// Verify that GetService returns AgentReference with correct version information.
    /// </summary>
    [Fact]
    public void GetService_WithAgentReference_ReturnsCorrectVersionInformation()
    {
        // Arrange
        AIProjectClient client = this.CreateTestAgentClient();
        var agentReference = new AgentReference("versioned-agent", "3.5");

        // Act
        var agent = client.GetAIAgent(agentReference);
        var retrievedReference = agent.GetService<AgentReference>();

        // Assert
        Assert.NotNull(retrievedReference);
        Assert.Equal("versioned-agent", retrievedReference.Name);
        Assert.Equal("3.5", retrievedReference.Version);
    }

    #endregion

    #region Helper Methods

    /// <summary>
    /// Creates a test AIProjectClient with fake behavior.
    /// </summary>
    private FakeAgentClient CreateTestAgentClient(string? agentName = null, string? instructions = null, string? description = null, AgentDefinition? agentDefinitionResponse = null)
    {
        return new FakeAgentClient(agentName, instructions, description, agentDefinitionResponse);
    }

    /// <summary>
    /// Creates a test AgentRecord for testing.
    /// </summary>
    private AgentRecord CreateTestAgentRecord(AgentDefinition? agentDefinition = null)
    {
        return ModelReaderWriter.Read<AgentRecord>(BinaryData.FromString(TestDataUtil.GetAgentResponseJson(agentDefinition: agentDefinition)))!;
    }

    private const string OpenAPISpec = """
        {
          "openapi": "3.0.3",
          "info": { "title": "Tiny Test API", "version": "1.0.0" },
          "paths": {
            "/ping": {
              "get": {
                "summary": "Health check",
                "operationId": "getPing",
                "responses": {
                  "200": {
                    "description": "OK",
                    "content": {
                      "application/json": {
                        "schema": {
                          "type": "object",
                          "properties": { "message": { "type": "string" } },
                          "required": ["message"]
                        },
                        "example": { "message": "pong" }
                      }
                    }
                  }
                }
              }
            }
          }
        }
        """;

    /// <summary>
    /// Creates a test AgentVersion for testing.
    /// </summary>
    private AgentVersion CreateTestAgentVersion()
    {
        return ModelReaderWriter.Read<AgentVersion>(BinaryData.FromString(TestDataUtil.GetAgentVersionResponseJson()))!;
    }

    /// <summary>
    /// Fake AIProjectClient for testing.
    /// </summary>
    private sealed class FakeAgentClient : AIProjectClient
    {
        public FakeAgentClient(string? agentName = null, string? instructions = null, string? description = null, AgentDefinition? agentDefinitionResponse = null)
        {
            this.Agents = new FakeAIProjectAgentsOperations(agentName, instructions, description, agentDefinitionResponse);
        }

        public override ClientConnection GetConnection(string connectionId)
        {
            return new ClientConnection("fake-connection-id", "http://localhost", ClientPipeline.Create(), CredentialKind.None);
        }

        public override AIProjectAgentsOperations Agents { get; }

        private sealed class FakeAIProjectAgentsOperations : AIProjectAgentsOperations
        {
            private readonly string? _agentName;
            private readonly string? _instructions;
            private readonly string? _description;
            private readonly AgentDefinition? _agentDefinition;

            public FakeAIProjectAgentsOperations(string? agentName = null, string? instructions = null, string? description = null, AgentDefinition? agentDefinitionResponse = null)
            {
                this._agentName = agentName;
                this._instructions = instructions;
                this._description = description;
                this._agentDefinition = agentDefinitionResponse;
            }

            public override ClientResult GetAgent(string agentName, RequestOptions options)
            {
                var responseJson = TestDataUtil.GetAgentResponseJson(this._agentName, this._agentDefinition, this._instructions, this._description);
                return ClientResult.FromValue(ModelReaderWriter.Read<AgentRecord>(BinaryData.FromString(responseJson))!, new MockPipelineResponse(200, BinaryData.FromString(responseJson)));
            }

            public override ClientResult<AgentRecord> GetAgent(string agentName, CancellationToken cancellationToken = default)
            {
                var responseJson = TestDataUtil.GetAgentResponseJson(this._agentName, this._agentDefinition, this._instructions, this._description);
                return ClientResult.FromValue(ModelReaderWriter.Read<AgentRecord>(BinaryData.FromString(responseJson))!, new MockPipelineResponse(200));
            }

            public override Task<ClientResult> GetAgentAsync(string agentName, RequestOptions options)
            {
                var responseJson = TestDataUtil.GetAgentResponseJson(this._agentName, this._agentDefinition, this._instructions, this._description);
                return Task.FromResult<ClientResult>(ClientResult.FromValue(ModelReaderWriter.Read<AgentRecord>(BinaryData.FromString(responseJson))!, new MockPipelineResponse(200, BinaryData.FromString(responseJson))));
            }

            public override Task<ClientResult<AgentRecord>> GetAgentAsync(string agentName, CancellationToken cancellationToken = default)
            {
                var responseJson = TestDataUtil.GetAgentResponseJson(this._agentName, this._agentDefinition, this._instructions, this._description);
                return Task.FromResult(ClientResult.FromValue(ModelReaderWriter.Read<AgentRecord>(BinaryData.FromString(responseJson))!, new MockPipelineResponse(200)));
            }

            public override ClientResult CreateAgentVersion(string agentName, BinaryContent content, RequestOptions? options = null)
            {
                var responseJson = TestDataUtil.GetAgentVersionResponseJson(this._agentName, this._agentDefinition, this._instructions, this._description);
                return ClientResult.FromValue(ModelReaderWriter.Read<AgentVersion>(BinaryData.FromString(responseJson))!, new MockPipelineResponse(200, BinaryData.FromString(responseJson)));
            }

            public override ClientResult<AgentVersion> CreateAgentVersion(string agentName, AgentVersionCreationOptions? options = null, CancellationToken cancellationToken = default)
            {
                var responseJson = TestDataUtil.GetAgentVersionResponseJson(this._agentName, this._agentDefinition, this._instructions, this._description);
                return ClientResult.FromValue(ModelReaderWriter.Read<AgentVersion>(BinaryData.FromString(responseJson))!, new MockPipelineResponse(200));
            }

            public override Task<ClientResult> CreateAgentVersionAsync(string agentName, BinaryContent content, RequestOptions? options = null)
            {
                var responseJson = TestDataUtil.GetAgentVersionResponseJson(this._agentName, this._agentDefinition, this._instructions, this._description);
                return Task.FromResult<ClientResult>(ClientResult.FromValue(ModelReaderWriter.Read<AgentVersion>(BinaryData.FromString(responseJson))!, new MockPipelineResponse(200, BinaryData.FromString(responseJson))));
            }

            public override Task<ClientResult<AgentVersion>> CreateAgentVersionAsync(string agentName, AgentVersionCreationOptions? options = null, CancellationToken cancellationToken = default)
            {
                var responseJson = TestDataUtil.GetAgentVersionResponseJson(this._agentName, this._agentDefinition, this._instructions, this._description);
                return Task.FromResult(ClientResult.FromValue(ModelReaderWriter.Read<AgentVersion>(BinaryData.FromString(responseJson))!, new MockPipelineResponse(200)));
            }
        }
    }

    private static PromptAgentDefinition GeneratePromptDefinitionResponse(PromptAgentDefinition inputDefinition, List<AITool>? tools)
    {
        var definitionResponse = new PromptAgentDefinition(inputDefinition.Model) { Instructions = inputDefinition.Instructions };
        if (tools is not null)
        {
            foreach (var tool in tools)
            {
                definitionResponse.Tools.Add(tool.GetService<ResponseTool>() ?? tool.AsOpenAIResponseTool());
            }
        }

        return definitionResponse;
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
    /// Mock pipeline response for testing ClientResult wrapping.
    /// </summary>
    private sealed class MockPipelineResponse : PipelineResponse
    {
        private readonly int _status;
        private readonly BinaryData _content;
        private readonly MockPipelineResponseHeaders _headers;

        public MockPipelineResponse(int status, BinaryData? content = null)
        {
            this._status = status;
            this._content = content ?? BinaryData.Empty;
            this._headers = new MockPipelineResponseHeaders();
        }

        public override int Status => this._status;

        public override string ReasonPhrase => "OK";

        public override Stream? ContentStream
        {
            get => null;
            set { }
        }

        public override BinaryData Content => this._content;

        protected override PipelineResponseHeaders HeadersCore => this._headers;

        public override BinaryData BufferContent(CancellationToken cancellationToken = default) =>
            throw new NotSupportedException("Buffering content is not supported for mock responses.");

        public override ValueTask<BinaryData> BufferContentAsync(CancellationToken cancellationToken = default) =>
            throw new NotSupportedException("Buffering content asynchronously is not supported for mock responses.");

        public override void Dispose()
        {
        }

        private sealed class MockPipelineResponseHeaders : PipelineResponseHeaders
        {
            private readonly Dictionary<string, string> _headers = new(StringComparer.OrdinalIgnoreCase)
            {
                { "Content-Type", "application/json" },
                { "x-ms-request-id", "test-request-id" }
            };

            public override bool TryGetValue(string name, out string? value)
            {
                return this._headers.TryGetValue(name, out value);
            }

            public override bool TryGetValues(string name, out IEnumerable<string>? values)
            {
                if (this._headers.TryGetValue(name, out var value))
                {
                    values = [value];
                    return true;
                }

                values = null;
                return false;
            }

            public override IEnumerator<KeyValuePair<string, string>> GetEnumerator()
            {
                return this._headers.GetEnumerator();
            }
        }
    }

    #endregion

    /// <summary>
    /// Helper method to access internal ChatOptions property via reflection.
    /// </summary>
    private static ChatOptions? GetAgentChatOptions(ChatClientAgent agent)
    {
        if (agent is null)
        {
            return null;
        }

        var chatOptionsProperty = typeof(ChatClientAgent).GetProperty(
            "ChatOptions",
            System.Reflection.BindingFlags.Public |
            System.Reflection.BindingFlags.NonPublic |
            System.Reflection.BindingFlags.Instance);

        return chatOptionsProperty?.GetValue(agent) as ChatOptions;
    }
}

/// <summary>
/// Provides test data for invalid agent name validation tests.
/// </summary>
internal static class InvalidAgentNameTestData
{
    /// <summary>
    /// Gets a collection of invalid agent names for theory-based testing.
    /// </summary>
    /// <returns>Collection of invalid agent name test cases.</returns>
    public static IEnumerable<object[]> GetInvalidAgentNames()
    {
        yield return new object[] { "-agent" };
        yield return new object[] { "agent-" };
        yield return new object[] { "agent_name" };
        yield return new object[] { "agent name" };
        yield return new object[] { "agent@name" };
        yield return new object[] { "agent#name" };
        yield return new object[] { "agent$name" };
        yield return new object[] { "agent%name" };
        yield return new object[] { "agent&name" };
        yield return new object[] { "agent*name" };
        yield return new object[] { "agent.name" };
        yield return new object[] { "agent/name" };
        yield return new object[] { "agent\\name" };
        yield return new object[] { "agent:name" };
        yield return new object[] { "agent;name" };
        yield return new object[] { "agent,name" };
        yield return new object[] { "agent<name" };
        yield return new object[] { "agent>name" };
        yield return new object[] { "agent?name" };
        yield return new object[] { "agent!name" };
        yield return new object[] { "agent~name" };
        yield return new object[] { "agent`name" };
        yield return new object[] { "agent^name" };
        yield return new object[] { "agent|name" };
        yield return new object[] { "agent[name" };
        yield return new object[] { "agent]name" };
        yield return new object[] { "agent{name" };
        yield return new object[] { "agent}name" };
        yield return new object[] { "agent(name" };
        yield return new object[] { "agent)name" };
        yield return new object[] { "agent+name" };
        yield return new object[] { "agent=name" };
        yield return new object[] { "a" + new string('b', 63) };
    }
}
