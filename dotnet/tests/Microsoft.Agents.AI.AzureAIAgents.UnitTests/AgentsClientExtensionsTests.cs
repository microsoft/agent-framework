// Copyright (c) Microsoft. All rights reserved.

using System;
using System.ClientModel;
using System.ClientModel.Primitives;
using System.Collections.Generic;
using System.IO;
using System.Threading;
using System.Threading.Tasks;
using Azure.AI.Agents;
using Microsoft.Extensions.AI;
using Moq;
using OpenAI;

namespace Microsoft.Agents.AI.AzureAIAgents.UnitTests;

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
            client!.GetAIAgent("model", agentRecord, chatOptions: null));

        Assert.Equal("agentsClient", exception.ParamName);
    }

    /// <summary>
    /// Verify that GetAIAgent throws ArgumentNullException when model is null.
    /// </summary>
    [Fact]
    public void GetAIAgent_WithAgentRecord_WithNullModel_ThrowsArgumentNullException()
    {
        // Arrange
        var mockClient = new Mock<AgentsClient>();
        AgentRecord agentRecord = this.CreateTestAgentRecord();

        // Act & Assert
        var exception = Assert.Throws<ArgumentNullException>(() =>
            mockClient.Object.GetAIAgent(null!, agentRecord, chatOptions: null));

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
            mockClient.Object.GetAIAgent(string.Empty, agentRecord, chatOptions: null));

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
            mockClient.Object.GetAIAgent("   ", agentRecord, chatOptions: null));

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
            mockClient.Object.GetAIAgent("model", (AgentRecord)null!, chatOptions: null));

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
        var agent = client.GetAIAgent("test-model", agentRecord, chatOptions: null);

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
        AgentsClient client = this.CreateTestAgentsClient();
        AgentRecord agentRecord = this.CreateTestAgentRecord();
        TestChatClient? testChatClient = null;

        // Act
        var agent = client.GetAIAgent(
            "test-model",
            agentRecord,
            chatOptions: null,
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
            client!.GetAIAgent("model", agentVersion, chatOptions: null));

        Assert.Equal("agentsClient", exception.ParamName);
    }

    /// <summary>
    /// Verify that GetAIAgent throws ArgumentNullException when model is null.
    /// </summary>
    [Fact]
    public void GetAIAgent_WithAgentVersion_WithNullModel_ThrowsArgumentNullException()
    {
        // Arrange
        var mockClient = new Mock<AgentsClient>();
        AgentVersion agentVersion = this.CreateTestAgentVersion();

        // Act & Assert
        var exception = Assert.Throws<ArgumentNullException>(() =>
            mockClient.Object.GetAIAgent(null!, agentVersion, chatOptions: null));

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
            mockClient.Object.GetAIAgent("model", (AgentVersion)null!, chatOptions: null));

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
        var agent = client.GetAIAgent("test-model", agentVersion, chatOptions: null);

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
        AgentsClient client = this.CreateTestAgentsClient();
        AgentVersion agentVersion = this.CreateTestAgentVersion();
        TestChatClient? testChatClient = null;

        // Act
        var agent = client.GetAIAgent(
            "test-model",
            agentVersion,
            chatOptions: null,
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
            client!.GetAIAgent("model", "test-agent", chatOptions: null));

        Assert.Equal("agentsClient", exception.ParamName);
    }

    /// <summary>
    /// Verify that GetAIAgent throws ArgumentNullException when model is null.
    /// </summary>
    [Fact]
    public void GetAIAgent_ByName_WithNullModel_ThrowsArgumentNullException()
    {
        // Arrange
        var mockClient = new Mock<AgentsClient>();

        // Act & Assert
        var exception = Assert.Throws<ArgumentNullException>(() =>
            mockClient.Object.GetAIAgent(null!, "test-agent", chatOptions: null));

        Assert.Equal("model", exception.ParamName);
    }

    /// <summary>
    /// Verify that GetAIAgent throws ArgumentNullException when name is null.
    /// </summary>
    [Fact]
    public void GetAIAgent_ByName_WithNullName_ThrowsArgumentNullException()
    {
        // Arrange
        var mockClient = new Mock<AgentsClient>();

        // Act & Assert
        var exception = Assert.Throws<ArgumentNullException>(() =>
            mockClient.Object.GetAIAgent("model", (string)null!, chatOptions: null));

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
            mockClient.Object.GetAIAgent("model", string.Empty, chatOptions: null));

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
            .Returns(ClientResult.FromOptionalValue((AgentRecord)null!, new MockPipelineResponse(200)));

        // Act & Assert
        var exception = Assert.Throws<InvalidOperationException>(() =>
            mockClient.Object.GetAIAgent("model", "non-existent-agent", chatOptions: null));

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
    /// Verify that GetAIAgentAsync throws ArgumentNullException when model is null.
    /// </summary>
    [Fact]
    public async Task GetAIAgentAsync_ByName_WithNullModel_ThrowsArgumentNullExceptionAsync()
    {
        // Arrange
        var mockClient = new Mock<AgentsClient>();

        // Act & Assert
        var exception = await Assert.ThrowsAsync<ArgumentNullException>(() =>
            mockClient.Object.GetAIAgentAsync(null!, "test-agent"));

        Assert.Equal("model", exception.ParamName);
    }

    /// <summary>
    /// Verify that GetAIAgentAsync throws ArgumentNullException when name is null.
    /// </summary>
    [Fact]
    public async Task GetAIAgentAsync_ByName_WithNullName_ThrowsArgumentNullExceptionAsync()
    {
        // Arrange
        var mockClient = new Mock<AgentsClient>();

        // Act & Assert
        var exception = await Assert.ThrowsAsync<ArgumentNullException>(() =>
            mockClient.Object.GetAIAgentAsync("model", null!));

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
            .ReturnsAsync(ClientResult.FromOptionalValue((AgentRecord)null!, new MockPipelineResponse(200)));

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
        Assert.Equal("agent_abc123", agent.Name);
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
    /// Verify that CreateAIAgent throws ArgumentNullException when model is null.
    /// </summary>
    [Fact]
    public void CreateAIAgent_WithBasicParams_WithNullModel_ThrowsArgumentNullException()
    {
        // Arrange
        var mockClient = new Mock<AgentsClient>();

        // Act & Assert
        var exception = Assert.Throws<ArgumentNullException>(() =>
            mockClient.Object.CreateAIAgent(null!, "test-agent"));

        Assert.Equal("model", exception.ParamName);
    }

    /// <summary>
    /// Verify that CreateAIAgent throws ArgumentNullException when name is null.
    /// </summary>
    [Fact]
    public void CreateAIAgent_WithBasicParams_WithNullName_ThrowsArgumentNullException()
    {
        // Arrange
        var mockClient = new Mock<AgentsClient>();

        // Act & Assert
        var exception = Assert.Throws<ArgumentNullException>(() =>
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
    /// Verify that CreateAIAgent throws ArgumentNullException when name is null.
    /// </summary>
    [Fact]
    public void CreateAIAgent_WithAgentDefinition_WithNullName_ThrowsArgumentNullException()
    {
        // Arrange
        var mockClient = new Mock<AgentsClient>();
        var definition = new PromptAgentDefinition("test-model");

        // Act & Assert
        var exception = Assert.Throws<ArgumentNullException>(() =>
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
    public void CreateAIAgent_WithAgentDefinition_WithoutModel_ThrowsArgumentNullException()
    {
        // Arrange
        AgentsClient client = this.CreateTestAgentsClient();
        var definition = new PromptAgentDefinition("");

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
    /// Verify that CreateAIAgent throws ArgumentNullException when model is null.
    /// </summary>
    [Fact]
    public void CreateAIAgent_WithOptions_WithNullModel_ThrowsArgumentNullException()
    {
        // Arrange
        var mockClient = new Mock<AgentsClient>();
        var options = new ChatClientAgentOptions { Name = "test-agent" };

        // Act & Assert
        var exception = Assert.Throws<ArgumentNullException>(() =>
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
    /// Verify that CreateAIAgent throws ArgumentNullException when options.Name is null.
    /// </summary>
    [Fact]
    public void CreateAIAgent_WithOptions_WithoutName_ThrowsException()
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
            mockClient.Object.CreateAIAgentAsync(null!));

        Assert.Equal("agentDefinition", exception.ParamName);
    }

    /// <summary>
    /// Verify that CreateAIAgentAsync throws ArgumentException when model is not provided.
    /// </summary>
    [Fact]
    public async Task CreateAIAgentAsync_WithAgentDefinition_WithoutModel_ThrowsExceptionAsync()
    {
        // Arrange
        AgentsClient client = this.CreateTestAgentsClient();
        var definition = new PromptAgentDefinition("");

        // Act & Assert
        var exception = await Assert.ThrowsAsync<ArgumentException>(() =>
            client.CreateAIAgentAsync(definition, model: null));

        Assert.Contains("Model must be provided", exception.Message);
    }

    #endregion

    #region Helper Methods

    /// <summary>
    /// Creates a test AgentsClient with fake behavior.
    /// </summary>
    private FakeAgentsClient CreateTestAgentsClient()
    {
        return new FakeAgentsClient();
    }

    /// <summary>
    /// Creates a test AgentRecord for testing.
    /// </summary>
    private AgentRecord CreateTestAgentRecord()
    {
        return ModelReaderWriter.Read<AgentRecord>(BinaryData.FromString(AgentTestJsonObject))!;
    }

    private const string AgentTestJsonObject = """
            {
              "object": "agent",
              "id": "agent_abc123",
              "name": "agent_abc123",
              "versions": {
                "latest": {
                  "metadata": {},
                  "object": "agent.version",
                  "id": "agent_abc123:1",
                  "name": "agent_abc123",
                  "version": "1",
                  "description": "",
                  "created_at": 1761771936,
                  "definition": {
                    "kind": "prompt",
                    "model": "gpt-5-mini",
                    "instructions": "You are a storytelling agent. You craft engaging one-line stories based on user prompts and context."
                  }
                }
              }
            }
            """;

    private const string AgentVersionTestJsonObject = """
            {
              "object": "agent.version",
              "id": "agent_abc123:1",
              "name": "agent_abc123",
              "version": "1",
              "description": "",
              "created_at": 1761771936,
              "definition": {
                "kind": "prompt",
                "model": "gpt-5-mini",
                "instructions": "You are a storytelling agent. You craft engaging one-line stories based on user prompts and context."
              }
            }
            """;

    /// <summary>
    /// Creates a test AgentVersion for testing.
    /// </summary>
    private AgentVersion CreateTestAgentVersion()
    {
        return ModelReaderWriter.Read<AgentVersion>(BinaryData.FromString(AgentVersionTestJsonObject))!;
    }

    /// <summary>
    /// Fake AgentsClient for testing.
    /// </summary>
    private sealed class FakeAgentsClient : AgentsClient
    {
        public FakeAgentsClient()
        {
        }

        public override OpenAIClient GetOpenAIClient(OpenAIClientOptions? options = null)
        {
            return new OpenAIClient(new ApiKeyCredential("test-key"), options);
        }

        public override ClientResult<AgentRecord> GetAgent(string agentName, CancellationToken cancellationToken = default)
        {
            return ClientResult.FromValue(ModelReaderWriter.Read<AgentRecord>(BinaryData.FromString(AgentTestJsonObject))!, new MockPipelineResponse(200));
        }

        public override Task<ClientResult<AgentRecord>> GetAgentAsync(string agentName, CancellationToken cancellationToken = default)
        {
            return Task.FromResult(ClientResult.FromValue(ModelReaderWriter.Read<AgentRecord>(BinaryData.FromString(AgentTestJsonObject))!, new MockPipelineResponse(200)));
        }

        public override ClientResult<AgentVersion> CreateAgentVersion(string agentName, AgentDefinition definition, AgentVersionCreationOptions? options = null, CancellationToken cancellationToken = default)
        {
            return ClientResult.FromValue(ModelReaderWriter.Read<AgentVersion>(BinaryData.FromString(AgentVersionTestJsonObject))!, new MockPipelineResponse(200));
        }

        public override Task<ClientResult<AgentVersion>> CreateAgentVersionAsync(string agentName, AgentDefinition definition, AgentVersionCreationOptions? options = null, CancellationToken cancellationToken = default)
        {
            return Task.FromResult(ClientResult.FromValue(ModelReaderWriter.Read<AgentVersion>(BinaryData.FromString(AgentVersionTestJsonObject))!, new MockPipelineResponse(200)));
        }

        public override ClientResult<AgentRecord> CreateAgent(string name, AgentDefinition definition, AgentCreationOptions? options = null, CancellationToken cancellationToken = default)
        {
            return ClientResult.FromValue(ModelReaderWriter.Read<AgentRecord>(BinaryData.FromString(AgentTestJsonObject))!, new MockPipelineResponse(200));
        }

        public override Task<ClientResult<AgentRecord>> CreateAgentAsync(string name, AgentDefinition definition, AgentCreationOptions? options = null, CancellationToken cancellationToken = default)
        {
            return Task.FromResult(ClientResult.FromValue(ModelReaderWriter.Read<AgentRecord>(BinaryData.FromString(AgentTestJsonObject))!, new MockPipelineResponse(200)));
        }
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

        public MockPipelineResponse(int status)
        {
            this._status = status;
        }

        public override int Status => this._status;

        public override string ReasonPhrase => "OK";

        public override Stream? ContentStream
        {
            get => null;
            set { }
        }

        public override BinaryData Content => BinaryData.Empty;

        protected override PipelineResponseHeaders HeadersCore => new EmptyPipelineResponseHeaders();

        public override BinaryData BufferContent(CancellationToken cancellationToken = default) =>
            throw new NotSupportedException("Buffering content is not supported for mock responses.");

        public override ValueTask<BinaryData> BufferContentAsync(CancellationToken cancellationToken = default) =>
            throw new NotSupportedException("Buffering content asynchronously is not supported for mock responses.");

        public override void Dispose()
        {
        }

        private sealed class EmptyPipelineResponseHeaders : PipelineResponseHeaders
        {
            public override bool TryGetValue(string name, out string? value)
            {
                value = null;
                return false;
            }

            public override bool TryGetValues(string name, out IEnumerable<string>? values)
            {
                values = null;
                return false;
            }

            public override IEnumerator<KeyValuePair<string, string>> GetEnumerator()
            {
                yield break;
            }
        }
    }

    #endregion
}
