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
using Azure.AI.Extensions.OpenAI;
using Azure.AI.Projects;
using Azure.AI.Projects.Agents;
using Microsoft.Extensions.AI;
using Moq;
using OpenAI.Responses;

namespace Microsoft.Agents.AI.Foundry.UnitTests;

#pragma warning disable CS0618
/// <summary>
/// Unit tests for the <see cref="AzureAIProjectChatClientExtensions"/> class.
/// </summary>
public sealed class AzureAIProjectChatClientExtensionsTests
{
    #region AsAIAgent(AIProjectClient, model, instructions) Tests

    /// <summary>
    /// Verify that the non-versioned AsAIAgent overload throws ArgumentNullException when AIProjectClient is null.
    /// </summary>
    [Fact]
    public void AsAIAgent_WithModelAndInstructions_WithNullClient_ThrowsArgumentNullException()
    {
        // Arrange
        AIProjectClient? client = null;

        // Act & Assert
        ArgumentNullException exception = Assert.Throws<ArgumentNullException>(() =>
            client!.AsAIAgent("gpt-4o-mini", "You are helpful."));

        Assert.Equal("aiProjectClient", exception.ParamName);
    }

    /// <summary>
    /// Verify that the non-versioned AsAIAgent overload creates a valid ChatClientAgent.
    /// </summary>
    [Fact]
    public void AsAIAgent_Rapi_WithModelAndInstructions_CreatesChatClientAgent()
    {
        // Arrange
        AIProjectClient client = this.CreateTestAgentClient();
        List<AITool> tools =
        [
            AIFunctionFactory.Create(() => "test", "test_function", "A test function")
        ];

        // Act
        ChatClientAgent agent = client.AsAIAgent(
            "gpt-4o-mini",
            "You are helpful.",
            name: "test-agent",
            description: "A test agent",
            tools: tools);

        // Assert
        Assert.NotNull(agent);
        Assert.Equal("test-agent", agent.Name);
        Assert.Equal("A test agent", agent.Description);
        Assert.NotNull(agent.GetService<IChatClient>());
        Assert.Null(agent.GetService<AIProjectClient>());
    }

    /// <summary>
    /// Verify that the non-versioned AsAIAgent overload applies the clientFactory.
    /// </summary>
    [Fact]
    public void AsAIAgent_WithModelAndInstructions_WithClientFactory_AppliesFactoryCorrectly()
    {
        // Arrange
        AIProjectClient client = this.CreateTestAgentClient();
        TestChatClient? testChatClient = null;

        // Act
        ChatClientAgent agent = client.AsAIAgent(
            "gpt-4o-mini",
            "You are helpful.",
            clientFactory: innerClient => testChatClient = new TestChatClient(innerClient));

        // Assert
        Assert.NotNull(agent);
        TestChatClient? retrievedTestClient = agent.GetService<TestChatClient>();
        Assert.NotNull(retrievedTestClient);
        Assert.Same(testChatClient, retrievedTestClient);
    }

    /// <summary>
    /// Verify that the options-based non-versioned AsAIAgent overload creates a valid ChatClientAgent.
    /// </summary>
    [Fact]
    public void AsAIAgent_Rapi_WithOptions_CreatesChatClientAgent()
    {
        // Arrange
        AIProjectClient client = this.CreateTestAgentClient();
        ChatClientAgentOptions options = new()
        {
            Name = "options-agent",
            Description = "Agent from options",
            ChatOptions = new ChatOptions
            {
                ModelId = "gpt-4o-mini",
                Instructions = "You are helpful.",
            },
        };

        // Act
        ChatClientAgent agent = client.AsAIAgent(options);

        // Assert
        Assert.NotNull(agent);
        Assert.Equal("options-agent", agent.Name);
        Assert.Equal("Agent from options", agent.Description);
        Assert.Null(agent.GetService<AIProjectClient>());
    }

    /// <summary>
    /// Verify that the non-versioned AsAIAgent overload adds the MEAI user-agent header to Responses API requests.
    /// </summary>
    [Fact]
    public async Task AsAIAgent_Rapi_WithModelAndInstructions_UserAgentHeaderAddedToResponsesRequestsAsync()
    {
        // Arrange
        bool userAgentFound = false;
        using HttpHandlerAssert httpHandler = new(request =>
        {
            if (request.Headers.TryGetValues("User-Agent", out IEnumerable<string>? values))
            {
                foreach (string value in values)
                {
                    if (value.Contains("MEAI"))
                    {
                        userAgentFound = true;
                    }
                }
            }

            if (request.Method == HttpMethod.Post && request.RequestUri!.PathAndQuery.Contains("/responses"))
            {
                return new HttpResponseMessage(HttpStatusCode.OK)
                {
                    Content = new StringContent(
                        TestDataUtil.GetOpenAIDefaultResponseJson(),
                        Encoding.UTF8,
                        "application/json")
                };
            }

            return new HttpResponseMessage(HttpStatusCode.OK)
            {
                Content = new StringContent("{}", Encoding.UTF8, "application/json")
            };
        });

#pragma warning disable CA5399
        using HttpClient httpClient = new(httpHandler);
#pragma warning restore CA5399

        AIProjectClient aiProjectClient = new(
            new Uri("https://test.openai.azure.com/"),
            new FakeAuthenticationTokenProvider(),
            new() { Transport = new HttpClientPipelineTransport(httpClient) });

        ChatClientAgent agent = aiProjectClient.AsAIAgent(
            "gpt-4o-mini",
            "You are helpful.");

        // Act
        AgentSession session = await agent.CreateSessionAsync();
        await agent.RunAsync("Hello", session);

        // Assert
        Assert.True(userAgentFound, "MEAI user-agent header was not found in any request");
    }

    #endregion

    #region AsAIAgent(AIProjectClient, ProjectsAgentRecord) Tests

    /// <summary>
    /// Verify that AsAIAgent throws ArgumentNullException when AIProjectClient is null.
    /// </summary>
    [Fact]
    public void AsAIAgent_WithAgentRecord_WithNullClient_ThrowsArgumentNullException()
    {
        // Arrange
        AIProjectClient? client = null;
        ProjectsAgentRecord agentRecord = this.CreateTestAgentRecord();

        // Act & Assert
        var exception = Assert.Throws<ArgumentNullException>(() =>
            client!.AsAIAgent(agentRecord));

        Assert.Equal("aiProjectClient", exception.ParamName);
    }

    /// <summary>
    /// Verify that AsAIAgent throws ArgumentNullException when agentRecord is null.
    /// </summary>
    [Fact]
    public void AsAIAgent_WithAgentRecord_WithNullAgentRecord_ThrowsArgumentNullException()
    {
        // Arrange
        var mockClient = new Mock<AIProjectClient>();

        // Act & Assert
        var exception = Assert.Throws<ArgumentNullException>(() =>
            mockClient.Object.AsAIAgent((ProjectsAgentRecord)null!));

        Assert.Equal("agentRecord", exception.ParamName);
    }

    /// <summary>
    /// Verify that AsAIAgent with ProjectsAgentRecord creates a valid agent.
    /// </summary>
    [Fact]
    public void AsAIAgent_WithAgentRecord_CreatesValidAgent()
    {
        // Arrange
        AIProjectClient client = this.CreateTestAgentClient();
        ProjectsAgentRecord agentRecord = this.CreateTestAgentRecord();

        // Act
        var agent = client.AsAIAgent(agentRecord);

        // Assert
        Assert.NotNull(agent);
        Assert.IsType<FoundryAgent>(agent);
        Assert.Equal("agent_abc123", agent.Name);
        Assert.Same(client, agent.GetService<AIProjectClient>());
    }

    /// <summary>
    /// Verify that AsAIAgent with ProjectsAgentRecord and clientFactory applies the factory.
    /// </summary>
    [Fact]
    public void AsAIAgent_WithAgentRecord_WithClientFactory_AppliesFactoryCorrectly()
    {
        // Arrange
        AIProjectClient client = this.CreateTestAgentClient();
        ProjectsAgentRecord agentRecord = this.CreateTestAgentRecord();
        TestChatClient? testChatClient = null;

        // Act
        var agent = client.AsAIAgent(
            agentRecord,
            clientFactory: (innerClient) => testChatClient = new TestChatClient(innerClient));

        // Assert
        Assert.NotNull(agent);
        var retrievedTestClient = agent.GetService<TestChatClient>();
        Assert.NotNull(retrievedTestClient);
        Assert.Same(testChatClient, retrievedTestClient);
    }

    #endregion

    #region AsAIAgent(AIProjectClient, ProjectsAgentVersion) Tests

    /// <summary>
    /// Verify that AsAIAgent throws ArgumentNullException when AIProjectClient is null.
    /// </summary>
    [Fact]
    public void AsAIAgent_WithAgentVersion_WithNullClient_ThrowsArgumentNullException()
    {
        // Arrange
        AIProjectClient? client = null;
        ProjectsAgentVersion agentVersion = this.CreateTestAgentVersion();

        // Act & Assert
        var exception = Assert.Throws<ArgumentNullException>(() =>
            client!.AsAIAgent(agentVersion));

        Assert.Equal("aiProjectClient", exception.ParamName);
    }

    /// <summary>
    /// Verify that AsAIAgent throws ArgumentNullException when agentVersion is null.
    /// </summary>
    [Fact]
    public void AsAIAgent_WithAgentVersion_WithNullAgentVersion_ThrowsArgumentNullException()
    {
        // Arrange
        var mockClient = new Mock<AIProjectClient>();

        // Act & Assert
        var exception = Assert.Throws<ArgumentNullException>(() =>
            mockClient.Object.AsAIAgent((ProjectsAgentVersion)null!));

        Assert.Equal("agentVersion", exception.ParamName);
    }

    /// <summary>
    /// Verify that AsAIAgent with ProjectsAgentVersion creates a valid agent.
    /// </summary>
    [Fact]
    public void AsAIAgent_WithAgentVersion_CreatesValidAgent()
    {
        // Arrange
        AIProjectClient client = this.CreateTestAgentClient();
        ProjectsAgentVersion agentVersion = this.CreateTestAgentVersion();

        // Act
        var agent = client.AsAIAgent(agentVersion);

        // Assert
        Assert.NotNull(agent);
        Assert.IsType<FoundryAgent>(agent);
        Assert.Equal("agent_abc123", agent.Name);
        Assert.Same(client, agent.GetService<AIProjectClient>());
    }

    /// <summary>
    /// Verify that AsAIAgent with ProjectsAgentVersion and clientFactory applies the factory.
    /// </summary>
    [Fact]
    public void AsAIAgent_WithAgentVersion_WithClientFactory_AppliesFactoryCorrectly()
    {
        // Arrange
        AIProjectClient client = this.CreateTestAgentClient();
        ProjectsAgentVersion agentVersion = this.CreateTestAgentVersion();
        TestChatClient? testChatClient = null;

        // Act
        var agent = client.AsAIAgent(
            agentVersion,
            clientFactory: (innerClient) => testChatClient = new TestChatClient(innerClient));

        // Assert
        Assert.NotNull(agent);
        var retrievedTestClient = agent.GetService<TestChatClient>();
        Assert.NotNull(retrievedTestClient);
        Assert.Same(testChatClient, retrievedTestClient);
    }

    /// <summary>
    /// Verify that AsAIAgent with requireInvocableTools=true enforces invocable tools.
    /// </summary>
    [Fact]
    public void AsAIAgent_WithAgentVersion_WithRequireInvocableToolsTrue_EnforcesInvocableTools()
    {
        // Arrange
        AIProjectClient client = this.CreateTestAgentClient();
        ProjectsAgentVersion agentVersion = this.CreateTestAgentVersion();
        var tools = new List<AITool>
        {
            AIFunctionFactory.Create(() => "test", "test_function", "A test function")
        };

        // Act
        var agent = client.AsAIAgent(agentVersion, tools: tools);

        // Assert
        Assert.NotNull(agent);
        Assert.IsType<FoundryAgent>(agent);
    }

    /// <summary>
    /// Verify that AsAIAgent with requireInvocableTools=false allows declarative functions.
    /// </summary>
    [Fact]
    public void AsAIAgent_WithAgentVersion_WithRequireInvocableToolsFalse_AllowsDeclarativeFunctions()
    {
        // Arrange
        AIProjectClient client = this.CreateTestAgentClient();
        ProjectsAgentVersion agentVersion = this.CreateTestAgentVersion();

        // Act - should not throw even without tools when requireInvocableTools is false
        var agent = client.AsAIAgent(agentVersion);

        // Assert
        Assert.NotNull(agent);
        Assert.IsType<FoundryAgent>(agent);
    }

    #endregion

    #region AsAIAgent(AIProjectClient, string) Tests

    /// <summary>
    /// Verify that AsAIAgent throws ArgumentNullException when AIProjectClient is null.
    /// </summary>
    [Fact]
    public void AsAIAgent_ByName_WithNullClient_ThrowsArgumentNullException()
    {
        // Arrange
        AIProjectClient? client = null;

        // Act & Assert
        var exception = Assert.Throws<ArgumentNullException>(() =>
            client!.AsAIAgent("test-agent"));

        Assert.Equal("aiProjectClient", exception.ParamName);
    }

    /// <summary>
    /// Verify that AsAIAgent throws ArgumentNullException when name is null.
    /// </summary>
    [Fact]
    public void AsAIAgent_ByName_WithNullName_ThrowsArgumentNullException()
    {
        // Arrange
        var mockClient = new Mock<AIProjectClient>();

        // Act & Assert
        var exception = Assert.Throws<ArgumentNullException>(() =>
            mockClient.Object.AsAIAgent((string)null!));

        Assert.Equal("name", exception.ParamName);
    }

    /// <summary>
    /// Verify that AsAIAgent throws ArgumentException when name is empty.
    /// </summary>
    [Fact]
    public void AsAIAgent_ByName_WithEmptyName_ThrowsArgumentException()
    {
        // Arrange
        var mockClient = new Mock<AIProjectClient>();

        // Act & Assert
        var exception = Assert.Throws<ArgumentException>(() =>
            mockClient.Object.AsAIAgent(string.Empty));

        Assert.Equal("name", exception.ParamName);
    }

    #endregion

    #region AsAIAgent(AIProjectClient, ProjectsAgentRecord) with tools Tests

    /// <summary>
    /// Verify that AsAIAgent with additional tools when the definition has no tools does not throw and results in an agent with no tools.
    /// </summary>
    [Fact]
    public void AsAIAgent_WithAgentRecordAndAdditionalTools_WhenDefinitionHasNoTools_ShouldNotThrow()
    {
        // Arrange
        AIProjectClient client = this.CreateTestAgentClient();
        ProjectsAgentRecord agentRecord = this.CreateTestAgentRecord();
        var tools = new List<AITool>
        {
            AIFunctionFactory.Create(() => "test", "test_function", "A test function")
        };

        // Act
        var agent = client.AsAIAgent(agentRecord, tools: tools);

        // Assert
        Assert.NotNull(agent);
        Assert.IsType<FoundryAgent>(agent);
        var chatClient = agent.GetService<IChatClient>();
        Assert.NotNull(chatClient);
        var agentVersion = chatClient.GetService<ProjectsAgentVersion>();
        Assert.NotNull(agentVersion);
        var definition = Assert.IsType<DeclarativeAgentDefinition>(agentVersion.Definition);
        Assert.Empty(definition.Tools);
    }

    /// <summary>
    /// Verify that AsAIAgent with null tools works correctly.
    /// </summary>
    [Fact]
    public void AsAIAgent_WithAgentRecordAndNullTools_WorksCorrectly()
    {
        // Arrange
        AIProjectClient client = this.CreateTestAgentClient();
        ProjectsAgentRecord agentRecord = this.CreateTestAgentRecord();

        // Act
        var agent = client.AsAIAgent(agentRecord, tools: null);

        // Assert
        Assert.NotNull(agent);
        Assert.Equal("agent_abc123", agent.Name);
    }

    #endregion

    #region Tool Validation Tests

    /// <summary>
    /// Verify that when providing AITools with AsAIAgent, any additional tool that doesn't match the tools in agent definition are ignored.
    /// </summary>
    [Fact]
    public void AsAIAgent_AdditionalAITools_WhenNotInTheDefinitionAreIgnored()
    {
        // Arrange
        AIProjectClient client = this.CreateTestAgentClient();
        var agentVersion = this.CreateTestAgentVersion();

        // Manually add tools to the definition to simulate inline tools
        if (agentVersion.Definition is DeclarativeAgentDefinition promptDef)
        {
            promptDef.Tools.Add(ResponseTool.CreateFunctionTool("inline_tool", BinaryData.FromString("{}"), strictModeEnabled: false));
        }

        var invocableInlineAITool = AIFunctionFactory.Create(() => "test", "inline_tool", "An invocable AIFunction for the inline function");
        var shouldBeIgnoredTool = AIFunctionFactory.Create(() => "test", "additional_tool", "An additional test function that should be ignored");

        // Act & Assert
        var agent = client.AsAIAgent(agentVersion, tools: [invocableInlineAITool, shouldBeIgnoredTool]);
        Assert.NotNull(agent);
        var version = agent.GetService<ProjectsAgentVersion>();
        Assert.NotNull(version);
        var definition = Assert.IsType<DeclarativeAgentDefinition>(version.Definition);
        Assert.NotEmpty(definition.Tools);
        Assert.NotNull(GetAgentChatOptions(agent));
        Assert.NotNull(GetAgentChatOptions(agent)!.Tools);
        Assert.Single(GetAgentChatOptions(agent)!.Tools!);
        Assert.Equal("inline_tool", (definition.Tools.First() as FunctionTool)?.FunctionName);
    }

    #endregion

    #region Inline Tools vs Parameter Tools Tests

    /// <summary>
    /// Verify that tools passed as parameters are accepted by AsAIAgent.
    /// </summary>
    [Fact]
    public void AsAIAgent_WithParameterTools_AcceptsTools()
    {
        // Arrange
        AIProjectClient client = this.CreateTestAgentClient();
        ProjectsAgentRecord agentRecord = this.CreateTestAgentRecord();
        var tools = new List<AITool>
        {
            AIFunctionFactory.Create(() => "tool1", "param_tool_1", "First parameter tool"),
            AIFunctionFactory.Create(() => "tool2", "param_tool_2", "Second parameter tool")
        };

        // Act
        var agent = client.AsAIAgent(agentRecord, tools: tools);

        // Assert
        Assert.NotNull(agent);
        Assert.IsType<FoundryAgent>(agent);
        var chatClient = agent.GetService<IChatClient>();
        Assert.NotNull(chatClient);
        var agentVersion = chatClient.GetService<ProjectsAgentVersion>();
        Assert.NotNull(agentVersion);
    }

    #endregion

    #region Declarative Function Handling Tests

    /// <summary>
    /// Verifies that CreateAIAgent uses tools from definition when they are ResponseTool instances, resulting in successful agent creation.
    /// </summary>
    [Fact]
    public async Task CreateAIAgentAsync_WithResponseToolsInDefinition_CreatesAgentSuccessfullyAsync()
    {
        // Arrange
        var definition = new DeclarativeAgentDefinition("test-model") { Instructions = "Test instructions" };

        var fabricToolOptions = new FabricDataAgentToolOptions();
        fabricToolOptions.ProjectConnections.Add(new ToolProjectConnection("connection-id"));

        var sharepointOptions = new SharePointGroundingToolOptions();
        sharepointOptions.ProjectConnections.Add(new ToolProjectConnection("connection-id"));

        var structuredOutputs = new StructuredOutputDefinition("name", "description", new Dictionary<string, BinaryData> { ["schema"] = BinaryData.FromString(AIJsonUtilities.CreateJsonSchema(new { id = "test" }.GetType()).ToString()) }, false);

        // Add tools to the definition
        definition.Tools.Add(ResponseTool.CreateFunctionTool("create_tool", BinaryData.FromString("{}"), strictModeEnabled: false));
        definition.Tools.Add((ResponseTool)ProjectsAgentTool.CreateBingCustomSearchTool(new BingCustomSearchToolOptions([new BingCustomSearchConfiguration("connection-id", "instance-name")])));
        definition.Tools.Add((ResponseTool)ProjectsAgentTool.CreateBrowserAutomationTool(new BrowserAutomationToolOptions(new BrowserAutomationToolConnectionParameters("id"))));
        definition.Tools.Add(ProjectsAgentTool.CreateA2ATool(new Uri("https://test-uri.microsoft.com")));
        definition.Tools.Add((ResponseTool)ProjectsAgentTool.CreateBingGroundingTool(new BingGroundingSearchToolOptions([new BingGroundingSearchConfiguration("connection-id")])));
        definition.Tools.Add((ResponseTool)ProjectsAgentTool.CreateMicrosoftFabricTool(fabricToolOptions));
        definition.Tools.Add((ResponseTool)ProjectsAgentTool.CreateOpenApiTool(new OpenApiFunctionDefinition("name", BinaryData.FromString(OpenAPISpec), new OpenAPIAnonymousAuthenticationDetails())));
        definition.Tools.Add((ResponseTool)ProjectsAgentTool.CreateSharepointTool(sharepointOptions));
        definition.Tools.Add((ResponseTool)ProjectsAgentTool.CreateStructuredOutputsTool(structuredOutputs));
        definition.Tools.Add((ResponseTool)ProjectsAgentTool.CreateAzureAISearchTool(new AzureAISearchToolOptions([new AzureAISearchToolIndex() { IndexName = "name" }])));

        // Generate agent definition response with the tools
        var definitionResponse = GeneratePromptDefinitionResponse(definition, definition.Tools.Select(t => t.AsAITool()).ToList());

        using var testClient = CreateTestAgentClientWithHandler(agentDefinitionResponse: definitionResponse);

        var options = new ProjectsAgentVersionCreationOptions(definition);

        // Act
        var agentVersion = (await testClient.Client.AgentAdministrationClient.CreateAgentVersionAsync("test-agent", options)).Value;
        var agent = testClient.Client.AsAIAgent(agentVersion);

        // Assert
        Assert.NotNull(agent);
        Assert.IsType<FoundryAgent>(agent);
        var agentVersion2 = agent.GetService<ProjectsAgentVersion>()!;
        Assert.NotNull(agentVersion);
        if (agentVersion2.Definition is DeclarativeAgentDefinition promptDef)
        {
            Assert.NotEmpty(promptDef.Tools);
            Assert.Equal(10, promptDef.Tools.Count);
        }
    }

    /// <summary>
    /// Verify that AsAIAgentAsync accepts FunctionTools from definition.
    /// </summary>
    [Fact]
    public async Task AsAIAgent_WithFunctionToolsInDefinition_AcceptsDeclarativeFunctionAsync()
    {
        // Arrange
        var functionTool = ResponseTool.CreateFunctionTool(
            functionName: "get_user_name",
            functionParameters: BinaryData.FromString("{}"),
            strictModeEnabled: false,
            functionDescription: "Gets the user's name, as used for friendly address."
        );

        var definition = new DeclarativeAgentDefinition("test-model") { Instructions = "Test" };
        definition.Tools.Add(functionTool);

        // Generate response with the declarative function
        var definitionResponse = new DeclarativeAgentDefinition("test-model") { Instructions = "Test" };
        definitionResponse.Tools.Add(functionTool);

        using var testClient = CreateTestAgentClientWithHandler(agentName: "test-agent", agentDefinitionResponse: definitionResponse);

        var options = new ProjectsAgentVersionCreationOptions(definition);

        // Act
        var agentVersion = (await testClient.Client.AgentAdministrationClient.CreateAgentVersionAsync("test-agent", options)).Value;
        var agent = testClient.Client.AsAIAgent(agentVersion);

        // Assert
        Assert.NotNull(agent);
        Assert.IsType<FoundryAgent>(agent);
    }

    /// <summary>
    /// Verify that AsAIAgentAsync accepts declarative functions from definition.
    /// </summary>
    [Fact]
    public async Task AsAIAgent_WithDeclarativeFunctionFromDefinition_AcceptsDeclarativeFunctionAsync()
    {
        // Arrange
        using var testClient = CreateTestAgentClientWithHandler();
        var definition = new DeclarativeAgentDefinition("test-model") { Instructions = "Test" };

        // Create a declarative function (not invocable) using AIFunctionFactory.CreateDeclaration
        using var doc = JsonDocument.Parse("{}");
        var declarativeFunction = AIFunctionFactory.CreateDeclaration("test_function", "A test function", doc.RootElement);

        // Add to definition
        definition.Tools.Add(declarativeFunction.AsOpenAIResponseTool() ?? throw new InvalidOperationException());

        var options = new ProjectsAgentVersionCreationOptions(definition);

        // Act
        var agentVersion = (await testClient.Client.AgentAdministrationClient.CreateAgentVersionAsync("test-agent", options)).Value;
        var agent = testClient.Client.AsAIAgent(agentVersion);

        // Assert
        Assert.NotNull(agent);
        Assert.IsType<FoundryAgent>(agent);
    }

    /// <summary>
    /// Verify that AsAIAgentAsync accepts declarative functions from definition.
    /// </summary>
    [Fact]
    public async Task AsAIAgent_WithDeclarativeFunctionInDefinition_AcceptsDeclarativeFunctionAsync()
    {
        // Arrange
        var definition = new DeclarativeAgentDefinition("test-model") { Instructions = "Test" };

        // Create a declarative function (not invocable) using AIFunctionFactory.CreateDeclaration
        using var doc = JsonDocument.Parse("{}");
        var declarativeFunction = AIFunctionFactory.CreateDeclaration("test_function", "A test function", doc.RootElement);

        // Add to definition
        definition.Tools.Add(declarativeFunction.AsOpenAIResponseTool() ?? throw new InvalidOperationException());

        // Generate response with the declarative function
        var definitionResponse = new DeclarativeAgentDefinition("test-model") { Instructions = "Test" };
        definitionResponse.Tools.Add(declarativeFunction.AsOpenAIResponseTool() ?? throw new InvalidOperationException());

        using var testClient = CreateTestAgentClientWithHandler(agentName: "test-agent", agentDefinitionResponse: definitionResponse);

        var options = new ProjectsAgentVersionCreationOptions(definition);

        // Act
        var agentVersion = (await testClient.Client.AgentAdministrationClient.CreateAgentVersionAsync("test-agent", options)).Value;
        var agent = testClient.Client.AsAIAgent(agentVersion);

        // Assert
        Assert.NotNull(agent);
        Assert.IsType<FoundryAgent>(agent);
    }

    #endregion

    #region AgentName Validation Tests

    /// <summary>
    /// Verify that AsAIAgent throws ArgumentException when agent name is invalid.
    /// </summary>
    [Theory]
    [MemberData(nameof(InvalidAgentNameTestData.GetInvalidAgentNames), MemberType = typeof(InvalidAgentNameTestData))]
    public void AsAIAgent_ByName_WithInvalidAgentName_ThrowsArgumentException(string invalidName)
    {
        // Arrange
        var mockClient = new Mock<AIProjectClient>();

        // Act & Assert
        var exception = Assert.Throws<ArgumentException>(() =>
            mockClient.Object.AsAIAgent(invalidName));

        Assert.Equal("name", exception.ParamName);
        Assert.Contains("Agent name must be 1-63 characters long", exception.Message);
    }

    /// <summary>
    /// Verify that AsAIAgent with AgentReference throws ArgumentException when agent name is invalid.
    /// </summary>
    [Theory]
    [MemberData(nameof(InvalidAgentNameTestData.GetInvalidAgentNames), MemberType = typeof(InvalidAgentNameTestData))]
    public void AsAIAgent_WithAgentReference_WithInvalidAgentName_ThrowsArgumentException(string invalidName)
    {
        // Arrange
        var mockClient = new Mock<AIProjectClient>();
        var agentReference = new AgentReference(invalidName, "1");

        // Act & Assert
        var exception = Assert.Throws<ArgumentException>(() =>
            mockClient.Object.AsAIAgent(agentReference));

        Assert.Equal("name", exception.ParamName);
        Assert.Contains("Agent name must be 1-63 characters long", exception.Message);
    }

    #endregion

    #region AzureAIChatClient Behavior Tests

    /// <summary>
    /// Verify that the underlying chat client created by extension methods can be wrapped with clientFactory.
    /// </summary>
    [Fact]
    public void AsAIAgent_WithClientFactory_WrapsUnderlyingChatClient()
    {
        // Arrange
        AIProjectClient client = this.CreateTestAgentClient();
        ProjectsAgentRecord agentRecord = this.CreateTestAgentRecord();
        int factoryCallCount = 0;

        // Act
        var agent = client.AsAIAgent(
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
    /// Verify that multiple clientFactory calls create independent wrapped clients.
    /// </summary>
    [Fact]
    public void AsAIAgent_MultipleCallsWithClientFactory_CreatesIndependentClients()
    {
        // Arrange
        AIProjectClient client = this.CreateTestAgentClient();
        ProjectsAgentRecord agentRecord = this.CreateTestAgentRecord();

        // Act
        var agent1 = client.AsAIAgent(
            agentRecord,
            clientFactory: (innerClient) => new TestChatClient(innerClient));

        var agent2 = client.AsAIAgent(
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

    #endregion

    #region User-Agent Header Tests

    /// <summary>
    /// Verifies that the MEAI user-agent header is added to Responses API POST requests
    /// via the protocol method's RequestOptions pipeline policy.
    /// </summary>
    [Fact]
    public async Task AsAIAgent_Rapi_UserAgentHeaderAddedToRequestsAsync()
    {
        bool userAgentFound = false;
        using var httpHandler = new HttpHandlerAssert(request =>
        {
            if (request.Method == HttpMethod.Post && request.RequestUri!.PathAndQuery.Contains("/responses"))
            {
                // Verify MEAI user-agent header is present on Responses API POST request
                if (request.Headers.TryGetValues("User-Agent", out var userAgentValues)
                    && userAgentValues.Any(v => v.Contains("MEAI")))
                {
                    userAgentFound = true;
                }

                return new HttpResponseMessage(HttpStatusCode.OK)
                {
                    Content = new StringContent(
                        TestDataUtil.GetOpenAIDefaultResponseJson(),
                        Encoding.UTF8,
                        "application/json")
                };
            }

            return new HttpResponseMessage(HttpStatusCode.OK) { Content = new StringContent("{}", Encoding.UTF8, "application/json") };
        });

#pragma warning disable CA5399
        using var httpClient = new HttpClient(httpHandler);
#pragma warning restore CA5399

        // Arrange
        var aiProjectClient = new AIProjectClient(new Uri("https://test.openai.azure.com/"), new FakeAuthenticationTokenProvider(), new() { Transport = new HttpClientPipelineTransport(httpClient) });

        var agentOptions = new ChatClientAgentOptions
        {
            Name = "test-agent",
            ChatOptions = new ChatOptions { ModelId = "gpt-4o-mini" }
        };

        // Act
        var agent = aiProjectClient.AsAIAgent(agentOptions);

        var response = await agent.RunAsync("Hello");

        // Assert
        Assert.NotNull(agent);
        Assert.NotNull(response);
        Assert.True(userAgentFound, "MEAI user-agent header was not found in any Responses API request");
    }

    /// <summary>
    /// Verifies that the MEAI user-agent header is added to Responses API POST requests
    /// when using a versioned agent created via CreateAgentVersionAsync.
    /// </summary>
    [Fact]
    public async Task AsAIAgent_Versioned_UserAgentHeaderAddedToRequestsAsync()
    {
        bool userAgentFound = false;
        using var httpHandler = new HttpHandlerAssert(request =>
        {
            Assert.Equal("POST", request.Method.Method);

            if (request.RequestUri!.PathAndQuery.Contains("/responses"))
            {
                // Verify MEAI user-agent header is present on Responses API POST request
                Assert.True(request.Headers.TryGetValues("User-Agent", out var userAgentValues));
                Assert.Contains(userAgentValues, v => v.Contains("MEAI"));
                userAgentFound = true;

                return new HttpResponseMessage(HttpStatusCode.OK)
                {
                    Content = new StringContent(
                        TestDataUtil.GetOpenAIDefaultResponseJson(),
                        Encoding.UTF8,
                        "application/json")
                };
            }

            // CreateAgentVersion POST — return agent version response
            return new HttpResponseMessage(HttpStatusCode.OK) { Content = new StringContent(TestDataUtil.GetAgentVersionResponseJson(), Encoding.UTF8, "application/json") };
        });

#pragma warning disable CA5399
        using var httpClient = new HttpClient(httpHandler);
#pragma warning restore CA5399

        // Arrange
        var aiProjectClient = new AIProjectClient(new Uri("https://test.openai.azure.com/"), new FakeAuthenticationTokenProvider(), new() { Transport = new HttpClientPipelineTransport(httpClient) });

        var agentVersion = (await aiProjectClient.AgentAdministrationClient.CreateAgentVersionAsync("test-agent", new ProjectsAgentVersionCreationOptions(new DeclarativeAgentDefinition("test-model") { Instructions = "Test instructions" }))).Value;

        // Act
        var agent = aiProjectClient.AsAIAgent(agentVersion);

        var response = await agent.RunAsync("Hello");

        // Assert
        Assert.NotNull(agent);
        Assert.NotNull(response);
        Assert.True(userAgentFound, "MEAI user-agent header was not found in any Responses API request");
    }

    #endregion

    #region GetAIAgent(AIProjectClient, AgentReference) Tests

    /// <summary>
    /// Verify that AsAIAgent throws ArgumentNullException when AIProjectClient is null.
    /// </summary>
    [Fact]
    public void AsAIAgent_WithAgentReference_WithNullClient_ThrowsArgumentNullException()
    {
        // Arrange
        AIProjectClient? client = null;
        var agentReference = new AgentReference("test-name", "1");

        // Act & Assert
        var exception = Assert.Throws<ArgumentNullException>(() =>
            client!.AsAIAgent(agentReference));

        Assert.Equal("aiProjectClient", exception.ParamName);
    }

    /// <summary>
    /// Verify that AsAIAgent throws ArgumentNullException when agentReference is null.
    /// </summary>
    [Fact]
    public void AsAIAgent_WithAgentReference_WithNullAgentReference_ThrowsArgumentNullException()
    {
        // Arrange
        var mockClient = new Mock<AIProjectClient>();

        // Act & Assert
        var exception = Assert.Throws<ArgumentNullException>(() =>
            mockClient.Object.AsAIAgent((AgentReference)null!));

        Assert.Equal("agentReference", exception.ParamName);
    }

    /// <summary>
    /// Verify that AsAIAgent with AgentReference creates a valid agent.
    /// </summary>
    [Fact]
    public void AsAIAgent_WithAgentReference_CreatesValidAgent()
    {
        // Arrange
        AIProjectClient client = this.CreateTestAgentClient();
        var agentReference = new AgentReference("test-name", "1");

        // Act
        var agent = client.AsAIAgent(agentReference);

        // Assert
        Assert.NotNull(agent);
        Assert.IsType<FoundryAgent>(agent);
        Assert.Equal("test-name", agent.Name);
        Assert.Equal("test-name:1", agent.Id);
        Assert.Same(client, agent.GetService<AIProjectClient>());
    }

    /// <summary>
    /// Verify that AsAIAgent with AgentReference and clientFactory applies the factory.
    /// </summary>
    [Fact]
    public void AsAIAgent_WithAgentReference_WithClientFactory_AppliesFactoryCorrectly()
    {
        // Arrange
        AIProjectClient client = this.CreateTestAgentClient();
        var agentReference = new AgentReference("test-name", "1");
        TestChatClient? testChatClient = null;

        // Act
        var agent = client.AsAIAgent(
            agentReference,
            clientFactory: (innerClient) => testChatClient = new TestChatClient(innerClient));

        // Assert
        Assert.NotNull(agent);
        var retrievedTestClient = agent.GetService<TestChatClient>();
        Assert.NotNull(retrievedTestClient);
        Assert.Same(testChatClient, retrievedTestClient);
    }

    /// <summary>
    /// Verify that AsAIAgent with AgentReference sets the agent ID correctly.
    /// </summary>
    [Fact]
    public void AsAIAgent_WithAgentReference_SetsAgentIdCorrectly()
    {
        // Arrange
        AIProjectClient client = this.CreateTestAgentClient();
        var agentReference = new AgentReference("test-name", "2");

        // Act
        var agent = client.AsAIAgent(agentReference);

        // Assert
        Assert.NotNull(agent);
        Assert.Equal("test-name:2", agent.Id);
    }

    /// <summary>
    /// Verify that AsAIAgent with AgentReference and tools includes the tools in ChatOptions.
    /// </summary>
    [Fact]
    public void AsAIAgent_WithAgentReference_WithTools_IncludesToolsInChatOptions()
    {
        // Arrange
        AIProjectClient client = this.CreateTestAgentClient();
        var agentReference = new AgentReference("test-name", "1");
        var tools = new List<AITool>
        {
            AIFunctionFactory.Create(() => "test", "test_function", "A test function")
        };

        // Act
        var agent = client.AsAIAgent(agentReference, tools: tools);

        // Assert
        Assert.NotNull(agent);
        var chatOptions = GetAgentChatOptions(agent);
        Assert.NotNull(chatOptions);
        Assert.NotNull(chatOptions.Tools);
        Assert.Single(chatOptions.Tools);
    }

    #endregion

    #region GetService<ProjectsAgentRecord> Tests

    /// <summary>
    /// Verify that GetService returns ProjectsAgentRecord for agents created from ProjectsAgentRecord.
    /// </summary>
    [Fact]
    public void GetService_WithAgentRecord_ReturnsAgentRecord()
    {
        // Arrange
        AIProjectClient client = this.CreateTestAgentClient();
        ProjectsAgentRecord agentRecord = this.CreateTestAgentRecord();

        // Act
        var agent = client.AsAIAgent(agentRecord);
        var retrievedRecord = agent.GetService<ProjectsAgentRecord>();

        // Assert
        Assert.NotNull(retrievedRecord);
        Assert.Equal(agentRecord.Id, retrievedRecord.Id);
    }

    /// <summary>
    /// Verify that GetService returns null for ProjectsAgentRecord when agent is created from AgentReference.
    /// </summary>
    [Fact]
    public void GetService_WithAgentReference_ReturnsNullForAgentRecord()
    {
        // Arrange
        AIProjectClient client = this.CreateTestAgentClient();
        var agentReference = new AgentReference("test-name", "1");

        // Act
        var agent = client.AsAIAgent(agentReference);
        var retrievedRecord = agent.GetService<ProjectsAgentRecord>();

        // Assert
        Assert.Null(retrievedRecord);
    }

    #endregion

    #region GetService<ProjectsAgentVersion> Tests

    /// <summary>
    /// Verify that GetService returns ProjectsAgentVersion for agents created from ProjectsAgentVersion.
    /// </summary>
    [Fact]
    public void GetService_WithAgentVersion_ReturnsAgentVersion()
    {
        // Arrange
        AIProjectClient client = this.CreateTestAgentClient();
        ProjectsAgentVersion agentVersion = this.CreateTestAgentVersion();

        // Act
        var agent = client.AsAIAgent(agentVersion);
        var retrievedVersion = agent.GetService<ProjectsAgentVersion>();

        // Assert
        Assert.NotNull(retrievedVersion);
        Assert.Equal(agentVersion.Id, retrievedVersion.Id);
    }

    /// <summary>
    /// Verify that GetService returns null for ProjectsAgentVersion when agent is created from AgentReference.
    /// </summary>
    [Fact]
    public void GetService_WithAgentReference_ReturnsNullForAgentVersion()
    {
        // Arrange
        AIProjectClient client = this.CreateTestAgentClient();
        var agentReference = new AgentReference("test-name", "1");

        // Act
        var agent = client.AsAIAgent(agentReference);
        var retrievedVersion = agent.GetService<ProjectsAgentVersion>();

        // Assert
        Assert.Null(retrievedVersion);
    }

    #endregion

    #region ChatClientMetadata Tests

    /// <summary>
    /// Verify that ChatClientMetadata is properly populated for agents created from ProjectsAgentRecord.
    /// </summary>
    [Fact]
    public void ChatClientMetadata_WithAgentRecord_IsPopulatedCorrectly()
    {
        // Arrange
        AIProjectClient client = this.CreateTestAgentClient();
        ProjectsAgentRecord agentRecord = this.CreateTestAgentRecord();

        // Act
        var agent = client.AsAIAgent(agentRecord);
        var metadata = agent.GetService<ChatClientMetadata>();

        // Assert
        Assert.NotNull(metadata);
        Assert.NotNull(metadata.DefaultModelId);
    }

    /// <summary>
    /// Verify that ChatClientMetadata.DefaultModelId is set from DeclarativeAgentDefinition model property.
    /// </summary>
    [Fact]
    public void ChatClientMetadata_WithDeclarativeAgentDefinition_SetsDefaultModelIdFromModel()
    {
        // Arrange
        AIProjectClient client = this.CreateTestAgentClient();
        var definition = new DeclarativeAgentDefinition("gpt-4-turbo")
        {
            Instructions = "Test instructions"
        };
        ProjectsAgentRecord agentRecord = this.CreateTestAgentRecord(definition);

        // Act
        var agent = client.AsAIAgent(agentRecord);
        var metadata = agent.GetService<ChatClientMetadata>();

        // Assert
        Assert.NotNull(metadata);
        // The metadata should contain the model information from the agent definition
        Assert.NotNull(metadata.DefaultModelId);
        Assert.Equal("gpt-4-turbo", metadata.DefaultModelId);
    }

    /// <summary>
    /// Verify that ChatClientMetadata is properly populated for agents created from ProjectsAgentVersion.
    /// </summary>
    [Fact]
    public void ChatClientMetadata_WithAgentVersion_IsPopulatedCorrectly()
    {
        // Arrange
        AIProjectClient client = this.CreateTestAgentClient();
        ProjectsAgentVersion agentVersion = this.CreateTestAgentVersion();

        // Act
        var agent = client.AsAIAgent(agentVersion);
        var metadata = agent.GetService<ChatClientMetadata>();

        // Assert
        Assert.NotNull(metadata);
        Assert.NotNull(metadata.DefaultModelId);
        Assert.Equal((agentVersion.Definition as DeclarativeAgentDefinition)!.Model, metadata.DefaultModelId);
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
        var agent = client.AsAIAgent(agentReference);
        var retrievedReference = agent.GetService<AgentReference>();

        // Assert
        Assert.NotNull(retrievedReference);
        Assert.Equal("test-agent", retrievedReference.Name);
        Assert.Equal("1.0", retrievedReference.Version);
    }

    /// <summary>
    /// Verify that GetService returns null for AgentReference when agent is created from ProjectsAgentRecord.
    /// </summary>
    [Fact]
    public void GetService_WithAgentRecord_ReturnsAlsoAgentReference()
    {
        // Arrange
        AIProjectClient client = this.CreateTestAgentClient();
        ProjectsAgentRecord agentRecord = this.CreateTestAgentRecord();

        // Act
        var agent = client.AsAIAgent(agentRecord);
        var retrievedReference = agent.GetService<AgentReference>();

        // Assert
        Assert.NotNull(retrievedReference);
        Assert.Equal(agentRecord.Name, retrievedReference.Name);
    }

    /// <summary>
    /// Verify that GetService returns null for AgentReference when agent is created from ProjectsAgentVersion.
    /// </summary>
    [Fact]
    public void GetService_WithAgentVersion_ReturnsAlsoAgentReference()
    {
        // Arrange
        AIProjectClient client = this.CreateTestAgentClient();
        ProjectsAgentVersion agentVersion = this.CreateTestAgentVersion();

        // Act
        var agent = client.AsAIAgent(agentVersion);
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
        var agent = client.AsAIAgent(agentReference);
        var retrievedReference = agent.GetService<AgentReference>();

        // Assert
        Assert.NotNull(retrievedReference);
        Assert.Equal("versioned-agent", retrievedReference.Name);
        Assert.Equal("3.5", retrievedReference.Version);
    }

    #endregion

    #region Empty Version and ID Handling Tests

    /// <summary>
    /// Verify that AsAIAgent with ProjectsAgentRecord handles empty version by using "latest" as fallback.
    /// </summary>
    [Fact]
    public void AsAIAgent_WithAgentRecordEmptyVersion_CreatesAgentWithGeneratedId()
    {
        // Arrange
        AIProjectClient client = this.CreateTestAgentClientWithEmptyVersion();
        ProjectsAgentRecord agentRecord = this.CreateTestAgentRecordWithEmptyVersion();

        // Act
        var agent = client.AsAIAgent(agentRecord);

        // Assert
        Assert.NotNull(agent);
        // Verify the agent ID is generated from agent record name ("agent_abc123") and "latest"
        Assert.Equal("agent_abc123:latest", agent.Id);
    }

    /// <summary>
    /// Verify that AsAIAgent with ProjectsAgentVersion handles empty version by using "latest" as fallback.
    /// </summary>
    [Fact]
    public void AsAIAgent_WithAgentVersionEmptyVersion_CreatesAgentWithGeneratedId()
    {
        // Arrange
        AIProjectClient client = this.CreateTestAgentClientWithEmptyVersion();
        ProjectsAgentVersion agentVersion = this.CreateTestAgentVersionWithEmptyVersion();

        // Act
        var agent = client.AsAIAgent(agentVersion);

        // Assert
        Assert.NotNull(agent);
        // Verify the agent ID is generated from agent version name ("agent_abc123") and "latest"
        Assert.Equal("agent_abc123:latest", agent.Id);
    }

    /// <summary>
    /// Verify that AsAIAgent with ProjectsAgentRecord handles whitespace-only version by using "latest" as fallback.
    /// </summary>
    [Fact]
    public void AsAIAgent_WithAgentRecordWhitespaceVersion_CreatesAgentWithGeneratedId()
    {
        // Arrange
        AIProjectClient client = this.CreateTestAgentClientWithWhitespaceVersion();
        ProjectsAgentRecord agentRecord = this.CreateTestAgentRecordWithWhitespaceVersion();

        // Act
        var agent = client.AsAIAgent(agentRecord);

        // Assert
        Assert.NotNull(agent);
        // Verify the agent ID is generated from agent record name ("agent_abc123") and "latest"
        Assert.Equal("agent_abc123:latest", agent.Id);
    }

    /// <summary>
    /// Verify that AsAIAgent with ProjectsAgentVersion handles whitespace-only version by using "latest" as fallback.
    /// </summary>
    [Fact]
    public void AsAIAgent_WithAgentVersionWhitespaceVersion_CreatesAgentWithGeneratedId()
    {
        // Arrange
        AIProjectClient client = this.CreateTestAgentClientWithWhitespaceVersion();
        ProjectsAgentVersion agentVersion = this.CreateTestAgentVersionWithWhitespaceVersion();

        // Act
        var agent = client.AsAIAgent(agentVersion);

        // Assert
        Assert.NotNull(agent);
        // Verify the agent ID is generated from agent version name ("agent_abc123") and "latest"
        Assert.Equal("agent_abc123:latest", agent.Id);
    }

    #endregion

    #region ApplyToolsToAgentDefinition Tests

    /// <summary>
    /// Verify that when AsAIAgent is called without requireInvocableTools, hosted tools are correctly added.
    /// </summary>
    [Fact]
    public void AsAIAgent_WithServerHostedTools_AddsToolsToAgentOptions()
    {
        // Arrange
        DeclarativeAgentDefinition definition = new("test-model") { Instructions = "Test" };
        definition.Tools.Add(new HostedWebSearchTool().GetService<ResponseTool>() ?? new HostedWebSearchTool().AsOpenAIResponseTool());

        AIProjectClient client = this.CreateTestAgentClient();
        ProjectsAgentVersion agentVersion = ModelReaderWriter.Read<ProjectsAgentVersion>(BinaryData.FromString(TestDataUtil.GetAgentVersionResponseJson(agentDefinition: definition)))!;

        // Act - no tools provided, but requireInvocableTools is false when no tools param is passed
        FoundryAgent agent = client.AsAIAgent(agentVersion);

        // Assert
        Assert.NotNull(agent);
        Assert.IsType<FoundryAgent>(agent);
    }

    #endregion

    #region Helper Methods

    /// <summary>
    /// Creates a test AIProjectClient with fake behavior.
    /// </summary>
    private FakeAgentClient CreateTestAgentClient(string? agentName = null, string? instructions = null, string? description = null, ProjectsAgentDefinition? agentDefinitionResponse = null)
    {
        return new FakeAgentClient(agentName, instructions, description, agentDefinitionResponse);
    }

    /// <summary>
    /// Creates a test AIProjectClient backed by an HTTP handler that returns canned responses.
    /// Used for tests that exercise the protocol-method code path (CreateAgentVersion).
    /// The returned client must be disposed to clean up the underlying HttpClient/handler.
    /// </summary>
    private static DisposableTestClient CreateTestAgentClientWithHandler(string? agentName = null, string? instructions = null, string? description = null, ProjectsAgentDefinition? agentDefinitionResponse = null)
    {
        var responseJson = TestDataUtil.GetAgentVersionResponseJson(agentName, agentDefinitionResponse, instructions, description);

        var httpHandler = new HttpHandlerAssert(_ =>
            new HttpResponseMessage(HttpStatusCode.OK) { Content = new StringContent(responseJson, Encoding.UTF8, "application/json") });

#pragma warning disable CA5399
        var httpClient = new HttpClient(httpHandler);
#pragma warning restore CA5399

        var client = new AIProjectClient(
            new Uri("https://test.openai.azure.com/"),
            new FakeAuthenticationTokenProvider(),
            new() { Transport = new HttpClientPipelineTransport(httpClient) });

        return new DisposableTestClient(client, httpClient, httpHandler);
    }

    /// <summary>
    /// Wraps an AIProjectClient and its disposable dependencies for deterministic cleanup.
    /// </summary>
    private sealed class DisposableTestClient : IDisposable
    {
        private readonly HttpClient _httpClient;
        private readonly HttpHandlerAssert _httpHandler;

        public DisposableTestClient(AIProjectClient client, HttpClient httpClient, HttpHandlerAssert httpHandler)
        {
            this.Client = client;
            this._httpClient = httpClient;
            this._httpHandler = httpHandler;
        }

        public AIProjectClient Client { get; }

        public void Dispose()
        {
            this._httpClient.Dispose();
            this._httpHandler.Dispose();
        }
    }

    /// <summary>
    /// Creates a test ProjectsAgentRecord for testing.
    /// </summary>
    private ProjectsAgentRecord CreateTestAgentRecord(ProjectsAgentDefinition? agentDefinition = null)
    {
        return ModelReaderWriter.Read<ProjectsAgentRecord>(BinaryData.FromString(TestDataUtil.GetAgentResponseJson(agentDefinition: agentDefinition)))!;
    }

    /// <summary>
    /// Creates a test AIProjectClient with empty version fields for testing hosted MCP agents.
    /// </summary>
    private FakeAgentClient CreateTestAgentClientWithEmptyVersion(string? agentName = null, string? instructions = null, string? description = null, ProjectsAgentDefinition? agentDefinitionResponse = null)
    {
        return new FakeAgentClient(agentName, instructions, description, agentDefinitionResponse, useEmptyVersion: true);
    }

    /// <summary>
    /// Creates a test ProjectsAgentRecord with empty version for testing hosted MCP agents.
    /// </summary>
    private ProjectsAgentRecord CreateTestAgentRecordWithEmptyVersion(ProjectsAgentDefinition? agentDefinition = null)
    {
        return ModelReaderWriter.Read<ProjectsAgentRecord>(BinaryData.FromString(TestDataUtil.GetAgentResponseJsonWithEmptyVersion(agentDefinition: agentDefinition)))!;
    }

    /// <summary>
    /// Creates a test ProjectsAgentVersion with empty version for testing hosted MCP agents.
    /// </summary>
    private ProjectsAgentVersion CreateTestAgentVersionWithEmptyVersion()
    {
        return ModelReaderWriter.Read<ProjectsAgentVersion>(BinaryData.FromString(TestDataUtil.GetAgentVersionResponseJsonWithEmptyVersion()))!;
    }

    /// <summary>
    /// Creates a test AIProjectClient with whitespace-only version fields for testing hosted MCP agents.
    /// </summary>
    private FakeAgentClient CreateTestAgentClientWithWhitespaceVersion(string? agentName = null, string? instructions = null, string? description = null, ProjectsAgentDefinition? agentDefinitionResponse = null)
    {
        return new FakeAgentClient(agentName, instructions, description, agentDefinitionResponse, versionMode: VersionMode.Whitespace);
    }

    /// <summary>
    /// Creates a test ProjectsAgentRecord with whitespace-only version for testing hosted MCP agents.
    /// </summary>
    private ProjectsAgentRecord CreateTestAgentRecordWithWhitespaceVersion(ProjectsAgentDefinition? agentDefinition = null)
    {
        return ModelReaderWriter.Read<ProjectsAgentRecord>(BinaryData.FromString(TestDataUtil.GetAgentResponseJsonWithWhitespaceVersion(agentDefinition: agentDefinition)))!;
    }

    /// <summary>
    /// Creates a test ProjectsAgentVersion with whitespace-only version for testing hosted MCP agents.
    /// </summary>
    private ProjectsAgentVersion CreateTestAgentVersionWithWhitespaceVersion()
    {
        return ModelReaderWriter.Read<ProjectsAgentVersion>(BinaryData.FromString(TestDataUtil.GetAgentVersionResponseJsonWithWhitespaceVersion()))!;
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
    /// Creates a test ProjectsAgentVersion for testing.
    /// </summary>
    private ProjectsAgentVersion CreateTestAgentVersion()
    {
        return ModelReaderWriter.Read<ProjectsAgentVersion>(BinaryData.FromString(TestDataUtil.GetAgentVersionResponseJson()))!;
    }

    /// <summary>
    /// Specifies the version mode for test data generation.
    /// </summary>
    private enum VersionMode
    {
        Normal,
        Empty,
        Whitespace
    }

    /// <summary>
    /// Fake AIProjectClient for testing.
    /// </summary>
    private sealed class FakeAgentClient : AIProjectClient
    {
        public FakeAgentClient(string? agentName = null, string? instructions = null, string? description = null, ProjectsAgentDefinition? agentDefinitionResponse = null, bool useEmptyVersion = false, VersionMode versionMode = VersionMode.Normal)
        {
            // Handle backward compatibility with bool parameter
            var effectiveVersionMode = useEmptyVersion ? VersionMode.Empty : versionMode;
            this.AgentAdministrationClient = new FakeAgentsClient(agentName, instructions, description, agentDefinitionResponse, effectiveVersionMode);
        }

        public override ClientConnection GetConnection(string connectionId)
        {
            return new ClientConnection("fake-connection-id", "http://localhost", ClientPipeline.Create(), CredentialKind.None);
        }

        public override AgentAdministrationClient AgentAdministrationClient { get; }

        private sealed class FakeAgentsClient : AgentAdministrationClient
        {
            private readonly string? _agentName;
            private readonly string? _instructions;
            private readonly string? _description;
            private readonly ProjectsAgentDefinition? _agentDefinition;
            private readonly VersionMode _versionMode;

            public FakeAgentsClient(string? agentName = null, string? instructions = null, string? description = null, ProjectsAgentDefinition? agentDefinitionResponse = null, VersionMode versionMode = VersionMode.Normal)
            {
                this._agentName = agentName;
                this._instructions = instructions;
                this._description = description;
                this._agentDefinition = agentDefinitionResponse;
                this._versionMode = versionMode;
            }

            private string GetAgentResponseJson()
            {
                return this._versionMode switch
                {
                    VersionMode.Empty => TestDataUtil.GetAgentResponseJsonWithEmptyVersion(this._agentName, this._agentDefinition, this._instructions, this._description),
                    VersionMode.Whitespace => TestDataUtil.GetAgentResponseJsonWithWhitespaceVersion(this._agentName, this._agentDefinition, this._instructions, this._description),
                    _ => TestDataUtil.GetAgentResponseJson(this._agentName, this._agentDefinition, this._instructions, this._description)
                };
            }

            private string GetAgentVersionResponseJson()
            {
                return this._versionMode switch
                {
                    VersionMode.Empty => TestDataUtil.GetAgentVersionResponseJsonWithEmptyVersion(this._agentName, this._agentDefinition, this._instructions, this._description),
                    VersionMode.Whitespace => TestDataUtil.GetAgentVersionResponseJsonWithWhitespaceVersion(this._agentName, this._agentDefinition, this._instructions, this._description),
                    _ => TestDataUtil.GetAgentVersionResponseJson(this._agentName, this._agentDefinition, this._instructions, this._description)
                };
            }

            public override ClientResult GetAgent(string agentName, RequestOptions options)
            {
                var responseJson = this.GetAgentResponseJson();
                return ClientResult.FromValue(ModelReaderWriter.Read<ProjectsAgentRecord>(BinaryData.FromString(responseJson))!, new MockPipelineResponse(200, BinaryData.FromString(responseJson)));
            }

            public override ClientResult<ProjectsAgentRecord> GetAgent(string agentName, CancellationToken cancellationToken = default)
            {
                var responseJson = this.GetAgentResponseJson();
                return ClientResult.FromValue(ModelReaderWriter.Read<ProjectsAgentRecord>(BinaryData.FromString(responseJson))!, new MockPipelineResponse(200));
            }

            public override Task<ClientResult> GetAgentAsync(string agentName, RequestOptions options)
            {
                var responseJson = this.GetAgentResponseJson();
                return Task.FromResult<ClientResult>(ClientResult.FromValue(ModelReaderWriter.Read<ProjectsAgentRecord>(BinaryData.FromString(responseJson))!, new MockPipelineResponse(200, BinaryData.FromString(responseJson))));
            }

            public override Task<ClientResult<ProjectsAgentRecord>> GetAgentAsync(string agentName, CancellationToken cancellationToken = default)
            {
                var responseJson = this.GetAgentResponseJson();
                return Task.FromResult(ClientResult.FromValue(ModelReaderWriter.Read<ProjectsAgentRecord>(BinaryData.FromString(responseJson))!, new MockPipelineResponse(200)));
            }

            public override ClientResult<ProjectsAgentVersion> CreateAgentVersion(string agentName, ProjectsAgentVersionCreationOptions? options = null, string? foundryFeatures = null, CancellationToken cancellationToken = default)
            {
                var responseJson = this.GetAgentVersionResponseJson();
                return ClientResult.FromValue(ModelReaderWriter.Read<ProjectsAgentVersion>(BinaryData.FromString(responseJson))!, new MockPipelineResponse(200));
            }

            public override Task<ClientResult<ProjectsAgentVersion>> CreateAgentVersionAsync(string agentName, ProjectsAgentVersionCreationOptions? options = null, string? foundryFeatures = null, CancellationToken cancellationToken = default)
            {
                var responseJson = this.GetAgentVersionResponseJson();
                return Task.FromResult(ClientResult.FromValue(ModelReaderWriter.Read<ProjectsAgentVersion>(BinaryData.FromString(responseJson))!, new MockPipelineResponse(200)));
            }
        }
    }

    private static DeclarativeAgentDefinition GeneratePromptDefinitionResponse(DeclarativeAgentDefinition inputDefinition, List<AITool>? tools)
    {
        var definitionResponse = new DeclarativeAgentDefinition(inputDefinition.Model) { Instructions = inputDefinition.Instructions };
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
        private readonly MockPipelineResponseHeaders _headers;

        public MockPipelineResponse(int status, BinaryData? content = null)
        {
            this.Status = status;
            this.Content = content ?? BinaryData.Empty;
            this._headers = new MockPipelineResponseHeaders();
        }

        public override int Status { get; }

        public override string ReasonPhrase => "OK";

        public override Stream? ContentStream
        {
            get => null;
            set { }
        }

        public override BinaryData Content { get; }

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
    private static ChatOptions? GetAgentChatOptions(AIAgent agent)
    {
        ChatClientAgent? chatClientAgent = agent as ChatClientAgent ?? agent.GetService<ChatClientAgent>();
        if (chatClientAgent is null)
        {
            return null;
        }

        var chatOptionsProperty = typeof(ChatClientAgent).GetProperty(
            "ChatOptions",
            System.Reflection.BindingFlags.Public |
            System.Reflection.BindingFlags.NonPublic |
            System.Reflection.BindingFlags.Instance);

        return chatOptionsProperty?.GetValue(chatClientAgent) as ChatOptions;
    }

    /// <summary>
    /// Test schema for JSON response format tests.
    /// </summary>
#pragma warning disable CA1812 // Avoid uninstantiated internal classes - used via reflection by AIJsonUtilities
    private sealed class TestSchema
    {
        public string? Name { get; set; }
        public int Value { get; set; }
    }
#pragma warning restore CA1812
#pragma warning restore CS0618

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
