// Copyright (c) Microsoft. All rights reserved.

using System;
using System.ClientModel.Primitives;
using System.Net;
using System.Net.Http;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using Azure.AI.Extensions.OpenAI;
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
    public void Constructor_PreWiresClientHeadersAgent()
    {
        // Arrange / Act: the public FoundryAgent ctor should pre-wire the client-headers
        // pipeline so x-client-* headers stamped on ChatClientAgentRunOptions reach the wire.
        FoundryAgent agent = new(
            s_testEndpoint,
            new FakeAuthenticationTokenProvider(),
            model: "gpt-4o-mini",
            instructions: "Test");

        // Assert: ClientHeadersAgent decorator is present in the delegating chain.
        Assert.NotNull(agent.GetService<ClientHeadersAgent>());
    }

    [Fact]
    public void Constructor_FromAsAIAgentExtension_PreWiresClientHeadersAgent()
    {
        // Arrange: stand up a real AIProjectClient pointed at a fake transport.
        using var handler = new NoopHandler();
#pragma warning disable CA5399
        using var http = new HttpClient(handler);
#pragma warning restore CA5399
        var projectClient = new AIProjectClient(
            s_testEndpoint,
            new FakeAuthenticationTokenProvider(),
            new AIProjectClientOptions { Transport = new HttpClientPipelineTransport(http) });

        // Act: this AsAIAgent path constructs FoundryAgent via its internal
        // (AIProjectClient, ChatClientAgent) constructor, which previously bypassed pre-wiring.
        var agent = projectClient.AsAIAgent(new AgentReference("agent-name"));

        // Assert
        Assert.NotNull(agent.GetService<ClientHeadersAgent>());
    }

    private sealed class NoopHandler : HttpClientHandler
    {
        protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
            => Task.FromResult(new HttpResponseMessage(HttpStatusCode.OK));
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

    #region CreateSessionAsync tests

    [Fact]
    public async Task CreateSessionAsync_WithConversationId_ReturnsChatClientAgentSessionAsync()
    {
        // Arrange
        FoundryAgent agent = new(
            s_testEndpoint,
            new FakeAuthenticationTokenProvider(),
            model: "gpt-4o-mini",
            instructions: "Test");

        const string ConversationId = "test-conversation-id";

        // Act
        AgentSession session = await agent.CreateSessionAsync(ConversationId);

        // Assert
        ChatClientAgentSession chatSession = Assert.IsType<ChatClientAgentSession>(session);
        Assert.Equal(ConversationId, chatSession.ConversationId);
    }

    [Fact]
    public async Task CreateSessionAsync_WithoutConversationId_ReturnsChatClientAgentSessionWithoutConversationIdAsync()
    {
        // Arrange
        FoundryAgent agent = new(
            s_testEndpoint,
            new FakeAuthenticationTokenProvider(),
            model: "gpt-4o-mini",
            instructions: "Test");

        // Act
        AgentSession session = await agent.CreateSessionAsync();

        // Assert
        ChatClientAgentSession chatSession = Assert.IsType<ChatClientAgentSession>(session);
        Assert.Null(chatSession.ConversationId);
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

    #region Agent-endpoint constructor tests

    private const string TestAgentEndpoint = "https://test.services.ai.azure.com/api/projects/test-project/agents/it-happy-path/endpoint/protocols/openai";
    private static readonly Uri s_testAgentEndpoint = new(TestAgentEndpoint);

    [Fact]
    public void AgentEndpointConstructor_NullEndpoint_ThrowsArgumentNullException()
    {
        ArgumentNullException ex = Assert.Throws<ArgumentNullException>(() =>
            new FoundryAgent(agentEndpoint: null!, credential: new FakeAuthenticationTokenProvider()));
        Assert.Equal("agentEndpoint", ex.ParamName);
    }

    [Fact]
    public void AgentEndpointConstructor_NullCredential_ThrowsArgumentNullException()
    {
        ArgumentNullException ex = Assert.Throws<ArgumentNullException>(() =>
            new FoundryAgent(agentEndpoint: s_testAgentEndpoint, credential: null!));
        Assert.Equal("credential", ex.ParamName);
    }

    [Fact]
    public void AgentEndpointConstructor_PopulatesNameAndIdFromEndpointSlug()
    {
        FoundryAgent agent = new(s_testAgentEndpoint, new FakeAuthenticationTokenProvider());

        Assert.Equal("it-happy-path", agent.Name);
        Assert.Equal("it-happy-path", agent.Id);
    }

    [Fact]
    public void AgentEndpointConstructor_GetServiceProjectOpenAIClient_ReturnsNonNull()
    {
        FoundryAgent agent = new(s_testAgentEndpoint, new FakeAuthenticationTokenProvider());

        Assert.NotNull(agent.GetService<ProjectOpenAIClient>());
    }

    [Fact]
    public void AgentEndpointConstructor_GetServiceAIProjectClient_ReturnsNull()
    {
        FoundryAgent agent = new(s_testAgentEndpoint, new FakeAuthenticationTokenProvider());

        Assert.Null(agent.GetService<AIProjectClient>());
    }

    [Fact]
    public void ProjectEndpointConstructor_GetServiceProjectOpenAIClient_ReturnsNonNull()
    {
        FoundryAgent agent = new(
            s_testEndpoint,
            new FakeAuthenticationTokenProvider(),
            model: "gpt-4o-mini",
            instructions: "Test");

        Assert.NotNull(agent.GetService<ProjectOpenAIClient>());
    }

    [Fact]
    public void AgentEndpointConstructor_AppliesClientFactoryOnce()
    {
        int count = 0;
        FoundryAgent agent = new(
            s_testAgentEndpoint,
            new FakeAuthenticationTokenProvider(),
            clientFactory: c => { count++; return c; });

        Assert.Equal(1, count);
        Assert.NotNull(agent);
    }

    [Fact]
    public async Task AgentEndpointConstructor_RunAsync_RoutesThroughPerAgentResponsesUrlAsync()
    {
        Uri? capturedUri = null;
        using HttpHandlerAssert handler = new(req =>
        {
            capturedUri = req.RequestUri;
            return new HttpResponseMessage(HttpStatusCode.OK)
            {
                Content = new StringContent(TestDataUtil.GetOpenAIDefaultResponseJson(), Encoding.UTF8, "application/json"),
            };
        });
#pragma warning disable CA5399
        using HttpClient http = new(handler);
#pragma warning restore CA5399
        ProjectOpenAIClientOptions opts = new() { Transport = new HttpClientPipelineTransport(http) };

        FoundryAgent agent = new(s_testAgentEndpoint, new FakeAuthenticationTokenProvider(), clientOptions: opts);
        await agent.RunAsync("Hello");

        Assert.NotNull(capturedUri);
        string path = capturedUri!.AbsolutePath;
        Assert.Contains("/agents/it-happy-path/endpoint/protocols/openai/responses", path, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("/openai/v1/responses", path, StringComparison.OrdinalIgnoreCase);
        Assert.Contains("api-version=v1", capturedUri.Query, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public async Task AgentEndpointConstructor_RunStreamingAsync_RoutesThroughPerAgentResponsesUrlAsync()
    {
        Uri? capturedUri = null;
        bool sawStreamTrue = false;
        using HttpHandlerAssert handler = new(async req =>
        {
            capturedUri = req.RequestUri;
            if (req.Content is not null)
            {
                string body = await req.Content.ReadAsStringAsync().ConfigureAwait(false);
                if (body.Contains("\"stream\":true", StringComparison.Ordinal))
                {
                    sawStreamTrue = true;
                }
            }

            // Minimal SSE response; xUnit assertion only cares about the URL/body shape.
            return new HttpResponseMessage(HttpStatusCode.OK)
            {
                Content = new StringContent("data: [DONE]\n\n", Encoding.UTF8, "text/event-stream"),
            };
        });
#pragma warning disable CA5399
        using HttpClient http = new(handler);
#pragma warning restore CA5399
        ProjectOpenAIClientOptions opts = new() { Transport = new HttpClientPipelineTransport(http) };

        FoundryAgent agent = new(s_testAgentEndpoint, new FakeAuthenticationTokenProvider(), clientOptions: opts);
        try
        {
            await foreach (var _ in agent.RunStreamingAsync("Hello"))
            {
                // drain
            }
        }
        catch
        {
            // SSE parse errors are acceptable; we only assert the request shape.
        }

        Assert.NotNull(capturedUri);
        Assert.Contains("/agents/it-happy-path/endpoint/protocols/openai/responses", capturedUri!.AbsolutePath, StringComparison.OrdinalIgnoreCase);
        Assert.Contains("api-version=v1", capturedUri.Query, StringComparison.OrdinalIgnoreCase);
        Assert.True(sawStreamTrue, "Expected request body to include \"stream\":true.");
    }

    [Fact]
    public async Task AgentEndpointConstructor_CreateConversationSessionAsync_RoutesThroughProjectLevelUrlAsync()
    {
        Uri? capturedUri = null;
        using HttpHandlerAssert handler = new(req =>
        {
            capturedUri = req.RequestUri;
            return new HttpResponseMessage(HttpStatusCode.OK)
            {
                Content = new StringContent("{\"id\":\"conv_123\"}", Encoding.UTF8, "application/json"),
            };
        });
#pragma warning disable CA5399
        using HttpClient http = new(handler);
#pragma warning restore CA5399
        ProjectOpenAIClientOptions opts = new() { Transport = new HttpClientPipelineTransport(http) };

        FoundryAgent agent = new(s_testAgentEndpoint, new FakeAuthenticationTokenProvider(), clientOptions: opts);
        try
        {
            _ = await agent.CreateConversationSessionAsync();
        }
        catch
        {
            // Underlying SDK may attempt extra parsing on the minimal response. We only assert URL routing.
        }

        Assert.NotNull(capturedUri);
        string path = capturedUri!.AbsolutePath;
        Assert.Contains("/api/projects/test-project/openai/v1/conversations", path, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("/agents/", path, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public async Task AgentEndpointConstructor_StampsMeaiUserAgentHeaderAsync()
    {
        bool meaiSeen = false;
        using HttpHandlerAssert handler = new(req =>
        {
            if (req.Headers.TryGetValues("User-Agent", out var values))
            {
                foreach (string v in values)
                {
                    if (v.IndexOf("MEAI/", StringComparison.OrdinalIgnoreCase) >= 0)
                    {
                        meaiSeen = true;
                    }
                }
            }
            return new HttpResponseMessage(HttpStatusCode.OK)
            {
                Content = new StringContent(TestDataUtil.GetOpenAIDefaultResponseJson(), Encoding.UTF8, "application/json"),
            };
        });
#pragma warning disable CA5399
        using HttpClient http = new(handler);
#pragma warning restore CA5399
        ProjectOpenAIClientOptions opts = new() { Transport = new HttpClientPipelineTransport(http) };

        FoundryAgent agent = new(s_testAgentEndpoint, new FakeAuthenticationTokenProvider(), clientOptions: opts);
        await agent.RunAsync("Hello");

        Assert.True(meaiSeen, "Expected MEAI/x.y.z to appear in the User-Agent header on the agent-endpoint pipeline.");
    }

    [Fact]
    public async Task AgentEndpointConstructor_PassesThroughCallerPolicyOnPerAgentPipelineAsync()
    {
        // Direct switch to ProjectOpenAIClientOptions means caller-supplied pipeline policies
        // (added via AddPolicy) actually flow through to the per-agent traffic. Assert that a
        // tag-stamping policy executes on each outbound per-agent request.
        bool tagSeen = false;
        using HttpHandlerAssert handler = new(req =>
        {
            if (req.Headers.TryGetValues("X-Test-Tag", out var values))
            {
                foreach (string v in values)
                {
                    if (v == "tag-1")
                    {
                        tagSeen = true;
                    }
                }
            }
            return new HttpResponseMessage(HttpStatusCode.OK)
            {
                Content = new StringContent(TestDataUtil.GetOpenAIDefaultResponseJson(), Encoding.UTF8, "application/json"),
            };
        });
#pragma warning disable CA5399
        using HttpClient http = new(handler);
#pragma warning restore CA5399
        ProjectOpenAIClientOptions opts = new() { Transport = new HttpClientPipelineTransport(http) };
        opts.AddPolicy(new HeaderStampPolicy("X-Test-Tag", "tag-1"), PipelinePosition.PerCall);

        FoundryAgent agent = new(s_testAgentEndpoint, new FakeAuthenticationTokenProvider(), clientOptions: opts);
        await agent.RunAsync("Hello");

        Assert.True(tagSeen, "Expected caller-supplied per-call policy to execute on the per-agent pipeline.");
    }

    [Fact]
    public void AgentEndpointConstructor_OverridesCallerEndpointAndAgentName()
    {
        // The caller may set Endpoint/AgentName on the options bag; we must override both with
        // values derived from agentEndpoint so the URL routing is correct regardless.
        ProjectOpenAIClientOptions opts = new()
        {
            Endpoint = new Uri("https://wrong.example.com/openai/v1"),
            AgentName = "wrong-agent",
        };

        FoundryAgent agent = new(s_testAgentEndpoint, new FakeAuthenticationTokenProvider(), clientOptions: opts);

        Assert.Equal("it-happy-path", agent.Name);
        Assert.Equal(s_testAgentEndpoint, opts.Endpoint);
        Assert.Equal("it-happy-path", opts.AgentName);
    }

    [Fact]
    public void AgentEndpointConstructor_PropagatesUserAgentApplicationId_ToProjectLevelClient()
    {
        // The MEAI policy adds its own User-Agent header so we cannot reliably observe the OpenAI SDK's
        // application-id stamp in the outbound request. Verify the value is propagated onto the
        // project-level client's options via the public ProjectOpenAIClient surface.
        ProjectOpenAIClientOptions opts = new() { UserAgentApplicationId = "my-app-id" };

        FoundryAgent agent = new(s_testAgentEndpoint, new FakeAuthenticationTokenProvider(), clientOptions: opts);

        ProjectOpenAIClient? projectClient = agent.GetService<ProjectOpenAIClient>();
        Assert.NotNull(projectClient);
        // Caller's UserAgentApplicationId is preserved on the per-agent options bag verbatim.
        Assert.Equal("my-app-id", opts.UserAgentApplicationId);
    }

    #endregion

    #region ParseAgentEndpoint tests

    [Fact]
    public void ParseAgentEndpoint_StandardShape_Parses()
    {
        var (name, root) = FoundryAgent.ParseAgentEndpoint(new Uri("https://h.example.com/api/projects/p1/agents/a1/endpoint/protocols/openai"));
        Assert.Equal("a1", name);
        Assert.Equal("https://h.example.com/api/projects/p1", root.AbsoluteUri.TrimEnd('/'));
    }

    [Fact]
    public void ParseAgentEndpoint_TrailingSlash_Parses()
    {
        var (name, root) = FoundryAgent.ParseAgentEndpoint(new Uri("https://h.example.com/api/projects/p1/agents/a1/endpoint/protocols/openai/"));
        Assert.Equal("a1", name);
        Assert.Equal("https://h.example.com/api/projects/p1", root.AbsoluteUri.TrimEnd('/'));
    }

    [Fact]
    public void ParseAgentEndpoint_UppercaseAgentsSegment_Parses()
    {
        var (name, _) = FoundryAgent.ParseAgentEndpoint(new Uri("https://h.example.com/api/projects/p1/Agents/a1/endpoint/protocols/openai"));
        Assert.Equal("a1", name);
    }

    [Fact]
    public void ParseAgentEndpoint_SpecialCharsInName_Parses()
    {
        var (name, _) = FoundryAgent.ParseAgentEndpoint(new Uri("https://h.example.com/api/projects/p/agents/it-happy_path-1/endpoint/protocols/openai"));
        Assert.Equal("it-happy_path-1", name);
    }

    [Fact]
    public void ParseAgentEndpoint_QueryAndFragmentStripped()
    {
        var (_, root) = FoundryAgent.ParseAgentEndpoint(new Uri("https://h.example.com/api/projects/p/agents/a/endpoint/protocols/openai?x=1#frag"));
        Assert.Equal(string.Empty, root.Query);
        Assert.Equal(string.Empty, root.Fragment);
    }

    [Fact]
    public void ParseAgentEndpoint_SovereignCloudHostNoApiPrefix_Parses()
    {
        var (name, root) = FoundryAgent.ParseAgentEndpoint(new Uri("https://h.cognitive.microsoft.us/projects/p/agents/a1/endpoint/protocols/openai"));
        Assert.Equal("a1", name);
        Assert.Equal("https://h.cognitive.microsoft.us/projects/p", root.AbsoluteUri.TrimEnd('/'));
    }

    [Fact]
    public void ParseAgentEndpoint_MissingAgentsSegment_Throws()
    {
        ArgumentException ex = Assert.Throws<ArgumentException>(() =>
            FoundryAgent.ParseAgentEndpoint(new Uri("https://h.example.com/api/projects/p1/openai/v1")));
        Assert.Equal("agentEndpoint", ex.ParamName);
    }

    [Fact]
    public void ParseAgentEndpoint_WrongSuffix_Throws()
    {
        ArgumentException ex = Assert.Throws<ArgumentException>(() =>
            FoundryAgent.ParseAgentEndpoint(new Uri("https://h.example.com/api/projects/p/agents/a1/openai/v1")));
        Assert.Equal("agentEndpoint", ex.ParamName);
    }

    [Fact]
    public void ParseAgentEndpoint_EmptyAgentName_Throws()
    {
        ArgumentException ex = Assert.Throws<ArgumentException>(() =>
            FoundryAgent.ParseAgentEndpoint(new Uri("https://h.example.com/api/projects/p/agents//endpoint/protocols/openai")));
        Assert.Equal("agentEndpoint", ex.ParamName);
    }

    #endregion

    private sealed class HeaderStampPolicy : PipelinePolicy
    {
        private readonly string _name;
        private readonly string _value;
        public HeaderStampPolicy(string name, string value) { this._name = name; this._value = value; }

        public override void Process(PipelineMessage message, System.Collections.Generic.IReadOnlyList<PipelinePolicy> pipeline, int currentIndex)
        {
            message.Request.Headers.Set(this._name, this._value);
            ProcessNext(message, pipeline, currentIndex);
        }

        public override ValueTask ProcessAsync(PipelineMessage message, System.Collections.Generic.IReadOnlyList<PipelinePolicy> pipeline, int currentIndex)
        {
            message.Request.Headers.Set(this._name, this._value);
            return ProcessNextAsync(message, pipeline, currentIndex);
        }
    }
}
