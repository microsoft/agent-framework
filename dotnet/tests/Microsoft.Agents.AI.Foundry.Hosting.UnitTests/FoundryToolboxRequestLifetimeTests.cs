// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Linq;
using System.Runtime.CompilerServices;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using Azure.AI.AgentServer.Responses;
using Azure.AI.AgentServer.Responses.Models;
using Azure.Core;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging.Abstractions;
using Moq;
using MeaiTextContent = Microsoft.Extensions.AI.TextContent;

namespace Microsoft.Agents.AI.Foundry.Hosting.UnitTests;

/// <summary>
/// Verifies that every Foundry toolbox MCP connection belongs to exactly one response and the platform
/// call id of that response.
/// </summary>
/// <remarks>
/// The toolbox proxy resolves the caller only from the opaque, per-request <c>x-agent-foundry-call-id</c>; the
/// user id is never forwarded. An MCP session opened for one call id, or for none, must therefore never carry
/// another response's tool calls. These tests drive the response handler against a loopback MCP server that
/// records which call id opened each session.
/// </remarks>
[Collection(FoundryProjectEndpointEnvFixture.Name)]
public sealed class FoundryToolboxRequestLifetimeTests
{
    private const string ConsentLink = "https://auth.example.com/authorize";
    private static readonly string s_responseId = "resp_" + new string('4', 46);
    private static readonly TimeSpan s_runTimeout = TimeSpan.FromSeconds(30);
    private static readonly string[] s_callIdsInOrder = ["call-a", "call-b"];
    private static readonly string[] s_callerToolNames = ["tool_for_call_a"];
    private static readonly string[] s_toolNamesInToolboxOrder = ["weather_tool", "calendar_tool"];

    [Fact]
    public async Task StartAsync_OpensNoToolboxConnectionAsync()
    {
        // Arrange
        await using var server = await ToolboxLoopbackServer.StartAsync();
        await using var service = CreateService(server, "weather");

        // Act
        await service.StartAsync(CancellationToken.None);

        // Assert: startup has no caller, so any MCP session it opened could only be shared by every later caller.
        Assert.Empty(server.Requests);
    }

    [Fact]
    public async Task StartAsync_UnsafeToolboxName_FailsBeforeAnyRequestAsync()
    {
        // Arrange: a name that would move the proxy request target is a configuration error.
        await using var server = await ToolboxLoopbackServer.StartAsync();
        await using var service = CreateService(server, "../admin");

        // Act
        var exception = await Record.ExceptionAsync(() => service.StartAsync(CancellationToken.None));

        // Assert: fail fast at startup instead of retrying the rejected name on every request.
        Assert.IsType<InvalidOperationException>(exception);
        Assert.Empty(server.Requests);
    }

    [Fact]
    public async Task CreateAsync_ToolCallRunsOnSessionOpenedForItsCallIdAsync()
    {
        // Arrange
        await using var server = await ToolboxLoopbackServer.StartAsync();
        await using var service = CreateService(server, "weather");
        await service.StartAsync(CancellationToken.None);
        var handler = CreateHandler(new ToolCallingAgent(), service);

        // Act
        await RunAsync(handler, callId: "call-a");
        await RunAsync(handler, callId: "call-b");

        // Assert: each response's tool call travels on a session that the same caller opened.
        var calls = server.RequestsFor("tools/call");
        Assert.Equal(s_callIdsInOrder, calls.Select(static call => call.CallId));
        Assert.All(calls, call => Assert.Equal(call.CallId, server.CallIdThatOpened(call.SessionId)));
        Assert.NotEqual(calls[0].SessionId, calls[1].SessionId);
    }

    [Fact]
    public async Task CreateAsync_DiscoversToolsForTheCallerAsync()
    {
        // Arrange: the proxy can list different tools for different callers (delegated tool sources).
        await using var server = await ToolboxLoopbackServer.StartAsync();
        server.ToolNameFor = static (_, callId) => callId is null ? "startup_tool" : "tool_for_" + callId.Replace('-', '_');
        await using var service = CreateService(server, "weather");
        await service.StartAsync(CancellationToken.None);
        var agent = new ToolCallingAgent { InvokeTools = false };
        var handler = CreateHandler(agent, service);

        // Act
        await RunAsync(handler, callId: "call-a");

        // Assert: the agent sees the caller's tool list, not a list discovered without a caller.
        Assert.Equal(s_callerToolNames, Assert.Single(agent.ObservedToolNames));
    }

    [Fact]
    public async Task CreateAsync_CallerNeedsConsentAtDiscovery_SurfacesConsentRequestAsync()
    {
        // Arrange: discovery succeeds without a caller but needs OAuth consent for this caller.
        await using var server = await ToolboxLoopbackServer.StartAsync();
        server.ToolsListErrorFor = static (_, callId) => callId == "call-consent" ? ConsentRequiredError() : null;
        await using var service = CreateService(server, "weather");
        await service.StartAsync(CancellationToken.None);
        var agent = new ToolCallingAgent();
        var handler = CreateHandler(agent, service);

        // Act
        var events = await RunAsync(handler, callId: "call-consent");

        // Assert: the turn stops on the caller's consent prompt before the agent runs.
        var consent = Assert.Single(
            events.OfType<ResponseOutputItemAddedEvent>().Select(static added => added.Item).OfType<OAuthConsentRequestOutputItem>());
        Assert.Equal(ConsentLink, consent.ConsentLink);
        Assert.IsType<ResponseIncompleteEvent>(events[^1]);
        Assert.Empty(agent.ObservedToolNames);
    }

    [Fact]
    public async Task CreateAsync_EndsEveryMcpSessionWhenTheResponseCompletesAsync()
    {
        // Arrange
        await using var server = await ToolboxLoopbackServer.StartAsync();
        await using var service = CreateService(server, "weather");
        await service.StartAsync(CancellationToken.None);
        var handler = CreateHandler(new ToolCallingAgent(), service);

        // Act
        await RunAsync(handler, callId: "call-a");

        // Assert: no MCP session outlives the response, while the service itself is still running.
        Assert.NotEmpty(server.IssuedSessionIds);
        Assert.All(server.IssuedSessionIds, sessionId => Assert.Contains(sessionId, server.EndedSessionIds));
    }

    [Fact]
    public async Task CreateAsync_OpensNoStandaloneServerStreamAsync()
    {
        // Arrange
        await using var server = await ToolboxLoopbackServer.StartAsync();
        await using var service = CreateService(server, "weather");
        await service.StartAsync(CancellationToken.None);
        var handler = CreateHandler(new ToolCallingAgent(), service);

        // Act
        await RunAsync(handler, callId: "call-a");

        // Assert: a session that lives for one response has no use for unsolicited server messages, so it does
        // not hold a pooled connection open for the standalone GET stream.
        Assert.Single(server.RequestsFor("tools/call"));
        Assert.DoesNotContain(server.Requests, static request => request.HttpMethod == "GET");
    }

    [Fact]
    public async Task CreateAsync_ConcurrentResponsesWithTheSameCallId_UseIndependentSessionsAsync()
    {
        // Arrange: recovery or duplicate delivery can run two responses with the same platform call id.
        await using var server = await ToolboxLoopbackServer.StartAsync();
        await using var service = CreateService(server, "weather");
        await service.StartAsync(CancellationToken.None);
        var handler = CreateHandler(new ToolCallingAgent { ConcurrentRuns = 2 }, service);

        // Act
        await Task.WhenAll(
            Task.Run(() => RunAsync(handler, callId: "call-dup")),
            Task.Run(() => RunAsync(handler, callId: "call-dup")));

        // Assert: each response owns its own session and ends it.
        var sessions = server.RequestsFor("tools/call").Select(static call => call.SessionId).ToArray();
        Assert.Equal(2, sessions.Length);
        Assert.Equal(2, sessions.Distinct(StringComparer.Ordinal).Count());
        Assert.All(sessions, sessionId => Assert.Contains(sessionId, server.EndedSessionIds));
    }

    [Fact]
    public async Task CreateAsync_OpensConfiguredToolboxesConcurrentlyAsync()
    {
        // Arrange
        await using var server = await ToolboxLoopbackServer.StartAsync();
        server.ToolNameFor = static (toolboxName, _) => toolboxName + "_tool";
        server.InitializeConcurrencyTarget = 2;
        await using var service = CreateService(server, "weather", "calendar");
        await service.StartAsync(CancellationToken.None);
        var agent = new ToolCallingAgent { InvokeTools = false };
        var handler = CreateHandler(agent, service);

        // Act
        await RunAsync(handler, callId: "call-a");

        // Assert: toolbox handshakes overlap, and tools keep the configured toolbox order.
        Assert.Equal(2, server.MaxConcurrentInitializes);
        Assert.Equal(s_toolNamesInToolboxOrder, Assert.Single(agent.ObservedToolNames));
    }

    [Fact]
    public async Task CreateAsync_ToolCallKeepsItsCallIdWithoutAmbientContextAsync()
    {
        // Arrange: the agent invokes the tool from a worker that does not flow the request's execution context.
        await using var server = await ToolboxLoopbackServer.StartAsync();
        await using var service = CreateService(server, "weather");
        await service.StartAsync(CancellationToken.None);
        var handler = CreateHandler(new ToolCallingAgent { SuppressExecutionContextFlow = true }, service);

        // Act
        await RunAsync(handler, callId: "call-a");

        // Assert: the call id belongs to the connection, so it cannot be lost with ambient state.
        var call = Assert.Single(server.RequestsFor("tools/call"));
        Assert.Equal("call-a", call.CallId);
        Assert.Equal("call-a", server.CallIdThatOpened(call.SessionId));
    }

    private static JsonObject ConsentRequiredError() => new()
    {
        ["code"] = -32006,
        ["message"] = "tools/list failed " +
            """{"errors":[{"name":"get_weather","type":"mcp","error":{"code":"CONSENT_REQUIRED","message":"https://auth.example.com/authorize"}}]}""",
    };

    private static FoundryToolboxService CreateService(ToolboxLoopbackServer server, params string[] toolboxNames)
    {
        var credential = new Mock<TokenCredential>();
        credential
            .Setup(c => c.GetTokenAsync(It.IsAny<TokenRequestContext>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(new AccessToken("test-token", DateTimeOffset.UtcNow.AddHours(1)));
        var options = new FoundryToolboxServiceOptions { EndpointOverride = server.Endpoint };
        foreach (var name in toolboxNames)
        {
            options.ToolboxNames.Add(name);
        }

        return new FoundryToolboxService(options, credential.Object);
    }

    private static AgentFrameworkResponseHandler CreateHandler(AIAgent agent, FoundryToolboxService service)
    {
        var services = new ServiceCollection();
        services.AddSingleton<AgentSessionStore>(new TestAgentSessionStore());
        services.AddSingleton(agent);
        return new AgentFrameworkResponseHandler(
            services.BuildServiceProvider(),
            NullLogger<AgentFrameworkResponseHandler>.Instance,
            new FoundryResponsesServerOptions(),
            service);
    }

    private static async Task<List<ResponseStreamEvent>> RunAsync(AgentFrameworkResponseHandler handler, string callId)
    {
        var request = new CreateResponse { Model = "test" };
        request.Input = BinaryData.FromObjectAsJson(new[]
        {
            new
            {
                type = "message",
                id = "msg_1",
                status = "completed",
                role = "user",
                content = new[] { new { type = "input_text", text = "What is the weather?" } },
            },
        });

        var context = new Mock<ResponseContext>(s_responseId) { CallBase = true };
        context.Setup(x => x.PlatformContext).Returns(new PlatformContext("user", callId));
        context.Setup(x => x.GetHistoryAsync(It.IsAny<CancellationToken>())).ReturnsAsync(Array.Empty<OutputItem>());
        context.Setup(x => x.GetInputItemsAsync(It.IsAny<bool>(), It.IsAny<CancellationToken>())).ReturnsAsync(Array.Empty<Item>());

        using var timeout = new CancellationTokenSource(s_runTimeout);
        var events = new List<ResponseStreamEvent>();
        await foreach (var responseEvent in handler.CreateAsync(request, context.Object, timeout.Token))
        {
            events.Add(responseEvent);
        }

        return events;
    }

    /// <summary>
    /// Records the tools a response exposes to the agent and, unless disabled, invokes each of them once.
    /// </summary>
    private sealed class ToolCallingAgent : AIAgent
    {
        private static readonly TimeSpan s_concurrentRunsTimeout = TimeSpan.FromSeconds(10);
        private readonly TaskCompletionSource _concurrentRunsEntered = new(TaskCreationOptions.RunContinuationsAsynchronously);
        private int _runCount;

        /// <summary>Gets a value indicating whether each exposed tool is invoked.</summary>
        internal bool InvokeTools { get; init; } = true;

        /// <summary>Gets a value indicating whether tools run on a worker without the request's execution context.</summary>
        internal bool SuppressExecutionContextFlow { get; init; }

        /// <summary>Gets how many runs must be in progress together before any of them invokes a tool.</summary>
        internal int ConcurrentRuns { get; init; } = 1;

        /// <summary>Gets the tool names exposed to each run, in run order.</summary>
        internal ConcurrentQueue<IReadOnlyList<string>> ObservedToolNames { get; } = new();

        protected override async IAsyncEnumerable<AgentResponseUpdate> RunCoreStreamingAsync(
            IEnumerable<ChatMessage> messages,
            AgentSession? session,
            AgentRunOptions? options,
            [EnumeratorCancellation] CancellationToken cancellationToken = default)
        {
            var tools = (options as ChatClientAgentRunOptions)?.ChatOptions?.Tools ?? [];
            this.ObservedToolNames.Enqueue([.. tools.Select(static tool => tool.Name)]);
            if (Interlocked.Increment(ref this._runCount) >= this.ConcurrentRuns)
            {
                this._concurrentRunsEntered.TrySetResult();
            }

            await this._concurrentRunsEntered.Task.WaitAsync(s_concurrentRunsTimeout, cancellationToken);
            if (this.InvokeTools)
            {
                foreach (var function in tools.OfType<AIFunction>())
                {
                    await this.InvokeAsync(function, cancellationToken);
                }
            }

            yield return new AgentResponseUpdate { MessageId = "resp_msg_1", Contents = [new MeaiTextContent("done")] };
        }

        protected override Task<AgentResponse> RunCoreAsync(
            IEnumerable<ChatMessage> messages,
            AgentSession? session,
            AgentRunOptions? options,
            CancellationToken cancellationToken = default) =>
            throw new NotSupportedException();

        protected override ValueTask<AgentSession> CreateSessionCoreAsync(CancellationToken cancellationToken = default) =>
            new(new ToolCallingSession());

        protected override ValueTask<JsonElement> SerializeSessionCoreAsync(
            AgentSession session,
            JsonSerializerOptions? jsonSerializerOptions,
            CancellationToken cancellationToken = default) =>
            new(JsonDocument.Parse("{}").RootElement);

        protected override ValueTask<AgentSession> DeserializeSessionCoreAsync(
            JsonElement serializedState,
            JsonSerializerOptions? jsonSerializerOptions,
            CancellationToken cancellationToken = default) =>
            new(new ToolCallingSession());

        private Task<object?> InvokeAsync(AIFunction function, CancellationToken cancellationToken)
        {
            var arguments = new AIFunctionArguments { ["city"] = "Amsterdam" };
            if (!this.SuppressExecutionContextFlow)
            {
                return function.InvokeAsync(arguments, cancellationToken).AsTask();
            }

            // Start the call without the request's execution context, so no ambient value can identify the caller.
            using (ExecutionContext.SuppressFlow())
            {
                return Task.Run(() => function.InvokeAsync(arguments, cancellationToken).AsTask(), cancellationToken);
            }
        }
    }

    private sealed class ToolCallingSession : AgentSession
    {
    }
}
