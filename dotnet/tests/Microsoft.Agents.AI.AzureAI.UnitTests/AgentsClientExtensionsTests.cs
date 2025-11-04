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
using OpenAI.Responses;

namespace Microsoft.Agents.AI.AzureAI.UnitTests;

/// <summary>
/// Unit tests for the <see cref="AgentsClientExtensions"/> class.
/// </summary>
public sealed class AgentsClientExtensionsTests
{
    #region GetAIAgent(AgentsClient, AgentRecord) Tests

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
            client!.GetAIAgent(agentRecord));

        Assert.Equal("agentsClient", exception.ParamName);
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
        AgentsClient client = this.CreateTestAgentsClient();
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
        AgentsClient client = this.CreateTestAgentsClient();
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

    #region GetAIAgent(AgentsClient, AgentVersion) Tests

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
            client!.GetAIAgent(agentVersion));

        Assert.Equal("agentsClient", exception.ParamName);
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
        AgentsClient client = this.CreateTestAgentsClient();
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
        AgentsClient client = this.CreateTestAgentsClient();
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

    #endregion

    #region GetAIAgent(AgentsClient, string) Tests

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
            client!.GetAIAgent("test-agent"));

        Assert.Equal("agentsClient", exception.ParamName);
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
        var mockClient = new Mock<AgentsClient>();

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
        var mockClient = new Mock<AgentsClient>();
        mockClient.Setup(c => c.GetAgent(It.IsAny<string>(), It.IsAny<CancellationToken>()))
            .Returns(ClientResult.FromOptionalValue((AgentRecord)null!, new MockPipelineResponse(200)));

        // Act & Assert
        var exception = Assert.Throws<InvalidOperationException>(() =>
            mockClient.Object.GetAIAgent("non-existent-agent"));

        Assert.Contains("not found", exception.Message);
    }

    #endregion

    #region GetAIAgentAsync(AgentsClient, string) Tests

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
            client!.GetAIAgentAsync("test-agent"));

        Assert.Equal("agentsClient", exception.ParamName);
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
        var mockClient = new Mock<AgentsClient>();
        mockClient.Setup(c => c.GetAgentAsync(It.IsAny<string>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(ClientResult.FromOptionalValue((AgentRecord)null!, new MockPipelineResponse(200)));

        // Act & Assert
        var exception = await Assert.ThrowsAsync<InvalidOperationException>(() =>
            mockClient.Object.GetAIAgentAsync("non-existent-agent"));

        Assert.Contains("not found", exception.Message);
    }

    #endregion

    #region GetAIAgent(AgentsClient, AgentRecord) with tools Tests

    /// <summary>
    /// Verify that GetAIAgent with tools parameter passes tools to the agent.
    /// </summary>
    [Fact]
    public void GetAIAgent_WithAgentRecordAndTools_PassesToolsToAgent()
    {
        // Arrange
        AgentsClient client = this.CreateTestAgentsClient();
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
    }

    /// <summary>
    /// Verify that GetAIAgent with null tools works correctly.
    /// </summary>
    [Fact]
    public void GetAIAgent_WithAgentRecordAndNullTools_WorksCorrectly()
    {
        // Arrange
        AgentsClient client = this.CreateTestAgentsClient();
        AgentRecord agentRecord = this.CreateTestAgentRecord();

        // Act
        var agent = client.GetAIAgent(agentRecord, tools: null);

        // Assert
        Assert.NotNull(agent);
        Assert.Equal("agent_abc123", agent.Name);
    }

    #endregion

    #region GetAIAgentAsync(AgentsClient, string) with tools Tests

    /// <summary>
    /// Verify that GetAIAgentAsync with tools parameter creates an agent.
    /// </summary>
    [Fact]
    public async Task GetAIAgentAsync_WithNameAndTools_CreatesAgentAsync()
    {
        // Arrange
        AgentsClient client = this.CreateTestAgentsClient();
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
            client!.CreateAIAgent("test-agent", "model", "instructions"));

        Assert.Equal("agentsClient", exception.ParamName);
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
            mockClient.Object.CreateAIAgent(null!, "model", "instructions"));

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

    #endregion

    #region CreateAIAgent(AgentsClient, ChatClientAgentOptions, string) Tests

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
            client!.CreateAIAgentAsync("agent-name", definition));

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
            mockClient.Object.CreateAIAgentAsync(name: "agent-name", null!));

        Assert.Equal("agentDefinition", exception.ParamName);
    }

    #endregion

    #region Tool Validation Tests

    /// <summary>
    /// Verify that CreateAIAgent throws ArgumentException when agent definition contains inline tools.
    /// </summary>
    [Fact]
    public void CreateAIAgent_WithInlineToolsInDefinition_ThrowsArgumentException()
    {
        // Arrange
        AgentsClient client = this.CreateTestAgentsClient();
        var definition = new PromptAgentDefinition("test-model");
        definition.Tools.Add(ResponseTool.CreateFunctionTool("inline_tool", BinaryData.FromString("{}"), strictModeEnabled: false));

        // Act & Assert
        var exception = Assert.Throws<ArgumentException>(() =>
            client.CreateAIAgent("test-agent", definition));

        Assert.Contains("dedicated tools parameter", exception.Message);
    }

    /// <summary>
    /// Verify that CreateAIAgent with tools parameter applies tools to the agent definition.
    /// </summary>
    [Fact]
    public void CreateAIAgent_WithToolsParameter_AppliesToolsToDefinition()
    {
        // Arrange
        var definition = new PromptAgentDefinition("test-model");
        var tools = new List<AITool>
        {
            AIFunctionFactory.Create(() => "test", "test_function", "A test function")
        };

        var agentDefinitionResponse = GeneratePromptDefinitionResponse(definition, tools);
        AgentsClient client = this.CreateTestAgentsClient(agentName: "test-agent", agentDefinitionResponse: agentDefinitionResponse);

        // Act
        var agent = client.CreateAIAgent("test-agent", definition, tools: tools);

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
    /// Verify that GetAIAgent with inline tools in agent definition throws ArgumentException.
    /// </summary>
    [Fact]
    public void GetAIAgent_WithInlineToolsInDefinition_ThrowsArgumentException()
    {
        // Arrange
        AgentsClient client = this.CreateTestAgentsClient();
        var agentVersion = this.CreateTestAgentVersion();

        // Manually add tools to the definition to simulate inline tools
        if (agentVersion.Definition is PromptAgentDefinition promptDef)
        {
            promptDef.Tools.Add(ResponseTool.CreateFunctionTool("inline_tool", BinaryData.FromString("{}"), strictModeEnabled: false));
        }

        // Act & Assert
        var exception = Assert.Throws<ArgumentException>(() =>
            client.GetAIAgent(agentVersion));

        Assert.Contains("tools parameter", exception.Message);
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
        AgentsClient client = this.CreateTestAgentsClient();
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
    /// Verify that CreateAIAgent with parameter tools creates an agent successfully.
    /// </summary>
    [Fact]
    public void CreateAIAgent_WithParameterTools_CreatesAgentSuccessfully()
    {
        // Arrange
        var definition = new PromptAgentDefinition("test-model") { Instructions = "Test instructions" };
        var tools = new List<AITool>
        {
            AIFunctionFactory.Create(() => "result", "create_tool", "A tool for creation")
        };

        // Simulate agent definition response with the tools
        var definitionResponse = GeneratePromptDefinitionResponse(definition, tools);

        AgentsClient client = this.CreateTestAgentsClient(agentDefinitionResponse: definitionResponse);

        // Act
        var agent = client.CreateAIAgent("test-agent", definition, tools: tools);

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
    /// Verify that CreateAIAgent creates an agent successfully when provided with a mix of custom and hosted tools.
    /// </summary>
    [Fact]
    public void CreateAIAgent_WithMixedTools_CreatesAgentSuccessfully()
    {
        // Arrange
        var definition = new PromptAgentDefinition("test-model") { Instructions = "Test instructions" };
        var tools = new List<AITool>
        {
            AIFunctionFactory.Create(() => "result", "create_tool", "A tool for creation"),
            new HostedWebSearchTool(),
            new HostedFileSearchTool(),
        };

        // Simulate agent definition response with the tools
        var definitionResponse = new PromptAgentDefinition("test-model") { Instructions = "Test instructions" };
        foreach (var tool in tools)
        {
            definitionResponse.Tools.Add(tool.GetService<ResponseTool>() ?? tool.AsOpenAIResponseTool());
        }

        AgentsClient client = this.CreateTestAgentsClient(agentDefinitionResponse: definitionResponse);

        // Act
        var agent = client.CreateAIAgent("test-agent", definition, tools: tools);

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
    /// Verifies that CreateAIAgent accepts tools provided as ResponseTool instances and correctly converts them to AITool instances, resulting in successful agent creation.
    /// </summary>
    [Fact]
    public void CreateAIAgent_WithResponseToolsAsAITools_CreatesAgentSuccessfully()
    {
        // Arrange
        var definition = new PromptAgentDefinition("test-model") { Instructions = "Test instructions" };

        var fabricParameters = new FabricDataAgentToolParameters();
        fabricParameters.ProjectConnections.Add(new ToolProjectConnection("connection-id"));

        var sharepointParameters = new SharepointGroundingToolParameters();
        sharepointParameters.ProjectConnections.Add(new ToolProjectConnection("connection-id"));

        var structuredOutputs = new StructuredOutputDefinition("name", "description", new Dictionary<string, BinaryData>()
        {
            ["structured-1"] = BinaryData.FromString(AIJsonUtilities.CreateJsonSchema(new { id = "test" }.GetType()).ToString())
        }, false);

        ResponseTool openAIResponseTool = (ResponseTool)new AzureAISearchAgentTool(new());

        var tools = new List<AITool>
        {
            AIFunctionFactory.Create(() => "result", "create_tool", "A tool for creation"),
            ((ResponseTool)AgentTool.CreateBingCustomSearchTool(new BingCustomSearchToolParameters([new BingCustomSearchConfiguration("connection-id", "instance-name")]))).AsAITool(),
            ((ResponseTool)AgentTool.CreateBrowserAutomationTool(new BrowserAutomationToolParameters(new BrowserAutomationToolConnectionParameters("id")))).AsAITool(),
            AgentTool.CreateA2ATool(new Uri("https://test-uri.microsoft.com")).AsAITool(),
            ((ResponseTool)AgentTool.CreateBingGroundingTool(new BingGroundingSearchToolParameters([new BingGroundingSearchConfiguration("connection-id")]))).AsAITool(),
            ((ResponseTool)AgentTool.CreateMicrosoftFabricTool(fabricParameters)).AsAITool(),
            ((ResponseTool)AgentTool.CreateOpenApiTool(new OpenApiFunctionDefinition("name", BinaryData.FromString(OpenAPISpec), new OpenApiAnonymousAuthDetails()))).AsAITool(),
            ((ResponseTool)AgentTool.CreateSharepointTool(sharepointParameters)).AsAITool(),
            ((ResponseTool)AgentTool.CreateStructuredOutputsTool(structuredOutputs)).AsAITool(),

            // Workaround the bug with the AgentTool.CreateAzureAISearchTool() extension
            // Using the extension method AgentTool.CreateAzureAISearchTool() fails serialization, 
            // TODO: Revert back once bug fix is applied: https://github.com/Azure/azure-sdk-for-net/pull/53656
            ((ResponseTool)new AzureAISearchAgentTool(new())).AsAITool()
        };

        // Generate agent definition response with the tools
        var definitionResponse = GeneratePromptDefinitionResponse(definition, tools);

        AgentsClient client = this.CreateTestAgentsClient(agentDefinitionResponse: definitionResponse);

        // Act
        var agent = client.CreateAIAgent("test-agent", definition, tools: tools);

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

        AgentsClient client = this.CreateTestAgentsClient(agentName: "test-agent", agentDefinitionResponse: definitionResponse);

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
    /// Verify that CreateAIAgentAsync with tools parameter creates an agent.
    /// </summary>
    [Fact]
    public async Task CreateAIAgentAsync_WithToolsParameter_CreatesAgentAsync()
    {
        // Arrange
        AgentsClient client = this.CreateTestAgentsClient();
        var definition = new PromptAgentDefinition("test-model") { Instructions = "Test instructions" };
        var tools = new List<AITool>
        {
            AIFunctionFactory.Create(() => "async_result", "async_tool", "An async tool")
        };

        // Act
        var agent = await client.CreateAIAgentAsync("test-agent", definition, tools: tools);

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
        AgentsClient client = this.CreateTestAgentsClient();
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

    #region AzureAIChatClient Behavior Tests

    /// <summary>
    /// Verify that the underlying chat client created by extension methods can be wrapped with clientFactory.
    /// </summary>
    [Fact]
    public void GetAIAgent_WithClientFactory_WrapsUnderlyingChatClient()
    {
        // Arrange
        AgentsClient client = this.CreateTestAgentsClient();
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
        AgentsClient client = this.CreateTestAgentsClient();
        var definition = new PromptAgentDefinition("test-model") { Instructions = "Test" };
        IChatClient? receivedClient = null;

        // Act
        var agent = client.CreateAIAgent(
            "test-agent",
            definition,
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
        AgentsClient client = this.CreateTestAgentsClient();
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
        AgentsClient client = this.CreateTestAgentsClient(AgentName, Instructions);

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
    /// Verify that agent created with tools and clientFactory is created successfully.
    /// </summary>
    [Fact]
    public void CreateAIAgent_WithToolsAndClientFactory_CreatesAgentSuccessfully()
    {
        // Arrange
        var definition = new PromptAgentDefinition("test-model") { Instructions = "Test" };
        var tools = new List<AITool>
        {
            AIFunctionFactory.Create(() => "test", "test_tool", "A test tool")
        };

        var agentDefinitionResponse = GeneratePromptDefinitionResponse(definition, tools);
        AgentsClient client = this.CreateTestAgentsClient(agentName: "test-agent", agentDefinitionResponse: agentDefinitionResponse);

        // Act
        var agent = client.CreateAIAgent(
            "test-agent",
            definition,
            tools: tools,
            clientFactory: (innerClient) => new TestChatClient(innerClient));

        // Assert
        Assert.NotNull(agent);
        var wrappedClient = agent.GetService<TestChatClient>();
        Assert.NotNull(wrappedClient);
        var agentVersion = agent.GetService<AgentVersion>();
        Assert.NotNull(agentVersion);
        if (agentVersion.Definition is PromptAgentDefinition promptDef)
        {
            Assert.NotEmpty(promptDef.Tools);
            Assert.Single(promptDef.Tools);
        }
    }

    #endregion

    #region Helper Methods

    /// <summary>
    /// Creates a test AgentsClient with fake behavior.
    /// </summary>
    private FakeAgentsClient CreateTestAgentsClient(string? agentName = null, string? instructions = null, string? description = null, AgentDefinition? agentDefinitionResponse = null)
    {
        return new FakeAgentsClient(agentName, instructions, description, agentDefinitionResponse);
    }

    /// <summary>
    /// Creates a test AgentRecord for testing.
    /// </summary>
    private AgentRecord CreateTestAgentRecord()
    {
        return ModelReaderWriter.Read<AgentRecord>(BinaryData.FromString(AgentTestJsonObject))!;
    }

    private const string AgentDefinitionPlaceholder = """
        {
            "kind": "prompt",
            "model": "gpt-5-mini",
            "instructions": "You are a storytelling agent. You craft engaging one-line stories based on user prompts and context.",
            "tools": []
        }
        """;

    private const string AgentTestJsonObject = $$"""
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
                  "definition": {{AgentDefinitionPlaceholder}}
                }
              }
            }
            """;

    private const string AgentVersionTestJsonObject = $$"""
            {
              "object": "agent.version",
              "id": "agent_abc123:1",
              "name": "agent_abc123",
              "version": "1",
              "description": "",
              "created_at": 1761771936,
              "definition": {{AgentDefinitionPlaceholder}}
            }
            """;

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
        return ModelReaderWriter.Read<AgentVersion>(BinaryData.FromString(AgentVersionTestJsonObject))!;
    }

    /// <summary>
    /// Fake AgentsClient for testing.
    /// </summary>
    private sealed class FakeAgentsClient : AgentsClient
    {
        private readonly string? _agentName;
        private readonly string? _instructions;
        private readonly string? _description;
        private readonly AgentDefinition? _agentDefinition;

        public FakeAgentsClient(string? agentName = null, string? instructions = null, string? description = null, AgentDefinition? agentDefinitionResponse = null)
        {
            this._agentName = agentName;
            this._instructions = instructions;
            this._description = description;
            this._agentDefinition = agentDefinitionResponse;
        }

        public override OpenAIClient GetOpenAIClient(OpenAIClientOptions? options = null)
        {
            return new OpenAIClient(new ApiKeyCredential("test-key"), options);
        }

        public override ClientResult<AgentRecord> GetAgent(string agentName, CancellationToken cancellationToken = default)
        {
            return ClientResult.FromValue(ModelReaderWriter.Read<AgentRecord>(BinaryData.FromString(this.ApplyResponseChanges(AgentTestJsonObject)))!, new MockPipelineResponse(200));
        }

        public override Task<ClientResult<AgentRecord>> GetAgentAsync(string agentName, CancellationToken cancellationToken = default)
        {
            return Task.FromResult(ClientResult.FromValue(ModelReaderWriter.Read<AgentRecord>(BinaryData.FromString(this.ApplyResponseChanges(AgentTestJsonObject)))!, new MockPipelineResponse(200)));
        }

        public override ClientResult<AgentVersion> CreateAgentVersion(string agentName, AgentDefinition definition, AgentVersionCreationOptions? options = null, CancellationToken cancellationToken = default)
        {
            return ClientResult.FromValue(ModelReaderWriter.Read<AgentVersion>(BinaryData.FromString(this.ApplyResponseChanges(AgentVersionTestJsonObject)))!, new MockPipelineResponse(200));
        }

        public override Task<ClientResult<AgentVersion>> CreateAgentVersionAsync(string agentName, AgentDefinition definition, AgentVersionCreationOptions? options = null, CancellationToken cancellationToken = default)
        {
            return Task.FromResult(ClientResult.FromValue(ModelReaderWriter.Read<AgentVersion>(BinaryData.FromString(this.ApplyResponseChanges(AgentVersionTestJsonObject)))!, new MockPipelineResponse(200)));
        }

        private static string TryApplyAgentDefinition(string json, AgentDefinition? definition)
        {
            if (definition is not null)
            {
                json = json.Replace(AgentDefinitionPlaceholder, ModelReaderWriter.Write(definition).ToString());
            }
            return json;
        }

        private static string TryApplyAgentName(string json, string? agentName)
        {
            if (!string.IsNullOrEmpty(agentName))
            {
                return json.Replace("\"agent_abc123\"", $"\"{agentName}\"");
            }
            return json;
        }

        private static string TryApplyInstructions(string json, string? instructions)
        {
            if (!string.IsNullOrEmpty(instructions))
            {
                return json.Replace("You are a storytelling agent. You craft engaging one-line stories based on user prompts and context.", instructions);
            }
            return json;
        }

        private static string TryApplyDescription(string json, string? description)
        {
            if (!string.IsNullOrEmpty(description))
            {
                return json.Replace("\"description\": \"\"", $"\"description\": \"{description}\"");
            }
            return json;
        }

        private string ApplyResponseChanges(string json)
        {
            var modifiedJson = TryApplyAgentName(json, this._agentName);
            modifiedJson = TryApplyAgentDefinition(modifiedJson, this._agentDefinition);
            modifiedJson = TryApplyInstructions(modifiedJson, this._instructions);
            modifiedJson = TryApplyDescription(modifiedJson, this._description);

            return modifiedJson;
        }

        public override ClientResult<AgentRecord> CreateAgent(string name, AgentDefinition definition, AgentCreationOptions? options = null, CancellationToken cancellationToken = default)
        {
            string agentJson = AgentTestJsonObject.Replace("\"agent_abc123\"", $"\"{name}\"");
            var agentRecord = ModelReaderWriter.Read<AgentRecord>(BinaryData.FromString(agentJson))!;

            // Update the agent version's definition to match the provided definition
            if (agentRecord.Versions.Latest is AgentVersion agentVersion &&
                definition is PromptAgentDefinition promptDef &&
                agentVersion.Definition is PromptAgentDefinition versionPromptDef)
            {
                // Copy tools from the provided definition to the version's definition
                foreach (var tool in promptDef.Tools)
                {
                    versionPromptDef.Tools.Add(tool);
                }
            }

            return ClientResult.FromValue(agentRecord, new MockPipelineResponse(200));
        }

        public override Task<ClientResult<AgentRecord>> CreateAgentAsync(string name, AgentDefinition definition, AgentCreationOptions? options = null, CancellationToken cancellationToken = default)
        {
            string agentJson = AgentTestJsonObject.Replace("\"agent_abc123\"", $"\"{name}\"");
            var agentRecord = ModelReaderWriter.Read<AgentRecord>(BinaryData.FromString(agentJson))!;

            // Update the agent version's definition to match the provided definition
            if (agentRecord.Versions.Latest is AgentVersion agentVersion &&
                definition is PromptAgentDefinition promptDef &&
                agentVersion.Definition is PromptAgentDefinition versionPromptDef)
            {
                // Copy tools from the provided definition to the version's definition
                foreach (var tool in promptDef.Tools)
                {
                    versionPromptDef.Tools.Add(tool);
                }
            }

            return Task.FromResult(ClientResult.FromValue(agentRecord, new MockPipelineResponse(200)));
        }
    }

    private static PromptAgentDefinition GeneratePromptDefinitionResponse(PromptAgentDefinition inputDefinition, List<AITool> tools)
    {
        var definitionResponse = new PromptAgentDefinition(inputDefinition.Model) { Instructions = inputDefinition.Instructions };
        foreach (var tool in tools)
        {
            definitionResponse.Tools.Add(tool.GetService<ResponseTool>() ?? tool.AsOpenAIResponseTool());
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
