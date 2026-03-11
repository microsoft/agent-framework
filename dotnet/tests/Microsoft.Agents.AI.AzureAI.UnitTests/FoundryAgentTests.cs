// Copyright (c) Microsoft. All rights reserved.

using System;
using System.ClientModel.Primitives;
using System.Net;
using System.Net.Http;
using System.Text;
using System.Threading.Tasks;
using Azure.AI.Projects;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.AzureAI.UnitTests;

public class FoundryAgentTests
{
    private static readonly Uri TestEndpoint = new("https://test.services.ai.azure.com/api/projects/test-project");

    #region Constructor validation tests

    [Fact]
    public void Constructor_WithNullEndpoint_ThrowsArgumentNullException()
    {
        // Act & Assert
        ArgumentNullException exception = Assert.Throws<ArgumentNullException>(() =>
            new FoundryAgent(
                endpoint: null!,
                tokenProvider: new FakeAuthenticationTokenProvider(),
                model: "gpt-4o-mini"));

        Assert.Equal("endpoint", exception.ParamName);
    }

    [Fact]
    public void Constructor_WithNullTokenProvider_ThrowsArgumentNullException()
    {
        // Act & Assert
        ArgumentNullException exception = Assert.Throws<ArgumentNullException>(() =>
            new FoundryAgent(
                endpoint: TestEndpoint,
                tokenProvider: null!,
                model: "gpt-4o-mini"));

        Assert.Equal("tokenProvider", exception.ParamName);
    }

    [Fact]
    public void Constructor_WithNullModel_ThrowsArgumentException()
    {
        // Act & Assert
        Assert.ThrowsAny<ArgumentException>(() =>
            new FoundryAgent(
                endpoint: TestEndpoint,
                tokenProvider: new FakeAuthenticationTokenProvider(),
                model: null!));
    }

    [Fact]
    public void Constructor_WithEmptyModel_ThrowsArgumentException()
    {
        // Act & Assert
        Assert.ThrowsAny<ArgumentException>(() =>
            new FoundryAgent(
                endpoint: TestEndpoint,
                tokenProvider: new FakeAuthenticationTokenProvider(),
                model: string.Empty));
    }

    [Fact]
    public void Constructor_WithNullOptions_ThrowsArgumentNullException()
    {
        // Act & Assert
        ArgumentNullException exception = Assert.Throws<ArgumentNullException>(() =>
            new FoundryAgent(
                endpoint: TestEndpoint,
                tokenProvider: new FakeAuthenticationTokenProvider(),
                options: null!));

        Assert.Equal("options", exception.ParamName);
    }

    [Fact]
    public void Constructor_WithOptionsWithoutModelId_ThrowsArgumentException()
    {
        // Arrange
        ChatClientAgentOptions options = new()
        {
            ChatOptions = new ChatOptions()
        };

        // Act & Assert
        Assert.ThrowsAny<ArgumentException>(() =>
            new FoundryAgent(
                endpoint: TestEndpoint,
                tokenProvider: new FakeAuthenticationTokenProvider(),
                options: options));
    }

    [Fact]
    public void Constructor_WithValidParams_CreatesAgent()
    {
        // Act
        FoundryAgent agent = new(
            TestEndpoint,
            new FakeAuthenticationTokenProvider(),
            model: "gpt-4o-mini",
            name: "test-agent",
            description: "A test agent");

        // Assert
        Assert.NotNull(agent);
        Assert.Equal("test-agent", agent.Name);
        Assert.Equal("A test agent", agent.Description);
    }

    [Fact]
    public void Constructor_WithOptions_CreatesAgent()
    {
        // Arrange
        ChatClientAgentOptions options = new()
        {
            Name = "options-agent",
            Description = "Agent from options",
            ChatOptions = new ChatOptions { ModelId = "gpt-4o-mini" }
        };

        // Act
        FoundryAgent agent = new(
            TestEndpoint,
            new FakeAuthenticationTokenProvider(),
            options: options);

        // Assert
        Assert.NotNull(agent);
        Assert.Equal("options-agent", agent.Name);
        Assert.Equal("Agent from options", agent.Description);
    }

    #endregion

    #region Property / metadata tests

    [Fact]
    public void Name_ReturnsConfiguredName()
    {
        // Arrange
        FoundryAgent agent = new(
            TestEndpoint,
            new FakeAuthenticationTokenProvider(),
            model: "gpt-4o-mini",
            name: "my-agent");

        // Act & Assert
        Assert.Equal("my-agent", agent.Name);
    }

    [Fact]
    public void Description_ReturnsConfiguredDescription()
    {
        // Arrange
        FoundryAgent agent = new(
            TestEndpoint,
            new FakeAuthenticationTokenProvider(),
            model: "gpt-4o-mini",
            description: "Agent description");

        // Act & Assert
        Assert.Equal("Agent description", agent.Description);
    }

    [Fact]
    public void GetService_ReturnsAIProjectClient()
    {
        // Arrange
        FoundryAgent agent = new(
            TestEndpoint,
            new FakeAuthenticationTokenProvider(),
            model: "gpt-4o-mini");

        // Act
        AIProjectClient? client = agent.GetService<AIProjectClient>();

        // Assert
        Assert.NotNull(client);
    }

    [Fact]
    public void GetService_ReturnsChatClientAgent()
    {
        // Arrange
        FoundryAgent agent = new(
            TestEndpoint,
            new FakeAuthenticationTokenProvider(),
            model: "gpt-4o-mini");

        // Act
        ChatClientAgent? innerAgent = agent.GetService<ChatClientAgent>();

        // Assert
        Assert.NotNull(innerAgent);
    }

    [Fact]
    public void GetService_ReturnsAIAgentMetadata_WithFoundryProvider()
    {
        // Arrange
        FoundryAgent agent = new(
            TestEndpoint,
            new FakeAuthenticationTokenProvider(),
            model: "gpt-4o-mini");

        // Act
        AIAgentMetadata? metadata = agent.GetService<AIAgentMetadata>();

        // Assert
        Assert.NotNull(metadata);
        Assert.Equal("microsoft.foundry", metadata.ProviderName);
    }

    #endregion

    #region Functional tests

    [Fact]
    public async Task RunAsync_SendsRequestToResponsesAPIAsync()
    {
        // Arrange
        bool requestTriggered = false;
        using HttpHandlerAssert httpHandler = new(request =>
        {
            if (request.Method == HttpMethod.Post && request.RequestUri!.PathAndQuery.Contains("/responses"))
            {
                requestTriggered = true;
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

        AIProjectClientOptions clientOptions = new()
        {
            Transport = new HttpClientPipelineTransport(httpClient)
        };

        FoundryAgent agent = new(
            TestEndpoint,
            new FakeAuthenticationTokenProvider(),
            model: "gpt-4o-mini",
            clientOptions: clientOptions);

        // Act
        AgentSession session = await agent.CreateSessionAsync();
        await agent.RunAsync("Hello", session);

        // Assert
        Assert.True(requestTriggered);
    }

    [Fact]
    public void Constructor_WithChatClientFactory_AppliesFactory()
    {
        // Arrange
        bool factoryCalled = false;

        // Act
        FoundryAgent agent = new(
            TestEndpoint,
            new FakeAuthenticationTokenProvider(),
            model: "gpt-4o-mini",
            chatClientFactory: client =>
            {
                factoryCalled = true;
                return client;
            });

        // Assert
        Assert.True(factoryCalled);
        Assert.NotNull(agent);
    }

    [Fact]
    public async Task Constructor_UserAgentHeaderAddedToRequestsAsync()
    {
        // Arrange
        bool userAgentFound = false;
        using HttpHandlerAssert httpHandler = new(request =>
        {
            if (request.Headers.TryGetValues("User-Agent", out System.Collections.Generic.IEnumerable<string>? values))
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

        AIProjectClientOptions clientOptions = new()
        {
            Transport = new HttpClientPipelineTransport(httpClient)
        };

        FoundryAgent agent = new(
            TestEndpoint,
            new FakeAuthenticationTokenProvider(),
            model: "gpt-4o-mini",
            clientOptions: clientOptions);

        // Act
        AgentSession session = await agent.CreateSessionAsync();
        await agent.RunAsync("Hello", session);

        // Assert
        Assert.True(userAgentFound, "MEAI user-agent header was not found in any request");
    }

    #endregion
}
