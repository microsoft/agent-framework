// Copyright (c) Microsoft. All rights reserved.

using System;
using System.ClientModel.Primitives;
using System.Net;
using System.Net.Http;
using System.Text;
using System.Threading.Tasks;
using Azure.AI.Projects;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Foundry.UnitTests;

/// <summary>
/// Unit tests for the <see cref="FoundryAgent"/> class.
/// </summary>
public class FoundryAgentTests
{
    private static readonly Uri s_testEndpoint = new("https://test.services.ai.azure.com/api/projects/test-project");

    #region Constructor validation tests

    [Fact]
    public void Constructor_WithNullEndpoint_ThrowsArgumentNullException()
    {
        ArgumentNullException exception = Assert.Throws<ArgumentNullException>(() =>
            new FoundryAgent(
                projectEndpoint: null!,
                credential: new FakeAuthenticationTokenProvider(),
                model: "gpt-4o-mini",
                instructions: "Test instructions"));

        Assert.Equal("endpoint", exception.ParamName);
    }

    [Fact]
    public void Constructor_WithNullCredential_ThrowsArgumentNullException()
    {
        ArgumentNullException exception = Assert.Throws<ArgumentNullException>(() =>
            new FoundryAgent(
                projectEndpoint: s_testEndpoint,
                credential: null!,
                model: "gpt-4o-mini",
                instructions: "Test instructions"));

        Assert.Equal("credential", exception.ParamName);
    }

    [Fact]
    public void Constructor_WithNullModel_ThrowsArgumentException()
    {
        Assert.ThrowsAny<ArgumentException>(() =>
            new FoundryAgent(
                projectEndpoint: s_testEndpoint,
                credential: new FakeAuthenticationTokenProvider(),
                model: null!,
                instructions: "Test instructions"));
    }

    [Fact]
    public void Constructor_WithEmptyModel_ThrowsArgumentException()
    {
        Assert.ThrowsAny<ArgumentException>(() =>
            new FoundryAgent(
                projectEndpoint: s_testEndpoint,
                credential: new FakeAuthenticationTokenProvider(),
                model: string.Empty,
                instructions: "Test instructions"));
    }

    [Fact]
    public void Constructor_WithNullInstructions_ThrowsArgumentException()
    {
        Assert.ThrowsAny<ArgumentException>(() =>
            new FoundryAgent(
                projectEndpoint: s_testEndpoint,
                credential: new FakeAuthenticationTokenProvider(),
                model: "gpt-4o-mini",
                instructions: null!));
    }

    [Fact]
    public void Constructor_WithValidParams_CreatesAgent()
    {
        FoundryAgent agent = new(
            s_testEndpoint,
            new FakeAuthenticationTokenProvider(),
            model: "gpt-4o-mini",
            instructions: "You are a helpful assistant.",
            name: "test-agent",
            description: "A test agent");

        Assert.NotNull(agent);
        Assert.Equal("test-agent", agent.Name);
        Assert.Equal("A test agent", agent.Description);
    }

    #endregion

    #region Property tests

    [Fact]
    public void Name_ReturnsConfiguredName()
    {
        FoundryAgent agent = new(
            s_testEndpoint,
            new FakeAuthenticationTokenProvider(),
            model: "gpt-4o-mini",
            instructions: "Test",
            name: "my-agent");

        Assert.Equal("my-agent", agent.Name);
    }

    [Fact]
    public void Description_ReturnsConfiguredDescription()
    {
        FoundryAgent agent = new(
            s_testEndpoint,
            new FakeAuthenticationTokenProvider(),
            model: "gpt-4o-mini",
            instructions: "Test",
            description: "Agent description");

        Assert.Equal("Agent description", agent.Description);
    }

    [Fact]
    public void GetService_ReturnsAIProjectClient()
    {
        FoundryAgent agent = new(
            s_testEndpoint,
            new FakeAuthenticationTokenProvider(),
            model: "gpt-4o-mini",
            instructions: "Test");

        AIProjectClient? client = agent.GetService<AIProjectClient>();

        Assert.NotNull(client);
    }

    [Fact]
    public void GetService_ReturnsChatClientAgent()
    {
        FoundryAgent agent = new(
            s_testEndpoint,
            new FakeAuthenticationTokenProvider(),
            model: "gpt-4o-mini",
            instructions: "Test");

        ChatClientAgent? innerAgent = agent.GetService<ChatClientAgent>();

        Assert.NotNull(innerAgent);
    }

    [Fact]
    public void GetService_ReturnsIChatClient()
    {
        FoundryAgent agent = new(
            s_testEndpoint,
            new FakeAuthenticationTokenProvider(),
            model: "gpt-4o-mini",
            instructions: "Test");

        IChatClient? chatClient = agent.GetService<IChatClient>();

        Assert.NotNull(chatClient);
    }

    [Fact]
    public void GetService_ReturnsChatClientMetadata()
    {
        FoundryAgent agent = new(
            s_testEndpoint,
            new FakeAuthenticationTokenProvider(),
            model: "gpt-4o-mini",
            instructions: "Test");

        ChatClientMetadata? metadata = agent.GetService<ChatClientMetadata>();

        Assert.NotNull(metadata);
        Assert.Equal("microsoft.foundry", metadata.ProviderName);
    }

    [Fact]
    public void GetService_ReturnsNullForUnknownType()
    {
        FoundryAgent agent = new(
            s_testEndpoint,
            new FakeAuthenticationTokenProvider(),
            model: "gpt-4o-mini",
            instructions: "Test");

        Assert.Null(agent.GetService<HttpClient>());
    }

    #endregion

    #region Functional tests

    [Fact]
    public async Task RunAsync_SendsRequestToResponsesAPIAsync()
    {
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
            s_testEndpoint,
            new FakeAuthenticationTokenProvider(),
            model: "gpt-4o-mini",
            instructions: "You are a helpful assistant.",
            clientOptions: clientOptions);

        AgentSession session = await agent.CreateSessionAsync();
        await agent.RunAsync("Hello", session);

        Assert.True(requestTriggered);
    }

    [Fact]
    public void Constructor_WithChatClientFactory_AppliesFactory()
    {
        bool factoryCalled = false;

        FoundryAgent agent = new(
            s_testEndpoint,
            new FakeAuthenticationTokenProvider(),
            model: "gpt-4o-mini",
            instructions: "Test",
            clientFactory: client =>
            {
                factoryCalled = true;
                return client;
            });

        Assert.True(factoryCalled);
        Assert.NotNull(agent);
    }

    [Fact]
    public async Task Constructor_UserAgentHeaderAddedToRequestsAsync()
    {
        bool userAgentFound = false;
        using HttpHandlerAssert httpHandler = new(request =>
        {
            if (request.Headers.TryGetValues("User-Agent", out System.Collections.Generic.IEnumerable<string>? values))
            {
                foreach (string value in values)
                {
                    if (value.StartsWith("MEAI/", StringComparison.OrdinalIgnoreCase))
                    {
                        userAgentFound = true;
                    }
                }
            }

            return new HttpResponseMessage(HttpStatusCode.OK)
            {
                Content = new StringContent(
                    TestDataUtil.GetOpenAIDefaultResponseJson(),
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

        FoundryAgent agent = new(
            s_testEndpoint,
            new FakeAuthenticationTokenProvider(),
            model: "gpt-4o-mini",
            instructions: "Test",
            clientOptions: clientOptions);

        AgentSession session = await agent.CreateSessionAsync();
        await agent.RunAsync("Hello", session);

        Assert.True(userAgentFound, "Expected MEAI user-agent header to be present in requests.");
    }

    #endregion
}
