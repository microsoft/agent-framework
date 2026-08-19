// Copyright (c) Microsoft. All rights reserved.

using System;
using System.ClientModel;
using System.ClientModel.Primitives;
using System.Collections.Generic;
using System.Net;
using System.Net.Http;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using OpenAI;
using OpenAI.Responses;

#pragma warning disable OPENAI001, MEAI001, MAAI001, SCME0001

namespace Microsoft.Agents.AI.Foundry.UnitTests;

/// <summary>
/// Tests for hosted-agent session sticky behavior and per-call user identity.
/// </summary>
public sealed class FoundryHostedRequestTests
{
    [Fact]
    public void WithFoundryHostedAgentSessionId_WritesOptionsCarrier()
    {
        var options = new ChatOptions();
        options.WithFoundryHostedAgentSessionId("sess-1");
        Assert.Equal("sess-1", options.GetFoundryHostedAgentSessionId());
    }

    [Fact]
    public void WithFoundryHostedAgentUserIdentity_WritesOptionsCarrier()
    {
        var options = new ChatOptions();
        options.WithFoundryHostedAgentUserIdentity("alice");
        Assert.Equal("alice", options.GetFoundryHostedAgentUserIdentity());
    }

    [Fact]
    public async Task CreateFoundryHostedAgentSessionAsync_PinsHostedAndConversationIdsAsync()
    {
        FoundryAgent agent = CreateFoundryAgent();
        ChatClientAgentSession session = await agent.CreateFoundryHostedAgentSessionAsync(
            hostedSessionId: "sess-1",
            conversationId: "conv-1");

        Assert.Equal("sess-1", session.FoundryHostedAgentSessionId);
        Assert.Equal("conv-1", session.ConversationId);
        Assert.True(session.StateBag.TryGetValue<string>(FoundryAgentSessionExtensions.FoundryHostedAgentSessionIdKey, out var raw));
        Assert.Equal("sess-1", raw);
    }

    [Fact]
    public async Task CreateFoundryHostedAgentSessionAsync_WithoutIds_LeavesBothEmptyAsync()
    {
        FoundryAgent agent = CreateFoundryAgent();
        ChatClientAgentSession session = await agent.CreateFoundryHostedAgentSessionAsync();

        Assert.Null(session.FoundryHostedAgentSessionId);
        Assert.Null(session.ConversationId);
    }

    [Fact]
    public async Task CreateFoundryHostedAgentSessionAsync_WhitespaceHostedId_ThrowsAsync()
    {
        FoundryAgent agent = CreateFoundryAgent();

        await Assert.ThrowsAsync<ArgumentException>(
            () => agent.CreateFoundryHostedAgentSessionAsync(hostedSessionId: "   "));
    }

    [Fact]
    public async Task Conflict_SessionAndOptionsHostedIdsDiffer_ThrowsAsync()
    {
        var inner = new ProbeAgent();
        var agent = new FoundryHostedRequestAgent(inner);
        var session = new TestSession();
        session.FoundryHostedAgentSessionId = "sess-A";
        var runOptions = new ChatClientAgentRunOptions(
            new ChatOptions().WithFoundryHostedAgentSessionId("sess-B"));

        InvalidOperationException ex = await Assert.ThrowsAsync<InvalidOperationException>(
            () => agent.RunAsync("hi", session, runOptions));
        Assert.Contains("hosted-agent session id", ex.Message, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public async Task SameHostedId_OnSessionAndOptions_DoesNotThrowAsync()
    {
        var inner = new ProbeAgent();
        var agent = new FoundryHostedRequestAgent(inner);
        var session = new TestSession();
        session.FoundryHostedAgentSessionId = "sess-A";
        var runOptions = new ChatClientAgentRunOptions(
            new ChatOptions().WithFoundryHostedAgentSessionId("sess-A"));

        await agent.RunAsync("hi", session, runOptions);
        Assert.Equal(1, inner.RunCount);
    }

    [Fact]
    public async Task Sticky_SessionHostedId_IsInjectedIntoCreateResponseOptionsAsync()
    {
        CreateResponseOptions? seen = null;
        var inner = new ProbeAgent(onRun: options =>
        {
            if (options is ChatClientAgentRunOptions { ChatOptions.RawRepresentationFactory: { } factory })
            {
                seen = factory(null!) as CreateResponseOptions;
            }
        });
        var agent = new FoundryHostedRequestAgent(inner);
        var session = new TestSession();
        session.FoundryHostedAgentSessionId = "sess-sticky";

        await agent.RunAsync("hi", session);

        Assert.NotNull(seen);
        Assert.True(seen!.Patch.Contains("$.agent_session_id"u8));
    }

    [Fact]
    public async Task OptionsHostedId_WhenSessionEmpty_IsInjectedAndStickyAfterRunAsync()
    {
        var inner = new ProbeAgent();
        var agent = new FoundryHostedRequestAgent(inner);
        var session = new TestSession();
        var runOptions = new ChatClientAgentRunOptions(
            new ChatOptions().WithFoundryHostedAgentSessionId("sess-options"));

        await agent.RunAsync("hi", session, runOptions);
        Assert.Equal("sess-options", session.FoundryHostedAgentSessionId);
    }

    [Fact]
    public async Task UserIdentity_DifferentPerCall_OnSameSession_IsAllowedAsync()
    {
        // Pipeline still allows different identities on one AgentSession (request-scoped header).
        // On a live hosted agent, Foundry binds previous_response_id chains to the creating user, so
        // prefer distinct AgentSessions per identity; sandbox id may still be shared.
        var seen = new List<string?>();
        var inner = new ProbeAgent(onRun: _ => seen.Add(UserIdentityScope.Current));
        var agent = new FoundryHostedRequestAgent(inner);
        var session = new TestSession();
        session.FoundryHostedAgentSessionId = "sess-shared";

        await agent.RunAsync(
            "hi",
            session,
            new ChatClientAgentRunOptions(new ChatOptions().WithFoundryHostedAgentUserIdentity("alice")));
        await agent.RunAsync(
            "hi",
            session,
            new ChatClientAgentRunOptions(new ChatOptions().WithFoundryHostedAgentUserIdentity("bob")));

        Assert.Equal(["alice", "bob"], seen);
        Assert.Equal("sess-shared", session.FoundryHostedAgentSessionId);
    }

    [Fact]
    public async Task UserIdentity_OmittedAfterParent_ClearsAsyncLocalScopeAsync()
    {
        var seen = new List<string?>();
        var inner = new ProbeAgent(onRun: _ => seen.Add(UserIdentityScope.Current));
        var agent = new FoundryHostedRequestAgent(inner);
        var session = new TestSession();

        await agent.RunAsync(
            "hi",
            session,
            new ChatClientAgentRunOptions(new ChatOptions().WithFoundryHostedAgentUserIdentity("alice")));
        await agent.RunAsync("hi", session, new ChatClientAgentRunOptions(new ChatOptions()));

        Assert.Equal(["alice", null], seen);
    }

    [Fact]
    public async Task PlainAgentRunOptions_PreservesBasePropertiesAsync()
    {
        AgentRunOptions? seen = null;
        var inner = new ProbeAgent(onRun: o => seen = o);
        var agent = new FoundryHostedRequestAgent(inner);
#pragma warning disable MEAI001
        var plain = new AgentRunOptions
        {
            AllowBackgroundResponses = true,
            ResponseFormat = ChatResponseFormat.Text,
        };
#pragma warning restore MEAI001

        await agent.RunAsync("hi", new TestSession(), plain);

        var cro = Assert.IsType<ChatClientAgentRunOptions>(seen);
        Assert.True(cro.AllowBackgroundResponses);
        Assert.Same(ChatResponseFormat.Text, cro.ResponseFormat);
    }

    [Fact]
    public async Task ReusedRunOptions_DoesNotStackRawRepresentationFactoriesAsync()
    {
        CreateResponseOptions? first = null;
        CreateResponseOptions? second = null;
        int run = 0;
        var inner = new ProbeAgent(onRun: options =>
        {
            if (options is not ChatClientAgentRunOptions { ChatOptions.RawRepresentationFactory: { } factory })
            {
                return;
            }

            var created = factory(null!) as CreateResponseOptions;
            if (run++ == 0)
            {
                first = created;
            }
            else
            {
                second = created;
            }
        });
        var agent = new FoundryHostedRequestAgent(inner);
        var session = new TestSession();
        session.FoundryHostedAgentSessionId = "sess-shared";
        var reused = new ChatClientAgentRunOptions(new ChatOptions());

        await agent.RunAsync("hi", session, reused);
        await agent.RunAsync("hi", session, reused);

        Assert.NotNull(first);
        Assert.NotNull(second);
        Assert.NotSame(first, second);
        Assert.Null(reused.ChatOptions!.RawRepresentationFactory);
    }

    [Fact]
    public async Task EndToEnd_UserIdentity_AndHostedSessionId_ReachWireAsync()
    {
        using var handler = new RecordingHandler(
            MinimalResponseJson(),
            responseHeaders: new Dictionary<string, string>
            {
                ["x-agent-session-id"] = "sess-from-platform",
            });
#pragma warning disable CA5399
        using var http = new HttpClient(handler);
#pragma warning restore CA5399
        var openAIOptions = new OpenAIClientOptions { Transport = new HttpClientPipelineTransport(http) };
        var openAIClient = new OpenAIClient(new ApiKeyCredential("fake"), openAIOptions);
        IChatClient chatClient = openAIClient.GetResponsesClient().AsIChatClient();

#pragma warning disable MEAI001
        var policies = chatClient.GetService<OpenAIRequestPolicies>();
        Assert.NotNull(policies);
        OpenAIRequestPoliciesReflection.AddPolicyIfMissing(policies!, ClientHeadersPolicy.Instance);
        OpenAIRequestPoliciesReflection.AddPolicyIfMissing(policies!, UserIdentityPolicy.Instance);
        OpenAIRequestPoliciesReflection.AddPolicyIfMissing(policies!, HostedSessionIdCapturePolicy.Instance);
#pragma warning restore MEAI001

        var chatAgent = new ChatClientAgent(chatClient);
        AIAgent agent = new FoundryHostedRequestAgent(new ClientHeadersAgent(chatAgent));
        AgentSession session = await chatAgent.CreateSessionAsync();
        session.FoundryHostedAgentSessionId = "sess-pinned";

        var runOptions = new ChatClientAgentRunOptions(
            new ChatOptions()
                .WithFoundryHostedAgentUserIdentity("alice")
                .WithClientHeader("x-client-end-user-id", "alice-app"));

        // Response returns a different hosted session id than the pin → unexpected switch.
        InvalidOperationException ex = await Assert.ThrowsAsync<InvalidOperationException>(
            () => agent.RunAsync("hi", session, runOptions));
        Assert.Contains("Unexpected Foundry hosted session switch", ex.Message, StringComparison.Ordinal);

        Assert.True(handler.Requests.Count > 0);
        var req = handler.Requests[0];
        Assert.Equal("alice", req.Headers[FoundryChatOptionsExtensions.FoundryHostedAgentUserIdentityHeaderName]);
        Assert.Equal("alice-app", req.Headers["x-client-end-user-id"]);
        Assert.Contains("\"agent_session_id\":\"sess-pinned\"", req.Body, StringComparison.Ordinal);
        // Sticky pin must not be overwritten by the conflicting response id.
        Assert.Equal("sess-pinned", session.FoundryHostedAgentSessionId);
    }

    [Fact]
    public async Task EndToEnd_PinnedHostedSessionId_MatchingResponseKeepsStickyAsync()
    {
        using var handler = new RecordingHandler(
            MinimalResponseJson(),
            responseHeaders: new Dictionary<string, string>
            {
                ["x-agent-session-id"] = "sess-pinned",
            });
#pragma warning disable CA5399
        using var http = new HttpClient(handler);
#pragma warning restore CA5399
        var openAIClient = new OpenAIClient(
            new ApiKeyCredential("fake"),
            new OpenAIClientOptions { Transport = new HttpClientPipelineTransport(http) });
        IChatClient chatClient = openAIClient.GetResponsesClient().AsIChatClient();

#pragma warning disable MEAI001
        var policies = chatClient.GetService<OpenAIRequestPolicies>()!;
        OpenAIRequestPoliciesReflection.AddPolicyIfMissing(policies, HostedSessionIdCapturePolicy.Instance);
#pragma warning restore MEAI001

        var chatAgent = new ChatClientAgent(chatClient);
        AIAgent agent = new FoundryHostedRequestAgent(chatAgent);
        AgentSession session = await chatAgent.CreateSessionAsync();
        session.FoundryHostedAgentSessionId = "sess-pinned";

        await agent.RunAsync("hi", session);

        Assert.Equal("sess-pinned", session.FoundryHostedAgentSessionId);
        Assert.Contains("\"agent_session_id\":\"sess-pinned\"", handler.Requests[0].Body, StringComparison.Ordinal);
    }

    [Fact]
    public async Task EndToEnd_ServiceManaged_CapturesHostedSessionIdOntoSessionAsync()
    {
        using var handler = new RecordingHandler(
            MinimalResponseJson(),
            responseHeaders: new Dictionary<string, string>
            {
                ["x-agent-session-id"] = "sess-created",
            });
#pragma warning disable CA5399
        using var http = new HttpClient(handler);
#pragma warning restore CA5399
        var openAIClient = new OpenAIClient(
            new ApiKeyCredential("fake"),
            new OpenAIClientOptions { Transport = new HttpClientPipelineTransport(http) });
        IChatClient chatClient = openAIClient.GetResponsesClient().AsIChatClient();

#pragma warning disable MEAI001
        var policies = chatClient.GetService<OpenAIRequestPolicies>()!;
        OpenAIRequestPoliciesReflection.AddPolicyIfMissing(policies, HostedSessionIdCapturePolicy.Instance);
#pragma warning restore MEAI001

        var chatAgent = new ChatClientAgent(chatClient);
        AIAgent agent = new FoundryHostedRequestAgent(chatAgent);
        AgentSession session = await chatAgent.CreateSessionAsync();

        await agent.RunAsync("hi", session);

        Assert.Equal("sess-created", session.FoundryHostedAgentSessionId);
        Assert.DoesNotContain("agent_session_id", handler.Requests[0].Body, StringComparison.Ordinal);
    }

    [Fact]
    public void Constructor_PreWiresFoundryHostedRequestAgent()
    {
        FoundryAgent agent = CreateFoundryAgent();
        Assert.NotNull(agent.GetService<FoundryHostedRequestAgent>());
        Assert.NotNull(agent.GetService<ClientHeadersAgent>());
    }

    private static FoundryAgent CreateFoundryAgent() =>
        new(
            new Uri("https://test.services.ai.azure.com/api/projects/test-project"),
            new FakeAuthenticationTokenProvider(),
            model: "gpt-4o-mini",
            instructions: "Test");

    private static string MinimalResponseJson() => """
        {
          "id":"resp_1","object":"response","created_at":1700000000,"status":"completed",
          "model":"fake","output":[],"usage":{"input_tokens":1,"output_tokens":1,"total_tokens":2}
        }
        """;

    private sealed class TestSession : AgentSession;

    private sealed class ProbeAgent : AIAgent
    {
        private readonly Action<AgentRunOptions?>? _onRun;

        public ProbeAgent(Action<AgentRunOptions?>? onRun = null)
        {
            this._onRun = onRun;
        }

        public int RunCount { get; private set; }

        protected override Task<AgentResponse> RunCoreAsync(
            IEnumerable<ChatMessage> messages,
            AgentSession? session = null,
            AgentRunOptions? options = null,
            CancellationToken cancellationToken = default)
        {
            this.RunCount++;
            this._onRun?.Invoke(options);
            return Task.FromResult(new AgentResponse());
        }

        protected override async IAsyncEnumerable<AgentResponseUpdate> RunCoreStreamingAsync(
            IEnumerable<ChatMessage> messages,
            AgentSession? session = null,
            AgentRunOptions? options = null,
            [System.Runtime.CompilerServices.EnumeratorCancellation] CancellationToken cancellationToken = default)
        {
            this.RunCount++;
            this._onRun?.Invoke(options);
            await Task.Yield();
            yield break;
        }

        protected override ValueTask<AgentSession> CreateSessionCoreAsync(CancellationToken cancellationToken = default) =>
            new(new TestSession());

        protected override ValueTask<JsonElement> SerializeSessionCoreAsync(
            AgentSession session,
            JsonSerializerOptions? jsonSerializerOptions,
            CancellationToken cancellationToken = default) =>
            new(JsonDocument.Parse("{}").RootElement);

        protected override ValueTask<AgentSession> DeserializeSessionCoreAsync(
            JsonElement serializedState,
            JsonSerializerOptions? jsonSerializerOptions,
            CancellationToken cancellationToken = default) =>
            new(new TestSession());
    }

    private sealed class RecordingHandler : HttpClientHandler
    {
        private readonly string _body;
        private readonly Dictionary<string, string> _responseHeaders;

        public RecordingHandler(string body, Dictionary<string, string>? responseHeaders = null)
        {
            this._body = body;
            this._responseHeaders = responseHeaders ?? new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
        }

        public List<RecordedRequest> Requests { get; } = [];

        protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
        {
            var headers = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
            foreach (var h in request.Headers)
            {
                headers[h.Key] = string.Join(",", h.Value);
            }

            string body;
            if (request.Content is null)
            {
                body = string.Empty;
            }
            else
            {
#if NET
                body = await request.Content.ReadAsStringAsync(cancellationToken).ConfigureAwait(false);
#else
                body = await request.Content.ReadAsStringAsync().ConfigureAwait(false);
#endif
            }

            this.Requests.Add(new RecordedRequest(headers, body));

            var resp = new HttpResponseMessage(HttpStatusCode.OK)
            {
                Content = new StringContent(this._body, Encoding.UTF8, "application/json"),
                RequestMessage = request,
            };
            foreach (var kvp in this._responseHeaders)
            {
                resp.Headers.TryAddWithoutValidation(kvp.Key, kvp.Value);
            }

            return resp;
        }
    }

    private sealed class RecordedRequest(Dictionary<string, string> headers, string body)
    {
        public Dictionary<string, string> Headers { get; } = headers;
        public string Body { get; } = body;
    }
}
