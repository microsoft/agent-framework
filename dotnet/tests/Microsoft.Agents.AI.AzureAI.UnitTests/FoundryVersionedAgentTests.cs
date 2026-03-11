// Copyright (c) Microsoft. All rights reserved.

using System;
using System.ClientModel.Primitives;
using System.Collections.Generic;
using System.Net;
using System.Net.Http;
using System.Text;
using System.Threading.Tasks;
using Azure.AI.Projects;
using Azure.AI.Projects.OpenAI;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.AzureAI.UnitTests;

/// <summary>
/// Unit tests for the <see cref="FoundryVersionedAgent"/> class.
/// </summary>
public sealed class FoundryVersionedAgentTests
{
    private static readonly Uri TestEndpoint = new("https://test.services.ai.azure.com/api/projects/test-project");

    #region CreateAIAgentAsync validation tests

    [Fact]
    public async Task CreateAIAgentAsync_WithNullEndpoint_ThrowsArgumentNullExceptionAsync()
    {
        // Act & Assert
        ArgumentNullException exception = await Assert.ThrowsAsync<ArgumentNullException>(() =>
            FoundryVersionedAgent.CreateAIAgentAsync(
                endpoint: null!,
                tokenProvider: new FakeAuthenticationTokenProvider(),
                name: "test-agent",
                model: "gpt-4o-mini",
                instructions: "Test instructions"));

        Assert.Equal("endpoint", exception.ParamName);
    }

    [Fact]
    public async Task CreateAIAgentAsync_WithNullTokenProvider_ThrowsArgumentNullExceptionAsync()
    {
        // Act & Assert
        ArgumentNullException exception = await Assert.ThrowsAsync<ArgumentNullException>(() =>
            FoundryVersionedAgent.CreateAIAgentAsync(
                endpoint: TestEndpoint,
                tokenProvider: null!,
                name: "test-agent",
                model: "gpt-4o-mini",
                instructions: "Test instructions"));

        Assert.Equal("tokenProvider", exception.ParamName);
    }

    [Fact]
    public async Task CreateAIAgentAsync_WithNullModel_ThrowsArgumentExceptionAsync()
    {
        // Act & Assert
        await Assert.ThrowsAnyAsync<ArgumentException>(() =>
            FoundryVersionedAgent.CreateAIAgentAsync(
                endpoint: TestEndpoint,
                tokenProvider: new FakeAuthenticationTokenProvider(),
                name: "test-agent",
                model: null!,
                instructions: "Test instructions"));
    }

    [Fact]
    public async Task CreateAIAgentAsync_WithEmptyModel_ThrowsArgumentExceptionAsync()
    {
        // Act & Assert
        await Assert.ThrowsAnyAsync<ArgumentException>(() =>
            FoundryVersionedAgent.CreateAIAgentAsync(
                endpoint: TestEndpoint,
                tokenProvider: new FakeAuthenticationTokenProvider(),
                name: "test-agent",
                model: string.Empty,
                instructions: "Test instructions"));
    }

    [Fact]
    public async Task CreateAIAgentAsync_WithNullInstructions_ThrowsArgumentExceptionAsync()
    {
        // Act & Assert
        await Assert.ThrowsAnyAsync<ArgumentException>(() =>
            FoundryVersionedAgent.CreateAIAgentAsync(
                endpoint: TestEndpoint,
                tokenProvider: new FakeAuthenticationTokenProvider(),
                name: "test-agent",
                model: "gpt-4o-mini",
                instructions: null!));
    }

    [Theory]
    [MemberData(nameof(InvalidAgentNameTestData.GetInvalidAgentNames), MemberType = typeof(InvalidAgentNameTestData))]
    public async Task CreateAIAgentAsync_WithInvalidAgentName_ThrowsArgumentExceptionAsync(string invalidName)
    {
        // Act & Assert
        ArgumentException exception = await Assert.ThrowsAsync<ArgumentException>(() =>
            FoundryVersionedAgent.CreateAIAgentAsync(
                endpoint: TestEndpoint,
                tokenProvider: new FakeAuthenticationTokenProvider(),
                name: invalidName,
                model: "gpt-4o-mini",
                instructions: "Test instructions"));

        Assert.Equal("name", exception.ParamName);
        Assert.Contains("Agent name must be 1-63 characters long", exception.Message);
    }

    [Fact]
    public async Task CreateAIAgentAsync_WithValidParams_CreatesAgentAsync()
    {
        // Arrange
        using HttpHandlerAssert httpHandler = CreateAgentVersionHttpHandler("test-agent");

#pragma warning disable CA5399
        using HttpClient httpClient = new(httpHandler);
#pragma warning restore CA5399

        AIProjectClientOptions clientOptions = new()
        {
            Transport = new HttpClientPipelineTransport(httpClient)
        };

        // Act
        FoundryVersionedAgent agent = await FoundryVersionedAgent.CreateAIAgentAsync(
            TestEndpoint,
            new FakeAuthenticationTokenProvider(),
            name: "test-agent",
            model: "gpt-4o-mini",
            instructions: "Test instructions",
            clientOptions: clientOptions);

        // Assert
        Assert.NotNull(agent);
        Assert.Equal("test-agent", agent.Name);
    }

    [Fact]
    public async Task CreateAIAgentAsync_WithTools_CreatesAgentWithToolsAsync()
    {
        // Arrange
        using HttpHandlerAssert httpHandler = CreateAgentVersionHttpHandler("test-agent");

#pragma warning disable CA5399
        using HttpClient httpClient = new(httpHandler);
#pragma warning restore CA5399

        AIProjectClientOptions clientOptions = new()
        {
            Transport = new HttpClientPipelineTransport(httpClient)
        };

        List<AITool> tools = new()
        {
            AIFunctionFactory.Create(() => "result", "test-tool", "A test tool")
        };

        // Act
        FoundryVersionedAgent agent = await FoundryVersionedAgent.CreateAIAgentAsync(
            TestEndpoint,
            new FakeAuthenticationTokenProvider(),
            name: "test-agent",
            model: "gpt-4o-mini",
            instructions: "Test instructions",
            tools: tools,
            clientOptions: clientOptions);

        // Assert
        Assert.NotNull(agent);
    }

    [Fact]
    public async Task CreateAIAgentAsync_WithDescription_SetsDescriptionAsync()
    {
        // Arrange
        using HttpHandlerAssert httpHandler = CreateAgentVersionHttpHandler("test-agent", description: "A test description");

#pragma warning disable CA5399
        using HttpClient httpClient = new(httpHandler);
#pragma warning restore CA5399

        AIProjectClientOptions clientOptions = new()
        {
            Transport = new HttpClientPipelineTransport(httpClient)
        };

        // Act
        FoundryVersionedAgent agent = await FoundryVersionedAgent.CreateAIAgentAsync(
            TestEndpoint,
            new FakeAuthenticationTokenProvider(),
            name: "test-agent",
            model: "gpt-4o-mini",
            instructions: "Test instructions",
            description: "A test description",
            clientOptions: clientOptions);

        // Assert
        Assert.NotNull(agent);
        Assert.Equal("A test description", agent.Description);
    }

    #endregion

    #region GetAIAgentAsync validation tests

    [Fact]
    public async Task GetAIAgentAsync_WithNullEndpoint_ThrowsArgumentNullExceptionAsync()
    {
        // Act & Assert
        ArgumentNullException exception = await Assert.ThrowsAsync<ArgumentNullException>(() =>
            FoundryVersionedAgent.GetAIAgentAsync(
                endpoint: null!,
                tokenProvider: new FakeAuthenticationTokenProvider(),
                name: "test-agent"));

        Assert.Equal("endpoint", exception.ParamName);
    }

    [Fact]
    public async Task GetAIAgentAsync_WithNullTokenProvider_ThrowsArgumentNullExceptionAsync()
    {
        // Act & Assert
        ArgumentNullException exception = await Assert.ThrowsAsync<ArgumentNullException>(() =>
            FoundryVersionedAgent.GetAIAgentAsync(
                endpoint: TestEndpoint,
                tokenProvider: null!,
                name: "test-agent"));

        Assert.Equal("tokenProvider", exception.ParamName);
    }

    [Fact]
    public async Task GetAIAgentAsync_WithNullName_ThrowsArgumentExceptionAsync()
    {
        // Act & Assert
        await Assert.ThrowsAnyAsync<ArgumentException>(() =>
            FoundryVersionedAgent.GetAIAgentAsync(
                endpoint: TestEndpoint,
                tokenProvider: new FakeAuthenticationTokenProvider(),
                name: null!));
    }

    [Theory]
    [MemberData(nameof(InvalidAgentNameTestData.GetInvalidAgentNames), MemberType = typeof(InvalidAgentNameTestData))]

    public async Task GetAIAgentAsync_WithInvalidAgentName_ThrowsArgumentExceptionAsync(string invalidName)
    {
        // Act & Assert
        ArgumentException exception = await Assert.ThrowsAsync<ArgumentException>(() =>
            FoundryVersionedAgent.GetAIAgentAsync(
                endpoint: TestEndpoint,
                tokenProvider: new FakeAuthenticationTokenProvider(),
                name: invalidName));

        Assert.Equal("name", exception.ParamName);
        Assert.Contains("Agent name must be 1-63 characters long", exception.Message);
    }

    [Fact]
    public async Task GetAIAgentAsync_WithValidName_RetrievesAgentAsync()
    {
        // Arrange
        using HttpHandlerAssert httpHandler = GetAgentRecordHttpHandler("test-agent");

#pragma warning disable CA5399
        using HttpClient httpClient = new(httpHandler);
#pragma warning restore CA5399

        AIProjectClientOptions clientOptions = new()
        {
            Transport = new HttpClientPipelineTransport(httpClient)
        };

        // Act
        FoundryVersionedAgent agent = await FoundryVersionedAgent.GetAIAgentAsync(
            TestEndpoint,
            new FakeAuthenticationTokenProvider(),
            name: "test-agent",
            clientOptions: clientOptions);

        // Assert
        Assert.NotNull(agent);
        Assert.Equal("test-agent", agent.Name);
    }

    #endregion

    #region AsAIAgent tests

    [Fact]
    public void AsAIAgent_WithAgentVersion_CreatesValidAgent()
    {
        // Arrange
        AgentVersion agentVersion = ModelReaderWriter.Read<AgentVersion>(
            BinaryData.FromString(TestDataUtil.GetAgentVersionResponseJson()))!;

        // Act
        FoundryVersionedAgent agent = FoundryVersionedAgent.AsAIAgent(
            TestEndpoint,
            new FakeAuthenticationTokenProvider(),
            agentVersion);

        // Assert
        Assert.NotNull(agent);
        Assert.Equal(agentVersion.Name, agent.Name);
    }

    [Fact]
    public void AsAIAgent_WithAgentRecord_CreatesValidAgent()
    {
        // Arrange
        AgentRecord agentRecord = ModelReaderWriter.Read<AgentRecord>(
            BinaryData.FromString(TestDataUtil.GetAgentResponseJson()))!;

        // Act
        FoundryVersionedAgent agent = FoundryVersionedAgent.AsAIAgent(
            TestEndpoint,
            new FakeAuthenticationTokenProvider(),
            agentRecord);

        // Assert
        Assert.NotNull(agent);
        Assert.Equal(agentRecord.Name, agent.Name);
    }

    [Fact]
    public void AsAIAgent_WithAgentReference_CreatesValidAgent()
    {
        // Arrange
        AgentReference agentReference = new("test-name", "1");

        // Act
        FoundryVersionedAgent agent = FoundryVersionedAgent.AsAIAgent(
            TestEndpoint,
            new FakeAuthenticationTokenProvider(),
            agentReference);

        // Assert
        Assert.NotNull(agent);
        Assert.Equal("test-name", agent.Name);
    }

    [Fact]
    public void AsAIAgent_WithNullEndpoint_ThrowsArgumentNullException()
    {
        // Arrange
        AgentVersion agentVersion = ModelReaderWriter.Read<AgentVersion>(
            BinaryData.FromString(TestDataUtil.GetAgentVersionResponseJson()))!;

        // Act & Assert
        ArgumentNullException exception = Assert.Throws<ArgumentNullException>(() =>
            FoundryVersionedAgent.AsAIAgent(
                endpoint: null!,
                tokenProvider: new FakeAuthenticationTokenProvider(),
                agentVersion: agentVersion));

        Assert.Equal("endpoint", exception.ParamName);
    }

    [Fact]
    public void AsAIAgent_WithNullAgentVersion_ThrowsArgumentNullException()
    {
        // Act & Assert
        ArgumentNullException exception = Assert.Throws<ArgumentNullException>(() =>
            FoundryVersionedAgent.AsAIAgent(
                endpoint: TestEndpoint,
                tokenProvider: new FakeAuthenticationTokenProvider(),
                agentVersion: null!));

        Assert.Equal("agentVersion", exception.ParamName);
    }

    [Fact]
    public void AsAIAgent_WithAgentReference_SetsAgentIdCorrectly()
    {
        // Arrange
        AgentReference agentReference = new("test-name", "2");

        // Act
        FoundryVersionedAgent agent = FoundryVersionedAgent.AsAIAgent(
            TestEndpoint,
            new FakeAuthenticationTokenProvider(),
            agentReference);

        // Assert
        Assert.Equal("test-name:2", agent.Id);
    }

    #endregion

    #region Delete tests

    [Fact]
    public async Task DeleteAIAgentAsync_WithNullAgent_ThrowsArgumentNullExceptionAsync()
    {
        // Act & Assert
        ArgumentNullException exception = await Assert.ThrowsAsync<ArgumentNullException>(() =>
            FoundryVersionedAgent.DeleteAIAgentAsync(agent: null!));

        Assert.Equal("agent", exception.ParamName);
    }

    [Fact]
    public async Task DeleteAIAgentVersionAsync_WithNullAgent_ThrowsArgumentNullExceptionAsync()
    {
        // Act & Assert
        ArgumentNullException exception = await Assert.ThrowsAsync<ArgumentNullException>(() =>
            FoundryVersionedAgent.DeleteAIAgentVersionAsync(agent: null!));

        Assert.Equal("agent", exception.ParamName);
    }

    #endregion

    #region Metadata / GetService tests

    [Fact]
    public void GetService_ReturnsAIProjectClient()
    {
        // Arrange
        AgentVersion agentVersion = ModelReaderWriter.Read<AgentVersion>(
            BinaryData.FromString(TestDataUtil.GetAgentVersionResponseJson()))!;

        FoundryVersionedAgent agent = FoundryVersionedAgent.AsAIAgent(
            TestEndpoint,
            new FakeAuthenticationTokenProvider(),
            agentVersion);

        // Act
        AIProjectClient? client = agent.GetService<AIProjectClient>();

        // Assert
        Assert.NotNull(client);
    }

    [Fact]
    public void GetService_ReturnsAgentVersion()
    {
        // Arrange
        AgentVersion agentVersion = ModelReaderWriter.Read<AgentVersion>(
            BinaryData.FromString(TestDataUtil.GetAgentVersionResponseJson()))!;

        FoundryVersionedAgent agent = FoundryVersionedAgent.AsAIAgent(
            TestEndpoint,
            new FakeAuthenticationTokenProvider(),
            agentVersion);

        // Act
        AgentVersion? retrievedVersion = agent.GetService<AgentVersion>();

        // Assert
        Assert.NotNull(retrievedVersion);
        Assert.Equal(agentVersion.Id, retrievedVersion.Id);
    }

    [Fact]
    public void GetService_ReturnsChatClientAgent()
    {
        // Arrange
        AgentVersion agentVersion = ModelReaderWriter.Read<AgentVersion>(
            BinaryData.FromString(TestDataUtil.GetAgentVersionResponseJson()))!;

        FoundryVersionedAgent agent = FoundryVersionedAgent.AsAIAgent(
            TestEndpoint,
            new FakeAuthenticationTokenProvider(),
            agentVersion);

        // Act
        ChatClientAgent? innerAgent = agent.GetService<ChatClientAgent>();

        // Assert
        Assert.NotNull(innerAgent);
    }

    [Fact]
    public void GetService_ReturnsAIAgentMetadata_WithFoundryProvider()
    {
        // Arrange
        AgentVersion agentVersion = ModelReaderWriter.Read<AgentVersion>(
            BinaryData.FromString(TestDataUtil.GetAgentVersionResponseJson()))!;

        FoundryVersionedAgent agent = FoundryVersionedAgent.AsAIAgent(
            TestEndpoint,
            new FakeAuthenticationTokenProvider(),
            agentVersion);

        // Act
        AIAgentMetadata? metadata = agent.GetService<AIAgentMetadata>();

        // Assert
        Assert.NotNull(metadata);
        Assert.Equal("microsoft.foundry", metadata.ProviderName);
    }

    [Fact]
    public void Name_ReturnsAgentName()
    {
        // Arrange
        AgentVersion agentVersion = ModelReaderWriter.Read<AgentVersion>(
            BinaryData.FromString(TestDataUtil.GetAgentVersionResponseJson(agentName: "my-versioned-agent")))!;

        FoundryVersionedAgent agent = FoundryVersionedAgent.AsAIAgent(
            TestEndpoint,
            new FakeAuthenticationTokenProvider(),
            agentVersion);

        // Act & Assert
        Assert.Equal("my-versioned-agent", agent.Name);
    }

    [Fact]
    public void Description_ReturnsAgentDescription()
    {
        // Arrange
        AgentVersion agentVersion = ModelReaderWriter.Read<AgentVersion>(
            BinaryData.FromString(TestDataUtil.GetAgentVersionResponseJson(description: "Agent description")))!;

        FoundryVersionedAgent agent = FoundryVersionedAgent.AsAIAgent(
            TestEndpoint,
            new FakeAuthenticationTokenProvider(),
            agentVersion);

        // Act & Assert
        Assert.Equal("Agent description", agent.Description);
    }

    #endregion

    #region User-Agent header tests

    [Fact]
    public async Task CreateAIAgentAsync_UserAgentHeaderAddedToRequestsAsync()
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

            return new HttpResponseMessage(HttpStatusCode.OK)
            {
                Content = new StringContent(
                    TestDataUtil.GetAgentVersionResponseJson(),
                    Encoding.UTF8,
                    "application/json")
            };
        });

#pragma warning disable CA5399
        using HttpClient httpClient = new(httpHandler);
#pragma warning restore CA5399

        AIProjectClientOptions clientOptions = new()
        {
            Transport = new HttpClientPipelineTransport(httpClient)
        };

        // Act
        FoundryVersionedAgent agent = await FoundryVersionedAgent.CreateAIAgentAsync(
            TestEndpoint,
            new FakeAuthenticationTokenProvider(),
            name: "test-agent",
            model: "gpt-4o-mini",
            instructions: "Test instructions",
            clientOptions: clientOptions);

        // Assert
        Assert.NotNull(agent);
        Assert.True(userAgentFound, "MEAI user-agent header was not found in the request");
    }

    #endregion

    #region Helpers

    private static HttpHandlerAssert CreateAgentVersionHttpHandler(string agentName = "test-agent", string? description = null)
    {
        int requestCount = 0;
        return new HttpHandlerAssert(request =>
        {
            requestCount++;
            string responseJson = requestCount == 1
                ? TestDataUtil.GetAgentVersionResponseJson(agentName: agentName, description: description)
                : TestDataUtil.GetOpenAIDefaultResponseJson();
            return new HttpResponseMessage(HttpStatusCode.OK)
            {
                Content = new StringContent(responseJson, Encoding.UTF8, "application/json")
            };
        });
    }

    private static HttpHandlerAssert GetAgentRecordHttpHandler(string agentName = "test-agent")
    {
        int requestCount = 0;
        return new HttpHandlerAssert(request =>
        {
            requestCount++;
            string responseJson = requestCount == 1
                ? TestDataUtil.GetAgentResponseJson(agentName: agentName)
                : TestDataUtil.GetOpenAIDefaultResponseJson();
            return new HttpResponseMessage(HttpStatusCode.OK)
            {
                Content = new StringContent(responseJson, Encoding.UTF8, "application/json")
            };
        });
    }

    #endregion
}
