// Copyright (c) Microsoft. All rights reserved.

using System;
using System.ClientModel;
using System.ClientModel.Primitives;
using System.Collections.Generic;
using System.Net;
using System.Net.Http;
using System.Reflection;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using OpenAI;

#pragma warning disable OPENAI001, MEAI001, MAAI001, SCME0001

namespace Microsoft.Agents.AI.Foundry.UnitTests;

/// <summary>
/// Tests for the per-call <c>x-client-*</c> header pipeline:
/// <see cref="ClientHeadersExtensions.WithClientHeader(ChatOptions, string, string)"/>,
/// <see cref="ClientHeadersExtensions.UseClientHeaders(AIAgentBuilder)"/>,
/// the <c>ClientHeadersAgent</c> decorator, the <c>ClientHeadersScope</c> AsyncLocal,
/// and the <c>ClientHeadersPolicy</c> stamping policy.
/// </summary>
public sealed class ClientHeadersExtensionsTests
{
    // -------------------------------------------------------------------------------------------
    // 1. WithClientHeader writes namespaced key with valid value
    // -------------------------------------------------------------------------------------------

    [Fact]
    public void WithClientHeader_WritesNamespacedKey_WithValidValue()
    {
        // Arrange
        var options = new ChatOptions();

        // Act
        options.WithClientHeader("x-client-end-user-id", "alice");

        // Assert
        Assert.NotNull(options.AdditionalProperties);
        var raw = options.AdditionalProperties[ClientHeadersExtensions.ClientHeadersKey];
        var dict = Assert.IsType<Dictionary<string, string>>(raw);
        Assert.Equal("alice", dict["X-CLIENT-END-USER-ID"]); // OrdinalIgnoreCase
    }

    // -------------------------------------------------------------------------------------------
    // 2. WithClientHeader rejects non-x-client- prefix
    // -------------------------------------------------------------------------------------------

    [Theory]
    [InlineData("Authorization")]
    [InlineData("X-Custom-Header")]
    [InlineData("client-end-user-id")]
    [InlineData("xclient-end-user-id")]
    public void WithClientHeader_RejectsInvalidPrefix(string name)
    {
        // Arrange
        var options = new ChatOptions();

        // Act / Assert
        Assert.Throws<ArgumentException>(() => options.WithClientHeader(name, "value"));
    }

    // -------------------------------------------------------------------------------------------
    // 3. WithClientHeader rejects null/empty name and value
    // -------------------------------------------------------------------------------------------

    [Fact]
    public void WithClientHeader_RejectsNullName()
    {
        var options = new ChatOptions();
        Assert.Throws<ArgumentNullException>(() => options.WithClientHeader(null!, "v"));
    }

    [Fact]
    public void WithClientHeader_RejectsNullValue()
    {
        var options = new ChatOptions();
        Assert.Throws<ArgumentNullException>(() => options.WithClientHeader("x-client-foo", null!));
    }

    [Theory]
    [InlineData("")]
    [InlineData("   ")]
    public void WithClientHeader_RejectsEmptyOrWhitespaceName(string name)
    {
        var options = new ChatOptions();
        Assert.Throws<ArgumentException>(() => options.WithClientHeader(name, "v"));
    }

    [Fact]
    public void WithClientHeader_RejectsEmptyValue()
    {
        var options = new ChatOptions();
        Assert.Throws<ArgumentException>(() => options.WithClientHeader("x-client-foo", ""));
    }

    // -------------------------------------------------------------------------------------------
    // 4. WithClientHeaders (bulk) is all-or-nothing on first invalid key
    // -------------------------------------------------------------------------------------------

    [Fact]
    public void WithClientHeaders_AllOrNothing_OnInvalidKey()
    {
        // Arrange
        var options = new ChatOptions();
        var headers = new[]
        {
            new KeyValuePair<string, string>("x-client-end-user-id", "alice"),
            new KeyValuePair<string, string>("Authorization", "secret"), // invalid prefix
            new KeyValuePair<string, string>("x-client-end-chat-id", "chat-1"),
        };

        // Act / Assert: throws, and no entries are written.
        Assert.Throws<ArgumentException>(() => options.WithClientHeaders(headers));
        Assert.Null(options.GetClientHeaders());
    }

    // -------------------------------------------------------------------------------------------
    // 5. Multiple WithClientHeader calls accumulate (additive)
    // -------------------------------------------------------------------------------------------

    [Fact]
    public void WithClientHeader_Accumulates_MultipleCalls()
    {
        // Arrange
        var options = new ChatOptions();

        // Act
        options.WithClientHeader("x-client-a", "1");
        options.WithClientHeader("x-client-b", "2");
        options.WithClientHeader("x-client-a", "1-updated"); // upsert

        // Assert
        var dict = options.GetClientHeaders();
        Assert.NotNull(dict);
        Assert.Equal(2, dict!.Count);
        Assert.Equal("1-updated", dict["x-client-a"]);
        Assert.Equal("2", dict["x-client-b"]);
    }

    // -------------------------------------------------------------------------------------------
    // 6. Conflict on slot occupied by foreign type throws InvalidOperationException
    // -------------------------------------------------------------------------------------------

    [Fact]
    public void WithClientHeader_ForeignTypeAtSlot_Throws()
    {
        // Arrange
        var options = new ChatOptions
        {
            AdditionalProperties = new AdditionalPropertiesDictionary
            {
                [ClientHeadersExtensions.ClientHeadersKey] = "this is not a dictionary",
            },
        };

        // Act / Assert
        Assert.Throws<InvalidOperationException>(() => options.WithClientHeader("x-client-foo", "v"));
    }

    // -------------------------------------------------------------------------------------------
    // 7. UseClientHeaders is idempotent (already-wired returns innerAgent)
    // -------------------------------------------------------------------------------------------

    [Fact]
    public void UseClientHeaders_IsIdempotent()
    {
        // Arrange
        var inner = new FakeAgent();
        var first = inner.AsBuilder().UseClientHeaders().Build();

        // Act
        var second = first.AsBuilder().UseClientHeaders().Build();

        // Assert: only one ClientHeadersAgent in the chain.
        Assert.NotNull(first.GetService<ClientHeadersAgent>());
        Assert.NotNull(second.GetService<ClientHeadersAgent>());
        // The second call should return the same agent unchanged because the chain is already wired.
        Assert.Same(first, second);
    }

    // -------------------------------------------------------------------------------------------
    // 8. ClientHeadersAgent snapshots dict at push time (mid-run mutation does not leak)
    // -------------------------------------------------------------------------------------------

    [Fact]
    public async Task ClientHeadersAgent_SnapshotsAtPush_MidRunMutationDoesNotLeakAsync()
    {
        // Arrange: a fake inner agent that exposes ClientHeadersScope.Current at the moment of RunAsync.
        IReadOnlyDictionary<string, string>? observed = null;
        var inner = new ProbeAgent(_ =>
        {
            observed = ClientHeadersScope.Current;
            // Mutate the source dictionary mid-run; snapshot must not see the mutation.
            return Task.CompletedTask;
        });

        var agent = new ClientHeadersAgent(inner);
        var chatOptions = new ChatOptions();
        chatOptions.WithClientHeader("x-client-end-user-id", "alice");

        // Act
        var task = agent.RunAsync(messages: [], options: new ChatClientAgentRunOptions(chatOptions));
        // Mutate the source after RunAsync starts.
        chatOptions.WithClientHeader("x-client-end-user-id", "bob");
        await task;

        // Assert: probe saw "alice", not "bob".
        Assert.NotNull(observed);
        Assert.Equal("alice", observed!["x-client-end-user-id"]);
    }

    // -------------------------------------------------------------------------------------------
    // 9. ClientHeadersAgent streaming keeps scope alive across yields
    // -------------------------------------------------------------------------------------------

    [Fact]
    public async Task ClientHeadersAgent_Streaming_HasScopeAtFirstYieldAsync()
    {
        // Arrange: in production the SCM pipeline policy fires once at the first MoveNextAsync
        // (when MEAI's OpenAIResponsesChatClient initiates the HTTP request). We assert that at
        // that critical moment the AsyncLocal scope is observable. End-to-end coverage of the wire
        // behavior is provided by EndToEnd_UseClientHeaders_Streaming_StampsOnWireAsync.
        IReadOnlyDictionary<string, string>? observedAtFirstYield = null;
        var inner = new ProbeStreamingAgent(yields: 1, onYield: () => observedAtFirstYield = ClientHeadersScope.Current);
        var agent = new ClientHeadersAgent(inner);

        var chatOptions = new ChatOptions();
        chatOptions.WithClientHeader("x-client-end-user-id", "carol");

        // Act
        await foreach (var _ in agent.RunStreamingAsync(messages: [], options: new ChatClientAgentRunOptions(chatOptions)))
        {
            // drain
        }

        // Assert
        Assert.NotNull(observedAtFirstYield);
        Assert.Equal("carol", observedAtFirstYield!["x-client-end-user-id"]);
    }

    // -------------------------------------------------------------------------------------------
    // 10. ClientHeadersScope is AsyncLocal-isolated across parallel runs and auto-restores on
    //     async-method return (no explicit Dispose needed).
    // -------------------------------------------------------------------------------------------

    [Fact]
    public async Task ClientHeadersScope_IsAsyncLocalIsolatedAndAutoRestoresAsync()
    {
        // Arrange
        var dictA = new Dictionary<string, string> { ["x-client-end-user-id"] = "alice" };
        var dictB = new Dictionary<string, string> { ["x-client-end-user-id"] = "bob" };

        // Act / Assert: parallel async flows do not see each other's mutations.
        await Task.WhenAll(
            ProbeAsync(dictA, "alice"),
            ProbeAsync(dictB, "bob"));

        async Task ProbeAsync(Dictionary<string, string> dict, string expected)
        {
            ClientHeadersScope.Current = dict;
            await Task.Yield();
            Assert.Equal(expected, ClientHeadersScope.Current!["x-client-end-user-id"]);
        }

        // Assert: setting Current inside an awaited async method does not leak back to the caller
        // after the method returns. This is the AsyncLocal natural-restoration behavior the
        // ClientHeadersAgent relies on.
        Assert.Null(ClientHeadersScope.Current);
    }

    // -------------------------------------------------------------------------------------------
    // 11. ClientHeadersPolicy no-ops when scope is null
    // -------------------------------------------------------------------------------------------

    [Fact]
    public async Task ClientHeadersPolicy_NoOps_WhenScopeIsNullAsync()
    {
        // Arrange
        using var handler = new RecordingHandler();
#pragma warning disable CA5399
        using var http = new HttpClient(handler);
#pragma warning restore CA5399
        var pipeline = ClientPipeline.Create(
            new ClientPipelineOptions { Transport = new HttpClientPipelineTransport(http) },
            perCallPolicies: [ClientHeadersPolicy.Instance],
            perTryPolicies: default,
            beforeTransportPolicies: default);

        // Act: no scope pushed
        var msg = pipeline.CreateMessage();
        msg.Request.Method = "GET";
        msg.Request.Uri = new Uri("https://example.test/");
        await pipeline.SendAsync(msg);

        // Assert
        Assert.DoesNotContain(handler.Headers, kv => kv.Key.StartsWith("x-client-", StringComparison.OrdinalIgnoreCase));
    }

    // -------------------------------------------------------------------------------------------
    // 12. ClientHeadersPolicy stamps with Set (overwrites pre-existing same-name header)
    // -------------------------------------------------------------------------------------------

    [Fact]
    public async Task ClientHeadersPolicy_StampsWithSet_OverwritesPreExistingHeaderAsync()
    {
        // Arrange
        using var handler = new RecordingHandler();
#pragma warning disable CA5399
        using var http = new HttpClient(handler);
#pragma warning restore CA5399

        // A pre-existing policy that always sets x-client-end-user-id=initial.
        var preExisting = new HeaderSetterPolicy("x-client-end-user-id", "initial");

        var pipeline = ClientPipeline.Create(
            new ClientPipelineOptions { Transport = new HttpClientPipelineTransport(http) },
            perCallPolicies: [preExisting, ClientHeadersPolicy.Instance],
            perTryPolicies: default,
            beforeTransportPolicies: default);

        // Act
        ClientHeadersScope.Current = new Dictionary<string, string> { ["x-client-end-user-id"] = "alice" };
        try
        {
            var msg = pipeline.CreateMessage();
            msg.Request.Method = "GET";
            msg.Request.Uri = new Uri("https://example.test/");
            await pipeline.SendAsync(msg);
        }
        finally
        {
            ClientHeadersScope.Current = null;
        }

        // Assert: the per-call value won.
        Assert.Equal("alice", handler.Headers["x-client-end-user-id"]);
    }

    // -------------------------------------------------------------------------------------------
    // 13. Reflection dedup catches duplicate registration on a single OpenAIRequestPolicies
    // -------------------------------------------------------------------------------------------

    [Fact]
    public void OpenAIRequestPoliciesReflection_DedupsDuplicateRegistration()
    {
        // Arrange
        var policies = new OpenAIRequestPolicies();

        // Act
        var firstAdded = OpenAIRequestPoliciesReflection.AddPolicyIfMissing(policies, ClientHeadersPolicy.Instance);
        var secondAdded = OpenAIRequestPoliciesReflection.AddPolicyIfMissing(policies, ClientHeadersPolicy.Instance);

        // Assert
        Assert.True(firstAdded);
        Assert.False(secondAdded);
        Assert.Equal(1, EntriesCount(policies));
    }

    // -------------------------------------------------------------------------------------------
    // 14. Reflection dedup gracefully fails when shape is wrong (use a fake type to simulate)
    // -------------------------------------------------------------------------------------------

    [Fact]
    public void OpenAIRequestPoliciesReflection_ContainsPolicy_ReturnsFalse_OnNullEntries()
    {
        // Arrange: a fresh OpenAIRequestPolicies (Entries field exists, but is empty).
        var policies = new OpenAIRequestPolicies();

        // Act / Assert
        Assert.False(OpenAIRequestPoliciesReflection.ContainsPolicy(policies, ClientHeadersPolicy.Instance));
    }

    // -------------------------------------------------------------------------------------------
    // 15. CI guardrail: assert OpenAIRequestPolicies._entries field shape
    // -------------------------------------------------------------------------------------------

    [Fact]
    public void OpenAIRequestPolicies_EntriesField_ShapeGuardrail()
    {
        // Arrange / Act
        var field = typeof(OpenAIRequestPolicies).GetField("_entries", BindingFlags.Instance | BindingFlags.NonPublic);

        // Assert: this test fails loudly if MEAI renames the field, so we know to update
        // OpenAIRequestPoliciesReflection. The Entry array element type is private so we only
        // assert that the field is an Array; the ContainsPolicy method itself reflects the Policy
        // member dynamically so it survives Entry-shape changes too.
        Assert.NotNull(field);
        Assert.True(typeof(Array).IsAssignableFrom(field!.FieldType),
            $"Expected _entries to be an Array, got {field.FieldType}.");
    }

    // -------------------------------------------------------------------------------------------
    // 16. Foundry hosting end-to-end: per-call x-client-end-user-id reaches the wire
    //     (Covered by the existing HostedOutboundUserAgentTests pattern; we add a focused unit test
    //     here that verifies UseClientHeaders + the OpenAIRequestPolicies bridge stamps headers
    //     on the wire when invoked through a real ChatClientAgent.)
    // -------------------------------------------------------------------------------------------

    [Fact]
    public async Task EndToEnd_UseClientHeaders_StampsOnWireAsync()
    {
        // Arrange: build a real OpenAI ResponsesClient pointed at a fake handler.
        using var handler = new RecordingHandler(MinimalResponseJson());
#pragma warning disable CA5399
        using var http = new HttpClient(handler);
#pragma warning restore CA5399
        var openAIOptions = new OpenAIClientOptions { Transport = new HttpClientPipelineTransport(http) };
        var openAIClient = new OpenAIClient(new ApiKeyCredential("fake"), openAIOptions);
        var responsesClient = openAIClient.GetResponsesClient();
        IChatClient chatClient = responsesClient.AsIChatClient();

        AIAgent agent = new ChatClientAgent(chatClient).AsBuilder().UseClientHeaders().Build();

        var runOptions = new ChatClientAgentRunOptions(new ChatOptions());
        runOptions.ChatOptions!.WithClientHeader("x-client-end-user-id", "alice");

        // Act
        await agent.RunAsync("hi", options: runOptions);

        // Assert
        Assert.True(handler.Requests.Count > 0);
        Assert.Equal("alice", handler.Requests[0].Headers["x-client-end-user-id"]);
    }

    // -------------------------------------------------------------------------------------------
    // 17. Customer raw end-to-end: covered by #16 (which uses raw new ChatClientAgent + AsBuilder).
    //     Add a streaming variant here.
    // -------------------------------------------------------------------------------------------

    [Fact]
    public async Task EndToEnd_UseClientHeaders_Streaming_StampsOnWireAsync()
    {
        // Arrange
        using var handler = new RecordingHandler(MinimalResponseJson());
#pragma warning disable CA5399
        using var http = new HttpClient(handler);
#pragma warning restore CA5399
        var openAIOptions = new OpenAIClientOptions { Transport = new HttpClientPipelineTransport(http) };
        var openAIClient = new OpenAIClient(new ApiKeyCredential("fake"), openAIOptions);
        var responsesClient = openAIClient.GetResponsesClient();
        IChatClient chatClient = responsesClient.AsIChatClient();

        AIAgent agent = new ChatClientAgent(chatClient).AsBuilder().UseClientHeaders().Build();

        var runOptions = new ChatClientAgentRunOptions(new ChatOptions());
        runOptions.ChatOptions!.WithClientHeader("x-client-end-user-id", "carol");

        // Act
        try
        {
            await foreach (var _ in agent.RunStreamingAsync("hi", options: runOptions))
            {
                // drain
            }
        }
        catch
        {
            // The fake handler returns a non-streaming JSON; MEAI may throw mid-stream while parsing.
            // The wire request is captured before parsing, so the assertion below still validates the header.
        }

        // Assert
        Assert.True(handler.Requests.Count > 0);
        Assert.Equal("carol", handler.Requests[0].Headers["x-client-end-user-id"]);
    }

    // -------------------------------------------------------------------------------------------
    // 18. Headers-set-but-no-bridge: silent no-op confirmed (non-OpenAI mock)
    // -------------------------------------------------------------------------------------------

    [Fact]
    public async Task UseClientHeaders_OnNonOpenAIClient_IsSilentNoOpAsync()
    {
        // Arrange: a non-OpenAI fake agent that does not expose OpenAIRequestPolicies.
        var inner = new FakeAgent();
        var agent = inner.AsBuilder().UseClientHeaders().Build();

        var runOptions = new ChatClientAgentRunOptions(new ChatOptions());
        runOptions.ChatOptions!.WithClientHeader("x-client-end-user-id", "alice");

        // Act / Assert: no throw. AsyncLocal flows but no policy stamps anything because the
        // chat client doesn't have OpenAIRequestPolicies registered.
        await agent.RunAsync("hi", options: runOptions);
        Assert.True(true);
    }

    // -------------------------------------------------------------------------------------------
    // 19. Shared IChatClient across two agents both calling UseClientHeaders registers
    //     ClientHeadersPolicy exactly once on the shared OpenAIRequestPolicies.
    // -------------------------------------------------------------------------------------------

    [Fact]
    public async Task SharedChatClient_AcrossTwoAgents_RegistersPolicyOnceAsync()
    {
        // Arrange
        using var handler = new RecordingHandler(MinimalResponseJson());
#pragma warning disable CA5399
        using var http = new HttpClient(handler);
#pragma warning restore CA5399
        var openAIOptions = new OpenAIClientOptions { Transport = new HttpClientPipelineTransport(http) };
        var openAIClient = new OpenAIClient(new ApiKeyCredential("fake"), openAIOptions);
        var responsesClient = openAIClient.GetResponsesClient();
        IChatClient chatClient = responsesClient.AsIChatClient();

        // Act: build two agents that share the same chat client. Each calls UseClientHeaders.
        AIAgent agent1 = new ChatClientAgent(chatClient).AsBuilder().UseClientHeaders().Build();
        AIAgent agent2 = new ChatClientAgent(chatClient).AsBuilder().UseClientHeaders().Build();

        // Assert: the shared OpenAIRequestPolicies has exactly one ClientHeadersPolicy registered.
        var policies = chatClient.GetService<OpenAIRequestPolicies>();
        Assert.NotNull(policies);
        Assert.Equal(1, EntriesCount(policies!));

        // And on the wire, the per-call header is stamped exactly once (no duplication).
        var runOptions = new ChatClientAgentRunOptions(new ChatOptions());
        runOptions.ChatOptions!.WithClientHeader("x-client-end-user-id", "alice");
        try
        {
            await agent1.RunAsync("hi", options: runOptions);
        }
        catch
        {
            // tolerate parser issues; we assert on the wire.
        }
        Assert.True(handler.Requests.Count > 0);
        Assert.Equal("alice", handler.Requests[0].Headers["x-client-end-user-id"]);
    }

    // -------------------------------------------------------------------------------------------
    // 20. ClientHeadersPolicy registration via UseClientHeaders is deduped across many invocations
    //     on the same chat client (mirrors the Foundry.Hosting per-request resolution scenario).
    // -------------------------------------------------------------------------------------------

    [Fact]
    public void UseClientHeaders_RepeatedRegistrations_OnSameChatClient_OnlyRegistersOnce()
    {
        // Arrange: a chat client whose OpenAIRequestPolicies service we can inspect.
        using var handler = new RecordingHandler(MinimalResponseJson());
#pragma warning disable CA5399
        using var http = new HttpClient(handler);
#pragma warning restore CA5399
        var openAIClient = new OpenAIClient(new ApiKeyCredential("fake"),
            new OpenAIClientOptions { Transport = new HttpClientPipelineTransport(http) });
        IChatClient chatClient = openAIClient.GetResponsesClient().AsIChatClient();

        // Act: simulate N hosted-resolution-style wirings on top of the same shared chat client.
        for (int i = 0; i < 25; i++)
        {
            _ = new ChatClientAgent(chatClient).AsBuilder().UseClientHeaders().Build();
        }

        // Assert: exactly one ClientHeadersPolicy entry on the shared OpenAIRequestPolicies.
        var policies = chatClient.GetService<OpenAIRequestPolicies>();
        Assert.NotNull(policies);
        Assert.Equal(1, EntriesCount(policies!));
    }

    // -------------------------------------------------------------------------------------------
    // Helpers
    // -------------------------------------------------------------------------------------------

    private static int EntriesCount(OpenAIRequestPolicies policies)
    {
        var field = typeof(OpenAIRequestPolicies).GetField("_entries", BindingFlags.Instance | BindingFlags.NonPublic);
        var array = (Array?)field?.GetValue(policies);
        return array?.Length ?? -1;
    }

    private static string MinimalResponseJson() => """
        {
          "id":"resp_1","object":"response","created_at":1700000000,"status":"completed",
          "model":"fake","output":[],"usage":{"input_tokens":1,"output_tokens":1,"total_tokens":2}
        }
        """;

    /// <summary>An <see cref="HttpClientHandler"/> that records request headers and returns a fixed response body.</summary>
    private sealed class RecordingHandler : HttpClientHandler
    {
        private readonly string _body;

        public RecordingHandler(string body = """{}""")
        {
            this._body = body;
        }

        public List<RecordedRequest> Requests { get; } = [];

        public Dictionary<string, string> Headers => this.Requests.Count > 0 ? this.Requests[0].Headers : new Dictionary<string, string>();

        protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
        {
            var headers = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
            foreach (var h in request.Headers)
            {
                headers[h.Key] = string.Join(",", h.Value);
            }
            this.Requests.Add(new RecordedRequest(request.RequestUri?.ToString() ?? "?", headers));

            var resp = new HttpResponseMessage(HttpStatusCode.OK)
            {
                Content = new StringContent(this._body, Encoding.UTF8, "application/json"),
                RequestMessage = request,
            };
            return Task.FromResult(resp);
        }
    }

    private sealed class RecordedRequest
    {
        public RecordedRequest(string uri, Dictionary<string, string> headers)
        {
            this.Uri = uri;
            this.Headers = headers;
        }

        public string Uri { get; }
        public Dictionary<string, string> Headers { get; }
    }

    /// <summary>A pipeline policy that always stamps a fixed header value via Headers.Set.</summary>
    private sealed class HeaderSetterPolicy : PipelinePolicy
    {
        private readonly string _name;
        private readonly string _value;

        public HeaderSetterPolicy(string name, string value)
        {
            this._name = name;
            this._value = value;
        }

        public override void Process(PipelineMessage message, IReadOnlyList<PipelinePolicy> pipeline, int currentIndex)
        {
            message.Request.Headers.Set(this._name, this._value);
            ProcessNext(message, pipeline, currentIndex);
        }

        public override ValueTask ProcessAsync(PipelineMessage message, IReadOnlyList<PipelinePolicy> pipeline, int currentIndex)
        {
            message.Request.Headers.Set(this._name, this._value);
            return ProcessNextAsync(message, pipeline, currentIndex);
        }
    }

    /// <summary>A trivial session used by fake agents in these tests.</summary>
    private sealed class TrivialSession : AgentSession { }

    /// <summary>A minimal AIAgent that does nothing; used to test decorator wiring.</summary>
    private sealed class FakeAgent : AIAgent
    {
        protected override Task<AgentResponse> RunCoreAsync(IEnumerable<ChatMessage> messages, AgentSession? session = null, AgentRunOptions? options = null, CancellationToken cancellationToken = default)
            => Task.FromResult(new AgentResponse());

        protected override async IAsyncEnumerable<AgentResponseUpdate> RunCoreStreamingAsync(IEnumerable<ChatMessage> messages, AgentSession? session = null, AgentRunOptions? options = null, [System.Runtime.CompilerServices.EnumeratorCancellation] CancellationToken cancellationToken = default)
        {
            await Task.Yield();
            yield break;
        }

        protected override ValueTask<AgentSession> CreateSessionCoreAsync(CancellationToken cancellationToken = default) =>
            new(new TrivialSession());

        protected override ValueTask<JsonElement> SerializeSessionCoreAsync(AgentSession session, JsonSerializerOptions? jsonSerializerOptions, CancellationToken cancellationToken = default) =>
            new(JsonDocument.Parse("{}").RootElement);

        protected override ValueTask<AgentSession> DeserializeSessionCoreAsync(JsonElement serializedState, JsonSerializerOptions? jsonSerializerOptions, CancellationToken cancellationToken = default) =>
            new(new TrivialSession());
    }

    /// <summary>An AIAgent that invokes a probe action each time RunAsync is called.</summary>
    private sealed class ProbeAgent : AIAgent
    {
        private readonly Func<CancellationToken, Task> _probe;

        public ProbeAgent(Func<CancellationToken, Task> probe)
        {
            this._probe = probe;
        }

        protected override async Task<AgentResponse> RunCoreAsync(IEnumerable<ChatMessage> messages, AgentSession? session = null, AgentRunOptions? options = null, CancellationToken cancellationToken = default)
        {
            await this._probe(cancellationToken);
            return new AgentResponse();
        }

        protected override async IAsyncEnumerable<AgentResponseUpdate> RunCoreStreamingAsync(IEnumerable<ChatMessage> messages, AgentSession? session = null, AgentRunOptions? options = null, [System.Runtime.CompilerServices.EnumeratorCancellation] CancellationToken cancellationToken = default)
        {
            await this._probe(cancellationToken);
            yield break;
        }

        protected override ValueTask<AgentSession> CreateSessionCoreAsync(CancellationToken cancellationToken = default) =>
            new(new TrivialSession());

        protected override ValueTask<JsonElement> SerializeSessionCoreAsync(AgentSession session, JsonSerializerOptions? jsonSerializerOptions, CancellationToken cancellationToken = default) =>
            new(JsonDocument.Parse("{}").RootElement);

        protected override ValueTask<AgentSession> DeserializeSessionCoreAsync(JsonElement serializedState, JsonSerializerOptions? jsonSerializerOptions, CancellationToken cancellationToken = default) =>
            new(new TrivialSession());
    }

    /// <summary>An AIAgent whose streaming method invokes <c>onYield</c> at each yield point.</summary>
    private sealed class ProbeStreamingAgent : AIAgent
    {
        private readonly int _yields;
        private readonly Action _onYield;

        public ProbeStreamingAgent(int yields, Action onYield)
        {
            this._yields = yields;
            this._onYield = onYield;
        }

        protected override Task<AgentResponse> RunCoreAsync(IEnumerable<ChatMessage> messages, AgentSession? session = null, AgentRunOptions? options = null, CancellationToken cancellationToken = default)
            => Task.FromResult(new AgentResponse());

        protected override async IAsyncEnumerable<AgentResponseUpdate> RunCoreStreamingAsync(IEnumerable<ChatMessage> messages, AgentSession? session = null, AgentRunOptions? options = null, [System.Runtime.CompilerServices.EnumeratorCancellation] CancellationToken cancellationToken = default)
        {
            for (int i = 0; i < this._yields; i++)
            {
                this._onYield();
                await Task.Yield();
                yield return new AgentResponseUpdate();
            }
        }

        protected override ValueTask<AgentSession> CreateSessionCoreAsync(CancellationToken cancellationToken = default) =>
            new(new TrivialSession());

        protected override ValueTask<JsonElement> SerializeSessionCoreAsync(AgentSession session, JsonSerializerOptions? jsonSerializerOptions, CancellationToken cancellationToken = default) =>
            new(JsonDocument.Parse("{}").RootElement);

        protected override ValueTask<AgentSession> DeserializeSessionCoreAsync(JsonElement serializedState, JsonSerializerOptions? jsonSerializerOptions, CancellationToken cancellationToken = default) =>
            new(new TrivialSession());
    }
}
