// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Azure.AI.Agents;
using Microsoft.Extensions.AI;
using Moq;
using OpenAI;
using OpenAI.Responses;

namespace Microsoft.Agents.AI.AzureAIAgents.UnitTests.Extensions;

/// <summary>
/// Unit tests for the <see cref="AgentsClientExtensions"/> class.
/// </summary>
public sealed class AgentsClientExtensionsTests
{
    #region GetAIAgent(AgentsClient, string, AgentRecord) Tests

    /// <summary>
    /// Verify that GetAIAgent throws ArgumentNullException when agentsClient is null.
    /// </summary>
    [Fact]
    public void GetAIAgent_WithAgentRecord_WithNullClient_ThrowsArgumentNullException()
    {
        // Arrange
        AgentsClient? client = null;
        AgentRecord agentRecord = this.CreateTestAgentRecord();

        // Act & Assert
        var exception = Assert.Throws<ArgumentNullException>(() =>
            client!.GetAIAgent("model", agentRecord));

        Assert.Equal("agentsClient", exception.ParamName);
    }

    /// <summary>
    /// Verify that GetAIAgent throws ArgumentException when model is null.
    /// </summary>
    [Fact]
    public void GetAIAgent_WithAgentRecord_WithNullModel_ThrowsArgumentException()
    {
        // Arrange
        var mockClient = new Mock<AgentsClient>();
        AgentRecord agentRecord = this.CreateTestAgentRecord();

        // Act & Assert
        var exception = Assert.Throws<ArgumentException>(() =>
            mockClient.Object.GetAIAgent(null!, agentRecord));

        Assert.Equal("model", exception.ParamName);
    }

    /// <summary>
    /// Verify that GetAIAgent throws ArgumentException when model is empty.
    /// </summary>
    [Fact]
    public void GetAIAgent_WithAgentRecord_WithEmptyModel_ThrowsArgumentException()
    {
        // Arrange
        var mockClient = new Mock<AgentsClient>();
        AgentRecord agentRecord = this.CreateTestAgentRecord();

        // Act & Assert
        var exception = Assert.Throws<ArgumentException>(() =>
            mockClient.Object.GetAIAgent(string.Empty, agentRecord));

        Assert.Equal("model", exception.ParamName);
    }

    /// <summary>
    /// Verify that GetAIAgent throws ArgumentException when model is whitespace.
    /// </summary>
    [Fact]
    public void GetAIAgent_WithAgentRecord_WithWhitespaceModel_ThrowsArgumentException()
    {
        // Arrange
        var mockClient = new Mock<AgentsClient>();
        AgentRecord agentRecord = this.CreateTestAgentRecord();

        // Act & Assert
        var exception = Assert.Throws<ArgumentException>(() =>
            mockClient.Object.GetAIAgent("   ", agentRecord));

        Assert.Equal("model", exception.ParamName);
    }

    /// <summary>
    /// Verify that GetAIAgent throws ArgumentNullException when agentRecord is null.
    /// </summary>
    [Fact]
    public void GetAIAgent_WithAgentRecord_WithNullAgentRecord_ThrowsArgumentNullException()
    {
        // Arrange
        var mockClient = new Mock<AgentsClient>();

        // Act & Assert
        var exception = Assert.Throws<ArgumentNullException>(() =>
            mockClient.Object.GetAIAgent("model", (AgentRecord)null!));

        Assert.Equal("agentRecord", exception.ParamName);
    }

    /// <summary>
    /// Verify that GetAIAgent with AgentRecord creates a valid agent.
    /// </summary>
    [Fact]
    public void GetAIAgent_WithAgentRecord_CreatesValidAgent()
    {
        // Arrange
        AgentsClient client = this.CreateTestAgentsClient();
        AgentRecord agentRecord = this.CreateTestAgentRecord();

        // Act
        var agent = client.GetAIAgent("test-model", agentRecord);

        // Assert
        Assert.NotNull(agent);
        Assert.Equal("test-agent", agent.Name);
    }

    /// <summary>
    /// Verify that GetAIAgent with AgentRecord and clientFactory applies the factory.
    /// </summary>
    [Fact]
    public void GetAIAgent_WithAgentRecord_WithClientFactory_AppliesFactoryCorrectly()
    {
        // Arrange
        AgentsClient client = this.CreateTestAgentsClient();
        AgentRecord agentRecord = this.CreateTestAgentRecord();
        TestChatClient? testChatClient = null;

        // Act
        var agent = client.GetAIAgent(
            "test-model",
            agentRecord,
            clientFactory: (innerClient) => testChatClient = new TestChatClient(innerClient));

        // Assert
        Assert.NotNull(agent);
        var retrievedTestClient = agent.GetService<TestChatClient>();
        Assert.NotNull(retrievedTestClient);
        Assert.Same(testChatClient, retrievedTestClient);
    }

    #endregion

    #region GetAIAgent(AgentsClient, string, AgentVersion) Tests

    /// <summary>
    /// Verify that GetAIAgent throws ArgumentNullException when agentsClient is null.
    /// </summary>
    [Fact]
    public void GetAIAgent_WithAgentVersion_WithNullClient_ThrowsArgumentNullException()
    {
        // Arrange
        AgentsClient? client = null;
        AgentVersion agentVersion = this.CreateTestAgentVersion();

        // Act & Assert
        var exception = Assert.Throws<ArgumentNullException>(() =>
            client!.GetAIAgent("model", agentVersion));

        Assert.Equal("agentsClient", exception.ParamName);
    }

    /// <summary>
    /// Verify that GetAIAgent throws ArgumentException when model is null.
    /// </summary>
    [Fact]
    public void GetAIAgent_WithAgentVersion_WithNullModel_ThrowsArgumentException()
    {
        // Arrange
        var mockClient = new Mock<AgentsClient>();
        AgentVersion agentVersion = this.CreateTestAgentVersion();

        // Act & Assert
        var exception = Assert.Throws<ArgumentException>(() =>
            mockClient.Object.GetAIAgent(null!, agentVersion));

        Assert.Equal("model", exception.ParamName);
    }

    /// <summary>
    /// Verify that GetAIAgent throws ArgumentNullException when agentVersion is null.
    /// </summary>
    [Fact]
    public void GetAIAgent_WithAgentVersion_WithNullAgentVersion_ThrowsArgumentNullException()
    {
        // Arrange
        var mockClient = new Mock<AgentsClient>();

        // Act & Assert
        var exception = Assert.Throws<ArgumentNullException>(() =>
            mockClient.Object.GetAIAgent("model", (AgentVersion)null!));

        Assert.Equal("agentVersion", exception.ParamName);
    }

    /// <summary>
    /// Verify that GetAIAgent with AgentVersion creates a valid agent.
    /// </summary>
    [Fact]
    public void GetAIAgent_WithAgentVersion_CreatesValidAgent()
    {
        // Arrange
        AgentsClient client = this.CreateTestAgentsClient();
        AgentVersion agentVersion = this.CreateTestAgentVersion();

        // Act
        var agent = client.GetAIAgent("test-model", agentVersion);

        // Assert
        Assert.NotNull(agent);
        Assert.Equal("test-agent", agent.Name);
    }

    /// <summary>
    /// Verify that GetAIAgent with AgentVersion and clientFactory applies the factory.
    /// </summary>
    [Fact]
    public void GetAIAgent_WithAgentVersion_WithClientFactory_AppliesFactoryCorrectly()
    {
        // Arrange
        AgentsClient client = this.CreateTestAgentsClient();
        AgentVersion agentVersion = this.CreateTestAgentVersion();
        TestChatClient? testChatClient = null;

        // Act
        var agent = client.GetAIAgent(
            "test-model",
            agentVersion,
            clientFactory: (innerClient) => testChatClient = new TestChatClient(innerClient));

        // Assert
        Assert.NotNull(agent);
        var retrievedTestClient = agent.GetService<TestChatClient>();
        Assert.NotNull(retrievedTestClient);
        Assert.Same(testChatClient, retrievedTestClient);
    }

    #endregion

    #region GetAIAgent(AgentsClient, string, string) Tests

    /// <summary>
    /// Verify that GetAIAgent throws ArgumentNullException when agentsClient is null.
    /// </summary>
    [Fact]
    public void GetAIAgent_ByName_WithNullClient_ThrowsArgumentNullException()
    {
        // Arrange
        AgentsClient? client = null;

        // Act & Assert
        var exception = Assert.Throws<ArgumentNullException>(() =>
            client!.GetAIAgent("model", "test-agent"));

        Assert.Equal("agentsClient", exception.ParamName);
    }

    /// <summary>
    /// Verify that GetAIAgent throws ArgumentException when model is null.
    /// </summary>
    [Fact]
    public void GetAIAgent_ByName_WithNullModel_ThrowsArgumentException()
    {
        // Arrange
        var mockClient = new Mock<AgentsClient>();

        // Act & Assert
        var exception = Assert.Throws<ArgumentException>(() =>
            mockClient.Object.GetAIAgent(null!, "test-agent"));

        Assert.Equal("model", exception.ParamName);
    }

    /// <summary>
    /// Verify that GetAIAgent throws ArgumentException when name is null.
    /// </summary>
    [Fact]
    public void GetAIAgent_ByName_WithNullName_ThrowsArgumentException()
    {
        // Arrange
        var mockClient = new Mock<AgentsClient>();

        // Act & Assert
        var exception = Assert.Throws<ArgumentException>(() =>
            mockClient.Object.GetAIAgent("model", (string)null!));

        Assert.Equal("name", exception.ParamName);
    }

    /// <summary>
    /// Verify that GetAIAgent throws ArgumentException when name is empty.
    /// </summary>
    [Fact]
    public void GetAIAgent_ByName_WithEmptyName_ThrowsArgumentException()
    {
        // Arrange
        var mockClient = new Mock<AgentsClient>();

        // Act & Assert
        var exception = Assert.Throws<ArgumentException>(() =>
            mockClient.Object.GetAIAgent("model", string.Empty));

        Assert.Equal("name", exception.ParamName);
    }

    /// <summary>
    /// Verify that GetAIAgent throws InvalidOperationException when agent is not found.
    /// </summary>
    [Fact]
    public void GetAIAgent_ByName_WithNonExistentAgent_ThrowsInvalidOperationException()
    {
        // Arrange
        var mockClient = new Mock<AgentsClient>();
        mockClient.Setup(c => c.GetAgent(It.IsAny<string>(), It.IsAny<CancellationToken>()))
            .Returns((AgentRecord?)null);

        // Act & Assert
        var exception = Assert.Throws<InvalidOperationException>(() =>
            mockClient.Object.GetAIAgent("model", "non-existent-agent"));

        Assert.Contains("not found", exception.Message);
    }

    #endregion

    #region GetAIAgentAsync(AgentsClient, string, string) Tests

    /// <summary>
    /// Verify that GetAIAgentAsync throws ArgumentNullException when agentsClient is null.
    /// </summary>
    [Fact]
    public async Task GetAIAgentAsync_ByName_WithNullClient_ThrowsArgumentNullExceptionAsync()
    {
        // Arrange
        AgentsClient? client = null;

        // Act & Assert
        var exception = await Assert.ThrowsAsync<ArgumentNullException>(() =>
            client!.GetAIAgentAsync("model", "test-agent"));

        Assert.Equal("agentsClient", exception.ParamName);
    }

    /// <summary>
    /// Verify that GetAIAgentAsync throws ArgumentException when model is null.
    /// </summary>
    [Fact]
    public async Task GetAIAgentAsync_ByName_WithNullModel_ThrowsArgumentExceptionAsync()
    {
        // Arrange
        var mockClient = new Mock<AgentsClient>();

        // Act & Assert
        var exception = await Assert.ThrowsAsync<ArgumentException>(() =>
            mockClient.Object.GetAIAgentAsync(null!, "test-agent"));

        Assert.Equal("model", exception.ParamName);
    }

    /// <summary>
    /// Verify that GetAIAgentAsync throws ArgumentException when name is null.
    /// </summary>
    [Fact]
    public async Task GetAIAgentAsync_ByName_WithNullName_ThrowsArgumentExceptionAsync()
    {
        // Arrange
        var mockClient = new Mock<AgentsClient>();

        // Act & Assert
        var exception = await Assert.ThrowsAsync<ArgumentException>(() =>
            mockClient.Object.GetAIAgentAsync("model", (string)null!));

        Assert.Equal("name", exception.ParamName);
    }

    /// <summary>
    /// Verify that GetAIAgentAsync throws InvalidOperationException when agent is not found.
    /// </summary>
    [Fact]
    public async Task GetAIAgentAsync_ByName_WithNonExistentAgent_ThrowsInvalidOperationExceptionAsync()
    {
        // Arrange
        var mockClient = new Mock<AgentsClient>();
        mockClient.Setup(c => c.GetAgentAsync(It.IsAny<string>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync((AgentRecord?)null);

        // Act & Assert
        var exception = await Assert.ThrowsAsync<InvalidOperationException>(() =>
            mockClient.Object.GetAIAgentAsync("model", "non-existent-agent"));

        Assert.Contains("not found", exception.Message);
    }

    #endregion

    #region GetAIAgent(AgentsClient, string, AgentRecord, ChatClientAgentOptions) Tests

    /// <summary>
    /// Verify that GetAIAgent with options uses provided options correctly.
    /// </summary>
    [Fact]
    public void GetAIAgent_WithAgentRecordAndOptions_UsesProvidedOptions()
    {
        // Arrange
        AgentsClient client = this.CreateTestAgentsClient();
        AgentRecord agentRecord = this.CreateTestAgentRecord();
        var options = new ChatClientAgentOptions
        {
            Name = "Override Name",
            Description = "Override Description",
            Instructions = "Override Instructions"
        };

        // Act
        var agent = client.GetAIAgent("test-model", agentRecord, options);

        // Assert
        Assert.NotNull(agent);
        Assert.Equal("Override Name", agent.Name);
        Assert.Equal("Override Description", agent.Description);
        Assert.Equal("Override Instructions", agent.Instructions);
    }

    /// <summary>
    /// Verify that GetAIAgent with null options falls back to agent definition.
    /// </summary>
    [Fact]
    public void GetAIAgent_WithAgentRecordAndNullOptions_UsesAgentDefinition()
    {
        // Arrange
        AgentsClient client = this.CreateTestAgentsClient();
        AgentRecord agentRecord = this.CreateTestAgentRecord();

        // Act
        var agent = client.GetAIAgent("test-model", agentRecord, options: null);

        // Assert
        Assert.NotNull(agent);
        Assert.Equal("test-agent", agent.Name);
    }

    #endregion

    #region GetAIAgentAsync(AgentsClient, string, string, ChatClientAgentOptions) Tests

    /// <summary>
    /// Verify that GetAIAgentAsync throws ArgumentNullException when options is null.
    /// </summary>
    [Fact]
    public async Task GetAIAgentAsync_WithOptions_WithNullOptions_ThrowsArgumentNullExceptionAsync()
    {
        // Arrange
        var mockClient = new Mock<AgentsClient>();

        // Act & Assert
        var exception = await Assert.ThrowsAsync<ArgumentNullException>(() =>
            mockClient.Object.GetAIAgentAsync("model", "test-agent", (ChatClientAgentOptions)null!));

        Assert.Equal("options", exception.ParamName);
    }

    #endregion

    #region CreateAIAgent(AgentsClient, string, string) Tests

    /// <summary>
    /// Verify that CreateAIAgent throws ArgumentNullException when agentsClient is null.
    /// </summary>
    [Fact]
    public void CreateAIAgent_WithBasicParams_WithNullClient_ThrowsArgumentNullException()
    {
        // Arrange
        AgentsClient? client = null;

        // Act & Assert
        var exception = Assert.Throws<ArgumentNullException>(() =>
            client!.CreateAIAgent("model", "test-agent"));

        Assert.Equal("agentsClient", exception.ParamName);
    }

    /// <summary>
    /// Verify that CreateAIAgent throws ArgumentException when model is null.
    /// </summary>
    [Fact]
    public void CreateAIAgent_WithBasicParams_WithNullModel_ThrowsArgumentException()
    {
        // Arrange
        var mockClient = new Mock<AgentsClient>();

        // Act & Assert
        var exception = Assert.Throws<ArgumentException>(() =>
            mockClient.Object.CreateAIAgent(null!, "test-agent"));

        Assert.Equal("model", exception.ParamName);
    }

    /// <summary>
    /// Verify that CreateAIAgent throws ArgumentException when name is null.
    /// </summary>
    [Fact]
    public void CreateAIAgent_WithBasicParams_WithNullName_ThrowsArgumentException()
    {
        // Arrange
        var mockClient = new Mock<AgentsClient>();

        // Act & Assert
        var exception = Assert.Throws<ArgumentException>(() =>
            mockClient.Object.CreateAIAgent("model", (string)null!));

        Assert.Equal("name", exception.ParamName);
    }

    #endregion

    #region CreateAIAgent(AgentsClient, string, AgentDefinition) Tests

    /// <summary>
    /// Verify that CreateAIAgent throws ArgumentNullException when agentsClient is null.
    /// </summary>
    [Fact]
    public void CreateAIAgent_WithAgentDefinition_WithNullClient_ThrowsArgumentNullException()
    {
        // Arrange
        AgentsClient? client = null;
        var definition = new PromptAgentDefinition("test-model");

        // Act & Assert
        var exception = Assert.Throws<ArgumentNullException>(() =>
            client!.CreateAIAgent("test-agent", definition));

        Assert.Equal("agentsClient", exception.ParamName);
    }

    /// <summary>
    /// Verify that CreateAIAgent throws ArgumentException when name is null.
    /// </summary>
    [Fact]
    public void CreateAIAgent_WithAgentDefinition_WithNullName_ThrowsArgumentException()
    {
        // Arrange
        var mockClient = new Mock<AgentsClient>();
        var definition = new PromptAgentDefinition("test-model");

        // Act & Assert
        var exception = Assert.Throws<ArgumentException>(() =>
            mockClient.Object.CreateAIAgent(null!, definition));

        Assert.Equal("name", exception.ParamName);
    }

    /// <summary>
    /// Verify that CreateAIAgent throws ArgumentNullException when agentDefinition is null.
    /// </summary>
    [Fact]
    public void CreateAIAgent_WithAgentDefinition_WithNullDefinition_ThrowsArgumentNullException()
    {
        // Arrange
        var mockClient = new Mock<AgentsClient>();

        // Act & Assert
        var exception = Assert.Throws<ArgumentNullException>(() =>
            mockClient.Object.CreateAIAgent("test-agent", (AgentDefinition)null!));

        Assert.Equal("agentDefinition", exception.ParamName);
    }

    /// <summary>
    /// Verify that CreateAIAgent throws ArgumentException when model is not provided.
    /// </summary>
    [Fact]
    public void CreateAIAgent_WithAgentDefinition_WithoutModel_ThrowsArgumentException()
    {
        // Arrange
        AgentsClient client = this.CreateTestAgentsClient();
        var definition = new TestAgentDefinition();

        // Act & Assert
        var exception = Assert.Throws<ArgumentException>(() =>
            client.CreateAIAgent("test-agent", definition, model: null));

        Assert.Contains("Model must be provided", exception.Message);
    }

    #endregion

    #region CreateAIAgent(AgentsClient, string, ChatClientAgentOptions) Tests

    /// <summary>
    /// Verify that CreateAIAgent throws ArgumentNullException when agentsClient is null.
    /// </summary>
    [Fact]
    public void CreateAIAgent_WithOptions_WithNullClient_ThrowsArgumentNullException()
    {
        // Arrange
        AgentsClient? client = null;
        var options = new ChatClientAgentOptions { Name = "test-agent" };

        // Act & Assert
        var exception = Assert.Throws<ArgumentNullException>(() =>
            client!.CreateAIAgent("model", options));

        Assert.Equal("agentsClient", exception.ParamName);
    }

    /// <summary>
    /// Verify that CreateAIAgent throws ArgumentException when model is null.
    /// </summary>
    [Fact]
    public void CreateAIAgent_WithOptions_WithNullModel_ThrowsArgumentException()
    {
        // Arrange
        var mockClient = new Mock<AgentsClient>();
        var options = new ChatClientAgentOptions { Name = "test-agent" };

        // Act & Assert
        var exception = Assert.Throws<ArgumentException>(() =>
            mockClient.Object.CreateAIAgent(null!, options));

        Assert.Equal("model", exception.ParamName);
    }

    /// <summary>
    /// Verify that CreateAIAgent throws ArgumentNullException when options is null.
    /// </summary>
    [Fact]
    public void CreateAIAgent_WithOptions_WithNullOptions_ThrowsArgumentNullException()
    {
        // Arrange
        var mockClient = new Mock<AgentsClient>();

        // Act & Assert
        var exception = Assert.Throws<ArgumentNullException>(() =>
            mockClient.Object.CreateAIAgent("model", (ChatClientAgentOptions)null!));

        Assert.Equal("options", exception.ParamName);
    }

    /// <summary>
    /// Verify that CreateAIAgent throws ArgumentException when options.Name is null.
    /// </summary>
    [Fact]
    public void CreateAIAgent_WithOptions_WithoutName_ThrowsArgumentException()
    {
        // Arrange
        AgentsClient client = this.CreateTestAgentsClient();
        var options = new ChatClientAgentOptions();

        // Act & Assert
        var exception = Assert.Throws<ArgumentException>(() =>
            client.CreateAIAgent("test-model", options));

        Assert.Contains("Agent name must be provided", exception.Message);
    }

    #endregion

    #region CreateAIAgentAsync Tests

    /// <summary>
    /// Verify that CreateAIAgentAsync throws ArgumentNullException when agentsClient is null.
    /// </summary>
    [Fact]
    public async Task CreateAIAgentAsync_WithAgentDefinition_WithNullClient_ThrowsArgumentNullExceptionAsync()
    {
        // Arrange
        AgentsClient? client = null;
        var definition = new PromptAgentDefinition("test-model");

        // Act & Assert
        var exception = await Assert.ThrowsAsync<ArgumentNullException>(() =>
            client!.CreateAIAgentAsync(definition));

        Assert.Equal("agentsClient", exception.ParamName);
    }

    /// <summary>
    /// Verify that CreateAIAgentAsync throws ArgumentNullException when agentDefinition is null.
    /// </summary>
    [Fact]
    public async Task CreateAIAgentAsync_WithAgentDefinition_WithNullDefinition_ThrowsArgumentNullExceptionAsync()
    {
        // Arrange
        var mockClient = new Mock<AgentsClient>();

        // Act & Assert
        var exception = await Assert.ThrowsAsync<ArgumentNullException>(() =>
            mockClient.Object.CreateAIAgentAsync((AgentDefinition)null!));

        Assert.Equal("agentDefinition", exception.ParamName);
    }

    /// <summary>
    /// Verify that CreateAIAgentAsync throws ArgumentException when model is not provided.
    /// </summary>
    [Fact]
    public async Task CreateAIAgentAsync_WithAgentDefinition_WithoutModel_ThrowsArgumentExceptionAsync()
    {
        // Arrange
        AgentsClient client = this.CreateTestAgentsClient();
        var definition = new TestAgentDefinition();

        // Act & Assert
        var exception = await Assert.ThrowsAsync<ArgumentException>(() =>
            client.CreateAIAgentAsync(definition, model: null));

        Assert.Contains("Model must be provided", exception.Message);
    }

    #endregion

    #region Helper Methods

    /// <summary>
    /// Creates a test AgentsClient with mocked behavior.
    /// </summary>
    private AgentsClient CreateTestAgentsClient()
    {
        var mockClient = new Mock<AgentsClient>();

        // Setup GetAgent to return a test agent record
        mockClient.Setup(c => c.GetAgent(It.IsAny<string>(), It.IsAny<CancellationToken>()))
            .Returns(this.CreateTestAgentRecord());

        // Setup GetAgentAsync to return a test agent record
        mockClient.Setup(c => c.GetAgentAsync(It.IsAny<string>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(this.CreateTestAgentRecord());

        // Setup CreateAgentVersion to return a test agent version
        mockClient.Setup(c => c.CreateAgentVersion(
                It.IsAny<string>(),
                It.IsAny<AgentDefinition>(),
                It.IsAny<AgentVersionCreationOptions>(),
                It.IsAny<CancellationToken>()))
            .Returns(this.CreateTestAgentVersion());

        // Setup CreateAgentVersionAsync to return a test agent version
        mockClient.Setup(c => c.CreateAgentVersionAsync(
                It.IsAny<string>(),
                It.IsAny<AgentDefinition>(),
                It.IsAny<AgentVersionCreationOptions>(),
                It.IsAny<CancellationToken>()))
            .ReturnsAsync(this.CreateTestAgentVersion());

        // Setup CreateAgent to return a test agent record
        mockClient.Setup(c => c.CreateAgent(
                It.IsAny<string>(),
                It.IsAny<AgentDefinition>(),
                It.IsAny<AgentCreationOptions>(),
                It.IsAny<CancellationToken>()))
            .Returns(this.CreateTestAgentRecord());

        return mockClient.Object;
    }

    /// <summary>
    /// Creates a test AgentRecord for testing.
    /// </summary>
    private AgentRecord CreateTestAgentRecord()
    {
        AgentVersion version = this.CreateTestAgentVersion();
        var mockRecord = new Mock<AgentRecord>();
        var mockVersions = new Mock<AgentVersions>();

        mockVersions.Setup(v => v.Latest).Returns(version);
        mockRecord.Setup(r => r.Versions).Returns(mockVersions.Object);

        return mockRecord.Object;
    }

    /// <summary>
    /// Creates a test AgentVersion for testing.
    /// </summary>
    private AgentVersion CreateTestAgentVersion()
    {
        var mockVersion = new Mock<AgentVersion>();
        var definition = new PromptAgentDefinition("test-model")
        {
            Instructions = "Test instructions",
        };

        mockVersion.Setup(v => v.Name).Returns("test-agent");
        mockVersion.Setup(v => v.Id).Returns("version-1");
        mockVersion.Setup(v => v.Description).Returns("Test description");
        mockVersion.Setup(v => v.Definition).Returns(definition);

        return mockVersion.Object;
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
    /// Test agent definition that doesn't inherit from PromptAgentDefinition.
    /// </summary>
    private sealed class TestAgentDefinition : AgentDefinition
    {
    }

    #endregion
}
