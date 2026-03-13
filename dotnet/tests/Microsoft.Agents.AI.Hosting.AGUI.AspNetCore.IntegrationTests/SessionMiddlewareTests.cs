// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using System.Linq;
using System.Net.Http;
using System.Runtime.CompilerServices;
using System.Text.Json;
using System.Text.Json.Serialization;
using System.Threading;
using System.Threading.Tasks;
using FluentAssertions;
using Microsoft.Agents.AI.AGUI;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Hosting.Server;
using Microsoft.AspNetCore.TestHost;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.DependencyInjection;

namespace Microsoft.Agents.AI.Hosting.AGUI.AspNetCore.IntegrationTests;

/// <summary>
/// Integration tests that verify session propagation through the AGUI middleware pipeline.
/// Regression tests for <see href="https://github.com/microsoft/agent-framework/issues/3823">#3823</see>:
/// "Session is always null in the middleware".
/// </summary>
public sealed class SessionMiddlewareTests : IAsyncDisposable
{
    private WebApplication? _app;
    private HttpClient? _client;

    /// <summary>
    /// Verifies that when a workflow is configured with middleware via <c>AIAgentBuilder.Use</c>,
    /// the session parameter passed to the middleware during an AGUI-initiated run is not null.
    /// </summary>
    /// <remarks>
    /// Regression test for #3823. The bug was that <c>MapAGUI</c> called
    /// <c>RunStreamingAsync(messages, options: runOptions, ...)</c>, skipping the <c>session</c> parameter
    /// entirely, which caused it to be <c>null</c> for all middleware decorators.
    /// </remarks>
    [Fact]
    public async Task AGUIMiddleware_WithWorkflow_SessionIsNotNullAsync()
    {
        // Arrange
        AgentSession? capturedSession = null;
        var innerAgent = new FakeSessionCapturingAgent();

        // Wrap the agent with middleware that captures the session parameter
        AIAgent agentWithMiddleware = new AIAgentBuilder(innerAgent)
            .Use(
                runFunc: null,
                runStreamingFunc: (messages, session, options, innerAgent, ct) =>
                {
                    // Capture session in middleware — this is what #3823 tests
                    capturedSession = session;
                    return innerAgent.RunStreamingAsync(messages, session, options, ct);
                })
            .Build();

        await this.SetupTestServerAsync(agentWithMiddleware);
        var chatClient = new AGUIChatClient(this._client!, "", null);
        AIAgent clientAgent = chatClient.AsAIAgent(instructions: null, name: "assistant", description: "Session test assistant", tools: []);
        ChatClientAgentSession clientSession = (ChatClientAgentSession)await clientAgent.CreateSessionAsync();
        ChatMessage userMessage = new(ChatRole.User, "hello");

        List<AgentResponseUpdate> updates = [];

        // Act — run through the AGUI endpoint (full round-trip: AGUIChatClient → HTTP → MapAGUI → middleware → agent)
        await foreach (AgentResponseUpdate update in clientAgent.RunStreamingAsync([userMessage], clientSession, new AgentRunOptions(), CancellationToken.None))
        {
            updates.Add(update);
        }

        // Assert
        updates.Should().NotBeEmpty("the agent should have produced streaming updates");
        capturedSession.Should().NotBeNull("session should be propagated to middleware when invoked via AGUI endpoint (regression #3823)");
    }

    /// <summary>
    /// Verifies that the session is also available via <see cref="AIAgent.CurrentRunContext"/>
    /// when the agent is invoked through the AGUI endpoint.
    /// </summary>
    [Fact]
    public async Task AGUIMiddleware_CurrentRunContext_SessionIsNotNullAsync()
    {
        // Arrange
        AgentRunContext? capturedRunContext = null;
        var innerAgent = new FakeSessionCapturingAgent();

        // Wrap the agent with middleware that captures CurrentRunContext
        AIAgent agentWithMiddleware = new AIAgentBuilder(innerAgent)
            .Use(
                runFunc: null,
                runStreamingFunc: (messages, session, options, innerAgent, ct) =>
                {
                    // Capture the run context — its Session should not be null
                    capturedRunContext = AIAgent.CurrentRunContext;
                    return innerAgent.RunStreamingAsync(messages, session, options, ct);
                })
            .Build();

        await this.SetupTestServerAsync(agentWithMiddleware);
        var chatClient = new AGUIChatClient(this._client!, "", null);
        AIAgent clientAgent = chatClient.AsAIAgent(instructions: null, name: "assistant", description: "Context test assistant", tools: []);
        ChatClientAgentSession clientSession = (ChatClientAgentSession)await clientAgent.CreateSessionAsync();
        ChatMessage userMessage = new(ChatRole.User, "test context");

        List<AgentResponseUpdate> updates = [];

        // Act
        await foreach (AgentResponseUpdate update in clientAgent.RunStreamingAsync([userMessage], clientSession, new AgentRunOptions(), CancellationToken.None))
        {
            updates.Add(update);
        }

        // Assert
        updates.Should().NotBeEmpty();
        capturedRunContext.Should().NotBeNull("CurrentRunContext should be set during AGUI-initiated runs");
        capturedRunContext!.Session.Should().NotBeNull("CurrentRunContext.Session should not be null when invoked via AGUI endpoint (regression #3823)");
    }

    /// <summary>
    /// Verifies that the shared pre/post-processing middleware (via the single-delegate <c>AIAgentBuilder.Use</c> overload)
    /// also receives a non-null session when invoked through the AGUI endpoint.
    /// </summary>
    [Fact]
    public async Task AGUIMiddleware_SharedUseOverload_SessionIsNotNullAsync()
    {
        // Arrange
        AgentSession? capturedSession = null;
        var innerAgent = new FakeSessionCapturingAgent();

        // Use the shared (pre/post-processing) middleware overload
        AIAgent agentWithMiddleware = new AIAgentBuilder(innerAgent)
            .Use(async (messages, session, options, next, ct) =>
            {
                capturedSession = session;
                await next(messages, session, options, ct);
            })
            .Build();

        await this.SetupTestServerAsync(agentWithMiddleware);
        var chatClient = new AGUIChatClient(this._client!, "", null);
        AIAgent clientAgent = chatClient.AsAIAgent(instructions: null, name: "assistant", description: "Shared middleware test", tools: []);
        ChatClientAgentSession clientSession = (ChatClientAgentSession)await clientAgent.CreateSessionAsync();
        ChatMessage userMessage = new(ChatRole.User, "hello shared");

        List<AgentResponseUpdate> updates = [];

        // Act
        await foreach (AgentResponseUpdate update in clientAgent.RunStreamingAsync([userMessage], clientSession, new AgentRunOptions(), CancellationToken.None))
        {
            updates.Add(update);
        }

        // Assert
        updates.Should().NotBeEmpty();
        capturedSession.Should().NotBeNull("session should be propagated to shared middleware when invoked via AGUI endpoint (regression #3823)");
    }

    /// <summary>
    /// Verifies that the session received by middleware can be used to store and retrieve
    /// state via <see cref="AgentSessionStateBag"/>, proving it is a functional session instance.
    /// </summary>
    [Fact]
    public async Task AGUIMiddleware_SessionStateBag_IsAccessibleAsync()
    {
        // Arrange
        bool stateBagAccessible = false;
        var innerAgent = new FakeSessionCapturingAgent();

        AIAgent agentWithMiddleware = new AIAgentBuilder(innerAgent)
            .Use(
                runFunc: null,
                runStreamingFunc: (messages, session, options, innerAgent, ct) =>
                {
                    if (session is not null)
                    {
                        // Verify StateBag is usable
                        session.StateBag.SetValue("test_key", "test_value");
                        stateBagAccessible = session.StateBag.TryGetValue<string>("test_key", out var retrieved)
                            && retrieved == "test_value";
                    }

                    return innerAgent.RunStreamingAsync(messages, session, options, ct);
                })
            .Build();

        await this.SetupTestServerAsync(agentWithMiddleware);
        var chatClient = new AGUIChatClient(this._client!, "", null);
        AIAgent clientAgent = chatClient.AsAIAgent(instructions: null, name: "assistant", description: "StateBag test", tools: []);
        ChatClientAgentSession clientSession = (ChatClientAgentSession)await clientAgent.CreateSessionAsync();
        ChatMessage userMessage = new(ChatRole.User, "test statebag");

        List<AgentResponseUpdate> updates = [];

        // Act
        await foreach (AgentResponseUpdate update in clientAgent.RunStreamingAsync([userMessage], clientSession, new AgentRunOptions(), CancellationToken.None))
        {
            updates.Add(update);
        }

        // Assert
        updates.Should().NotBeEmpty();
        stateBagAccessible.Should().BeTrue("middleware should be able to use Session.StateBag when invoked via AGUI endpoint");
    }

    private async Task SetupTestServerAsync(AIAgent agent)
    {
        WebApplicationBuilder builder = WebApplication.CreateBuilder();
        builder.WebHost.UseTestServer();
        builder.Services.AddAGUI();

        this._app = builder.Build();
        this._app.MapAGUI("/agent", agent);

        await this._app.StartAsync();

        TestServer testServer = this._app.Services.GetRequiredService<IServer>() as TestServer
            ?? throw new InvalidOperationException("TestServer not found");

        this._client = testServer.CreateClient();
        this._client.BaseAddress = new Uri("http://localhost/agent");
    }

    public async ValueTask DisposeAsync()
    {
        this._client?.Dispose();
        if (this._app != null)
        {
            await this._app.DisposeAsync();
        }
    }
}

/// <summary>
/// A fake agent for testing session propagation through middleware.
/// This agent implements <see cref="CreateSessionCoreAsync"/> to return a valid session,
/// and its <see cref="RunCoreStreamingAsync"/> produces a deterministic response.
/// </summary>
[SuppressMessage("Performance", "CA1812:Avoid uninstantiated internal classes", Justification = "Instantiated directly in tests")]
internal sealed class FakeSessionCapturingAgent : AIAgent
{
    protected override string? IdCore => "fake-session-agent";

    public override string? Description => "A fake agent for testing session propagation through middleware";

    protected override ValueTask<AgentSession> CreateSessionCoreAsync(CancellationToken cancellationToken = default) =>
        new(new FakeAgentSession());

    protected override ValueTask<AgentSession> DeserializeSessionCoreAsync(JsonElement serializedState, JsonSerializerOptions? jsonSerializerOptions = null, CancellationToken cancellationToken = default) =>
        new(serializedState.Deserialize<FakeAgentSession>(jsonSerializerOptions)!);

    protected override ValueTask<JsonElement> SerializeSessionCoreAsync(AgentSession session, JsonSerializerOptions? jsonSerializerOptions = null, CancellationToken cancellationToken = default)
    {
        if (session is not FakeAgentSession fakeSession)
        {
            throw new InvalidOperationException(
                $"The provided session type '{session.GetType().Name}' is not compatible with this agent. " +
                $"Only sessions of type '{nameof(FakeAgentSession)}' can be serialized by this agent.");
        }

        return new(JsonSerializer.SerializeToElement(fakeSession, jsonSerializerOptions));
    }

    protected override async Task<AgentResponse> RunCoreAsync(
        IEnumerable<ChatMessage> messages,
        AgentSession? session = null,
        AgentRunOptions? options = null,
        CancellationToken cancellationToken = default)
    {
        List<AgentResponseUpdate> updates = [];
        await foreach (AgentResponseUpdate update in this.RunStreamingAsync(messages, session, options, cancellationToken).ConfigureAwait(false))
        {
            updates.Add(update);
        }

        return updates.ToAgentResponse();
    }

    protected override async IAsyncEnumerable<AgentResponseUpdate> RunCoreStreamingAsync(
        IEnumerable<ChatMessage> messages,
        AgentSession? session = null,
        AgentRunOptions? options = null,
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        string messageId = Guid.NewGuid().ToString("N");

        foreach (string chunk in new[] { "Session", " ", "test", " ", "response" })
        {
            yield return new AgentResponseUpdate
            {
                MessageId = messageId,
                Role = ChatRole.Assistant,
                Contents = [new TextContent(chunk)]
            };

            await Task.Yield();
        }
    }

    private sealed class FakeAgentSession : AgentSession
    {
        public FakeAgentSession()
        {
        }

        [JsonConstructor]
        public FakeAgentSession(AgentSessionStateBag stateBag) : base(stateBag)
        {
        }
    }
}
