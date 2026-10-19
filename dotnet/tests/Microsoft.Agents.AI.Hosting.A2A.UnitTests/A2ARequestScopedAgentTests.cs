// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using System.Globalization;
using System.Linq;
using System.Net;
using System.Net.Http;
using System.Runtime.CompilerServices;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using A2A;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Routing;
using Microsoft.AspNetCore.TestHost;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using Moq;

namespace Microsoft.Agents.AI.Hosting.A2A.UnitTests;

/// <summary>
/// Verifies that A2A hosting honors agent registration lifetimes and selects agents for each request.
/// </summary>
public sealed class A2ARequestScopedAgentTests
{
    private static readonly TimeSpan s_timeout = TimeSpan.FromSeconds(10);

    [Fact]
    public async Task AddA2AServer_WithScopedAgent_ResolvesAgentForEachOperationAsync()
    {
        // Arrange
        int createdAgents = 0;
        ServiceCollection services = new();
        services.AddLogging();
        services.AddScoped<RequestDependency>();
        services.AddAIAgent(
            "assistant",
            (sp, name) =>
            {
                _ = sp.GetRequiredService<RequestDependency>();
                Interlocked.Increment(ref createdAgents);
                return new TurnCountingAgent(name);
            },
            ServiceLifetime.Scoped)
            .WithInMemorySessionStore(withIsolation: false);
        services.AddA2AServer("assistant");
        await using ServiceProvider provider = services.BuildServiceProvider(new ServiceProviderOptions { ValidateScopes = true });
        A2AServer server = provider.GetRequiredKeyedService<A2AServer>("assistant");

        // Act
        SendMessageResponse firstResponse = await server.SendMessageAsync(CreateRequest("ctx-1"));
        SendMessageResponse secondResponse = await server.SendMessageAsync(CreateRequest("ctx-1"));

        // Assert
        Assert.Equal(2, createdAgents);
        Assert.Equal("assistant turn 1", GetText(firstResponse));
        Assert.Equal("assistant turn 2", GetText(secondResponse));
    }

    [Fact]
    public async Task AddA2AServer_WithSingletonHostedAgentBuilder_ResolvesAgentOnceAsync()
    {
        // Arrange
        int createdAgents = 0;
        ServiceCollection services = new();
        services.AddLogging();
        services.AddAIAgent(
            "assistant",
            (_, name) =>
            {
                Interlocked.Increment(ref createdAgents);
                return new TurnCountingAgent(name);
            })
            .WithInMemorySessionStore(withIsolation: false)
            .AddA2AServer();
        await using ServiceProvider provider = services.BuildServiceProvider(new ServiceProviderOptions { ValidateScopes = true });
        A2AServer server = provider.GetRequiredKeyedService<A2AServer>("assistant");
        int createdAtServerCreation = createdAgents;

        // Act
        await server.SendMessageAsync(CreateRequest("ctx-1"));
        SendMessageResponse secondResponse = await server.SendMessageAsync(CreateRequest("ctx-1"));

        // Assert
        Assert.Equal(1, createdAtServerCreation);
        Assert.Equal(1, createdAgents);
        Assert.Equal("assistant turn 2", GetText(secondResponse));
    }

    [Fact]
    public async Task AddA2AServer_WithUnregisteredAgent_ThrowsWhenServerIsResolvedAsync()
    {
        // Arrange
        ServiceCollection services = new();
        services.AddLogging();
        services.AddA2AServer("missing");
        await using ServiceProvider provider = services.BuildServiceProvider();

        // Act & Assert
        InvalidOperationException exception = Assert.Throws<InvalidOperationException>(() => provider.GetRequiredKeyedService<A2AServer>("missing"));
        Assert.Contains("missing", exception.Message, StringComparison.Ordinal);
    }

    [Fact]
    public async Task AddA2AServer_WithCustomAgentHandler_DoesNotRequireAgentRegistrationAsync()
    {
        // Arrange
        ServiceCollection services = new();
        services.AddLogging();
        services.AddKeyedSingleton("custom", Mock.Of<IAgentHandler>());
        services.AddA2AServer("custom");
        await using ServiceProvider provider = services.BuildServiceProvider();

        // Act
        A2AServer? server = provider.GetKeyedService<A2AServer>("custom");

        // Assert
        Assert.NotNull(server);
    }

    [Fact]
    public async Task MapA2AHttpJson_WithAgentSelector_SelectsAgentFromRouteValueAsync()
    {
        // Arrange
        await using WebApplication app = await StartAsync(
            services =>
            {
                services.AddAIAgent("alpha", (_, name) => new TurnCountingAgent(name), ServiceLifetime.Scoped)
                    .WithInMemorySessionStore(withIsolation: false);
                services.AddAIAgent("beta", (_, name) => new TurnCountingAgent(name), ServiceLifetime.Transient)
                    .WithInMemorySessionStore(withIsolation: false);
            },
            endpoints => endpoints.MapA2AHttpJson("/agents/{agentId}/a2a", SelectAgentFromRoute));
        using HttpClient httpClient = app.GetTestClient();
        using A2AHttpJsonClient alphaClient = new(new Uri(httpClient.BaseAddress!, "/agents/alpha/a2a"), httpClient);
        using A2AHttpJsonClient betaClient = new(new Uri(httpClient.BaseAddress!, "/agents/beta/a2a"), httpClient);

        // Act
        SendMessageResponse firstAlphaResponse = await alphaClient.SendMessageAsync(CreateRequest("ctx-1"));
        SendMessageResponse secondAlphaResponse = await alphaClient.SendMessageAsync(CreateRequest("ctx-1"));
        SendMessageResponse betaResponse = await betaClient.SendMessageAsync(CreateRequest("ctx-1"));

        // Assert
        Assert.Equal("alpha turn 1", GetText(firstAlphaResponse));
        Assert.Equal("alpha turn 2", GetText(secondAlphaResponse));
        Assert.Equal("beta turn 1", GetText(betaResponse));
    }

    [Fact]
    public async Task MapA2AJsonRpc_WithAgentSelector_PersistsSessionsAcrossNewAgentInstancesAsync()
    {
        // Arrange
        await using WebApplication app = await StartAsync(
            services => services.AddKeyedSingleton<AgentSessionStore>("dynamic", new InMemoryAgentSessionStore()),
            endpoints => endpoints.MapA2AJsonRpc("/a2a", _ => new TurnCountingAgent("dynamic")));
        using HttpClient httpClient = app.GetTestClient();
        using A2AClient client = new(new Uri(httpClient.BaseAddress!, "/a2a"), httpClient);

        // Act
        SendMessageResponse firstResponse = await client.SendMessageAsync(CreateRequest("ctx-1"));
        SendMessageResponse secondResponse = await client.SendMessageAsync(CreateRequest("ctx-1"));
        SendMessageResponse otherContextResponse = await client.SendMessageAsync(CreateRequest("ctx-2"));

        // Assert
        Assert.Equal("dynamic turn 1", GetText(firstResponse));
        Assert.Equal("dynamic turn 2", GetText(secondResponse));
        Assert.Equal("dynamic turn 1", GetText(otherContextResponse));
    }

    [Fact]
    public async Task MapA2AHttpJson_WithAgentSelector_StreamsSelectedAgentAsync()
    {
        // Arrange
        await using WebApplication app = await StartAsync(
            _ => { },
            endpoints => endpoints.MapA2AHttpJson("/a2a", _ => new TurnCountingAgent("streaming")));
        using HttpClient httpClient = app.GetTestClient();
        using A2AHttpJsonClient client = new(new Uri(httpClient.BaseAddress!, "/a2a"), httpClient);

        // Act
        List<StreamResponse> responses = [];
        await foreach (StreamResponse response in client.SendStreamingMessageAsync(CreateRequest("ctx-1")))
        {
            responses.Add(response);
        }

        // Assert
        Message message = Assert.IsType<Message>(Assert.Single(responses).Message);
        Assert.Equal("streaming turn 1", string.Concat(message.Parts.Select(part => part.Text)));
    }

    [Fact]
    public async Task MapA2AHttpJson_WithAgentSelector_SharesTaskStateAcrossRequestsAsync()
    {
        // Arrange
        await using WebApplication app = await StartAsync(
            _ => { },
            endpoints => endpoints.MapA2AHttpJson(
                "/a2a",
                _ => new TurnCountingAgent("tasks"),
                options => options.AgentRunMode = AgentRunMode.ReturnTask));
        using HttpClient httpClient = app.GetTestClient();
        using A2AHttpJsonClient client = new(new Uri(httpClient.BaseAddress!, "/a2a"), httpClient);

        // Act
        SendMessageResponse response = await client.SendMessageAsync(CreateRequest("ctx-1"));
        AgentTask task = await client.GetTaskAsync(new GetTaskRequest { Id = response.Task!.Id });

        // Assert
        Assert.Equal(response.Task.Id, task.Id);
        Assert.Equal(TaskState.Completed, task.Status.State);
    }

    [Fact]
    public async Task MapA2AJsonRpc_WithAgentSelectorReturningTask_RejectsReturnImmediatelyAsync()
    {
        // Arrange
        await using WebApplication app = await StartAsync(
            _ => { },
            endpoints => endpoints.MapA2AJsonRpc(
                "/a2a",
                _ => new TurnCountingAgent("tasks"),
                options => options.AgentRunMode = AgentRunMode.ReturnTask));
        using HttpClient httpClient = app.GetTestClient();
        using A2AClient client = new(new Uri(httpClient.BaseAddress!, "/a2a"), httpClient);

        // Act
        A2AException exception = await Assert.ThrowsAsync<A2AException>(
            () => client.SendMessageAsync(CreateRequest("ctx-1", returnImmediately: true)));

        // Assert
        Assert.Equal(A2AErrorCode.UnsupportedOperation, exception.ErrorCode);
    }

    [Fact]
    public async Task MapA2AHttpJson_WithAgentSelectorReturningMessage_IgnoresReturnImmediatelyAsync()
    {
        // Arrange
        await using WebApplication app = await StartAsync(
            _ => { },
            endpoints => endpoints.MapA2AHttpJson("/a2a", _ => new TurnCountingAgent("messages")));
        using HttpClient httpClient = app.GetTestClient();
        using A2AHttpJsonClient client = new(new Uri(httpClient.BaseAddress!, "/a2a"), httpClient);

        // Act
        SendMessageResponse response = await client.SendMessageAsync(CreateRequest("ctx-1", returnImmediately: true));

        // Assert
        Assert.Equal("messages turn 1", GetText(response));
    }

    [Fact]
    public async Task MapA2AHttpJson_WithAgentSelectorReturningNull_ReturnsNotFoundAsync()
    {
        // Arrange
        int selections = 0;
        await using WebApplication app = await StartAsync(
            _ => { },
            endpoints => endpoints.MapA2AHttpJson("/agents/{agentId}/a2a", _ =>
            {
                Interlocked.Increment(ref selections);
                return null;
            }));
        using HttpClient httpClient = app.GetTestClient();

        // Act
        using HttpResponseMessage response = await httpClient.GetAsync(new Uri("/agents/unknown/a2a/tasks/task-1", UriKind.Relative));

        // Assert
        Assert.Equal(HttpStatusCode.NotFound, response.StatusCode);
        Assert.Equal(1, selections);
    }

    [Fact]
    public async Task MapA2AJsonRpc_WithAgentSelectorReturningUnnamedAgent_FailsRequestAsync()
    {
        // Arrange
        await using WebApplication app = await StartAsync(
            _ => { },
            endpoints => endpoints.MapA2AJsonRpc("/a2a", _ => new TurnCountingAgent(name: null)));
        using HttpClient httpClient = app.GetTestClient();
        using A2AClient client = new(new Uri(httpClient.BaseAddress!, "/a2a"), httpClient);

        // Act & Assert
        InvalidOperationException exception = await Assert.ThrowsAsync<InvalidOperationException>(() => client.SendMessageAsync(CreateRequest("ctx-1")));
        Assert.Contains("stable name", exception.Message, StringComparison.Ordinal);
    }

    [Fact]
    public async Task MapA2AHttpJson_WithAgentSelector_KeepsRequestServicesUntilStreamingRunCompletesAfterDisconnectAsync()
    {
        // Arrange
        DisconnectProbe probe = new();
        await using WebApplication app = await StartAsync(
            services =>
            {
                services.AddScoped<DisposableRequestDependency>();
                services.AddKeyedScoped<AgentSessionStore>("streaming", (_, _) => new TrackingSessionStore(probe));
            },
            endpoints =>
            {
                endpoints.Use(async (context, next) =>
                {
                    try
                    {
                        await next(context);
                    }
                    finally
                    {
                        probe.RequestCompleted.TrySetResult();
                    }
                });
                endpoints.MapA2AHttpJson("/a2a", context => new BlockingAgent(context.RequestServices.GetRequiredService<DisposableRequestDependency>(), probe));
            });
        using HttpClient httpClient = app.GetTestClient();
        using A2AHttpJsonClient client = new(new Uri(httpClient.BaseAddress!, "/a2a"), httpClient);
        using CancellationTokenSource disconnect = new();

        // Act
        Task streaming = ConsumeAsync(client.SendStreamingMessageAsync(CreateRequest("ctx-1"), disconnect.Token));
        await Task.WhenAny(probe.AgentStarted.Task, streaming).WaitAsync(s_timeout);
        Assert.False(streaming.IsCompleted);
        disconnect.Cancel();
        Task first = await Task.WhenAny(probe.RequestCompleted.Task, Task.Delay(TimeSpan.FromMilliseconds(500)));
        bool requestCompletedBeforeRun = first == probe.RequestCompleted.Task;
        probe.ReleaseAgent.SetResult();
        await probe.SessionSaved.Task.WaitAsync(s_timeout);
        await probe.RequestCompleted.Task.WaitAsync(s_timeout);

        // Assert
        Assert.False(requestCompletedBeforeRun);
        Assert.False(probe.DependencyDisposedWhenRunFinished);
        Assert.False(probe.StoreDisposedWhenSessionSaved);
        await Assert.ThrowsAnyAsync<Exception>(() => streaming.WaitAsync(s_timeout));
    }

    [Fact]
    public async Task MapA2AHttpJson_WithRegisteredServerAndScopedIsolationKeyProvider_IsolatesTasksAndSessionsPerRequestAsync()
    {
        // Arrange
        await using WebApplication app = await StartAsync(
            services =>
            {
                services.AddScoped<AgentIsolationKeyProvider, RequestIsolationKeyProvider>();
                services.AddAIAgent("assistant", (_, name) => new TurnCountingAgent(name), ServiceLifetime.Scoped)
                    .WithInMemorySessionStore(withIsolation: false);
                services.AddA2AServer("assistant", options => options.AgentRunMode = AgentRunMode.ReturnTask);
            },
            endpoints =>
            {
                UseRequestIsolationKeyFromHeader(endpoints);
                endpoints.MapA2AHttpJson("assistant", "/a2a");
            });
        using HttpClient aliceHttpClient = CreateUserHttpClient(app, "alice");
        using HttpClient bobHttpClient = CreateUserHttpClient(app, "bob");
        using A2AHttpJsonClient alice = new(new Uri(aliceHttpClient.BaseAddress!, "/a2a"), aliceHttpClient);
        using A2AHttpJsonClient bob = new(new Uri(bobHttpClient.BaseAddress!, "/a2a"), bobHttpClient);

        // Act
        SendMessageResponse aliceFirst = await alice.SendMessageAsync(CreateRequest("ctx-1"));
        List<StreamResponse> aliceStreamed = [];
        await foreach (StreamResponse response in alice.SendStreamingMessageAsync(CreateRequest("ctx-1")))
        {
            aliceStreamed.Add(response);
        }

        SendMessageResponse bobFirst = await bob.SendMessageAsync(CreateRequest("ctx-1"));
        string aliceStreamedTaskId = aliceStreamed.Select(response => response.Task?.Id ?? response.StatusUpdate?.TaskId).First(id => id is not null)!;
        AgentTask aliceStreamedTask = await alice.GetTaskAsync(new GetTaskRequest { Id = aliceStreamedTaskId });
        A2AException otherUserError = await Assert.ThrowsAsync<A2AException>(() => bob.GetTaskAsync(new GetTaskRequest { Id = aliceFirst.Task!.Id }));

        // Assert
        Assert.Equal("assistant turn 1", GetArtifactText(aliceFirst.Task!));
        Assert.Equal("assistant turn 2", GetArtifactText(aliceStreamedTask));
        Assert.Equal("assistant turn 1", GetArtifactText(bobFirst.Task!));
        Assert.Equal(A2AErrorCode.TaskNotFound, otherUserError.ErrorCode);
    }

    [Fact]
    public async Task MapA2AHttpJson_WithAgentSelectorAndScopedIsolationKeyProvider_IsolatesTasksPerRequestAsync()
    {
        // Arrange
        await using WebApplication app = await StartAsync(
            services => services.AddScoped<AgentIsolationKeyProvider, RequestIsolationKeyProvider>(),
            endpoints =>
            {
                UseRequestIsolationKeyFromHeader(endpoints);
                endpoints.MapA2AHttpJson("/a2a", _ => new TurnCountingAgent("tasks"), options => options.AgentRunMode = AgentRunMode.ReturnTask);
            });
        using HttpClient aliceHttpClient = CreateUserHttpClient(app, "alice");
        using HttpClient bobHttpClient = CreateUserHttpClient(app, "bob");
        using A2AHttpJsonClient alice = new(new Uri(aliceHttpClient.BaseAddress!, "/a2a"), aliceHttpClient);
        using A2AHttpJsonClient bob = new(new Uri(bobHttpClient.BaseAddress!, "/a2a"), bobHttpClient);

        // Act
        SendMessageResponse sent = await alice.SendMessageAsync(CreateRequest("ctx-1"));
        List<StreamResponse> streamed = [];
        await foreach (StreamResponse response in alice.SendStreamingMessageAsync(CreateRequest("ctx-2")))
        {
            streamed.Add(response);
        }

        string streamedTaskId = streamed.Select(response => response.Task?.Id ?? response.StatusUpdate?.TaskId).First(id => id is not null)!;
        AgentTask sentTask = await alice.GetTaskAsync(new GetTaskRequest { Id = sent.Task!.Id });
        AgentTask streamedTask = await alice.GetTaskAsync(new GetTaskRequest { Id = streamedTaskId });
        A2AException otherUserError = await Assert.ThrowsAsync<A2AException>(() => bob.GetTaskAsync(new GetTaskRequest { Id = sent.Task.Id }));

        // Assert
        Assert.Equal(TaskState.Completed, sentTask.Status.State);
        Assert.Equal(TaskState.Completed, streamedTask.Status.State);
        Assert.Equal(A2AErrorCode.TaskNotFound, otherUserError.ErrorCode);
    }

    [Fact]
    public void MapA2AHttpJson_WithNullAgentSelector_ThrowsArgumentNullException()
    {
        // Arrange
        Mock<IEndpointRouteBuilder> endpoints = new();

        // Act & Assert
        Assert.Throws<ArgumentNullException>(() =>
            endpoints.Object.MapA2AHttpJson("/a2a", (Func<HttpContext, AIAgent?>)null!));
    }

    private static AIAgent? SelectAgentFromRoute(HttpContext context) =>
        context.GetRouteValue("agentId") is string agentId
            ? context.RequestServices.GetKeyedService<AIAgent>(agentId)
            : null;

    private static async Task<WebApplication> StartAsync(Action<IServiceCollection> configureServices, Action<WebApplication> mapEndpoints)
    {
        WebApplicationBuilder builder = WebApplication.CreateBuilder();
        builder.WebHost.UseTestServer();
        builder.Host.UseDefaultServiceProvider(options => options.ValidateScopes = true);
        configureServices(builder.Services);

        WebApplication app = builder.Build();
        mapEndpoints(app);
        await app.StartAsync();
        return app;
    }

    private static SendMessageRequest CreateRequest(string contextId, bool returnImmediately = false) => new()
    {
        Message = new Message
        {
            MessageId = Guid.NewGuid().ToString("N"),
            ContextId = contextId,
            Role = Role.User,
            Parts = [Part.FromText("hi")]
        },
        Configuration = returnImmediately ? new SendMessageConfiguration { ReturnImmediately = true } : null
    };

    private static string? GetText(SendMessageResponse response)
    {
        Message message = Assert.IsType<Message>(response.Message);
        return string.Concat(message.Parts.Select(part => part.Text));
    }

    private static async Task ConsumeAsync(IAsyncEnumerable<StreamResponse> responses)
    {
        await foreach (StreamResponse _ in responses)
        {
        }
    }

    private static HttpClient CreateUserHttpClient(WebApplication app, string user)
    {
        HttpClient httpClient = app.GetTestClient();
        httpClient.DefaultRequestHeaders.Add("X-User", user);
        return httpClient;
    }

    private static void UseRequestIsolationKeyFromHeader(WebApplication app) =>
        app.Use((context, next) =>
        {
            var provider = (RequestIsolationKeyProvider)context.RequestServices.GetRequiredService<AgentIsolationKeyProvider>();
            provider.Key = context.Request.Headers["X-User"].ToString();
            return next(context);
        });

    private static string GetArtifactText(AgentTask task) =>
        string.Concat(task.Artifacts!.SelectMany(artifact => artifact.Parts).Select(part => part.Text));

    [SuppressMessage("Performance", "CA1812:Avoid uninstantiated internal classes", Justification = "Instantiated via dependency injection")]
    private sealed class RequestIsolationKeyProvider : AgentIsolationKeyProvider
    {
        public string? Key { get; set; }

        public override ValueTask<string?> GetIsolationKeyAsync(CancellationToken cancellationToken = default) => new(this.Key);
    }

    private sealed class DisconnectProbe
    {
        public TaskCompletionSource AgentStarted { get; } = new(TaskCreationOptions.RunContinuationsAsynchronously);

        public TaskCompletionSource ReleaseAgent { get; } = new(TaskCreationOptions.RunContinuationsAsynchronously);

        public TaskCompletionSource SessionSaved { get; } = new(TaskCreationOptions.RunContinuationsAsynchronously);

        public TaskCompletionSource RequestCompleted { get; } = new(TaskCreationOptions.RunContinuationsAsynchronously);

        public bool? DependencyDisposedWhenRunFinished { get; set; }

        public bool? StoreDisposedWhenSessionSaved { get; set; }
    }

    [SuppressMessage("Performance", "CA1812:Avoid uninstantiated internal classes", Justification = "Instantiated via dependency injection")]
    private sealed class DisposableRequestDependency : IDisposable
    {
        public bool IsDisposed { get; private set; }

        public void Dispose() => this.IsDisposed = true;
    }

    private sealed class TrackingSessionStore(DisconnectProbe probe) : AgentSessionStore, IDisposable
    {
        private bool _disposed;

        public override ValueTask SaveSessionAsync(AIAgent agent, AgentSessionStoreKey key, AgentSession session, CancellationToken cancellationToken = default)
        {
            probe.StoreDisposedWhenSessionSaved = this._disposed;
            probe.SessionSaved.TrySetResult();
            return default;
        }

        public override ValueTask<AgentSession?> GetSessionAsync(AIAgent agent, AgentSessionStoreKey key, CancellationToken cancellationToken = default) =>
            new((AgentSession?)null);

        public void Dispose() => this._disposed = true;
    }

    private sealed class BlockingAgent(DisposableRequestDependency dependency, DisconnectProbe probe) : AIAgent
    {
        public override string? Name => "streaming";

        protected override ValueTask<AgentSession> CreateSessionCoreAsync(CancellationToken cancellationToken = default) =>
            new(new TurnCountingSession());

        protected override ValueTask<JsonElement> SerializeSessionCoreAsync(AgentSession session, JsonSerializerOptions? jsonSerializerOptions = null, CancellationToken cancellationToken = default) =>
            new(session.StateBag.Serialize());

        protected override ValueTask<AgentSession> DeserializeSessionCoreAsync(JsonElement serializedState, JsonSerializerOptions? jsonSerializerOptions = null, CancellationToken cancellationToken = default) =>
            new(new TurnCountingSession(AgentSessionStateBag.Deserialize(serializedState)));

        protected override Task<AgentResponse> RunCoreAsync(IEnumerable<ChatMessage> messages, AgentSession? session = null, AgentRunOptions? options = null, CancellationToken cancellationToken = default) =>
            throw new NotSupportedException();

        protected override async IAsyncEnumerable<AgentResponseUpdate> RunCoreStreamingAsync(
            IEnumerable<ChatMessage> messages,
            AgentSession? session = null,
            AgentRunOptions? options = null,
            [EnumeratorCancellation] CancellationToken cancellationToken = default)
        {
            probe.AgentStarted.TrySetResult();
            await probe.ReleaseAgent.Task.ConfigureAwait(false);
            probe.DependencyDisposedWhenRunFinished = dependency.IsDisposed;
            yield return new AgentResponseUpdate
            {
                MessageId = "message-1",
                Role = ChatRole.Assistant,
                Contents = [new TextContent("done")]
            };
        }
    }

    [SuppressMessage("Performance", "CA1812:Avoid uninstantiated internal classes", Justification = "Instantiated via dependency injection")]
    private sealed class RequestDependency;

    private sealed class TurnCountingAgent(string? name) : AIAgent
    {
        public override string? Name => name;

        protected override ValueTask<AgentSession> CreateSessionCoreAsync(CancellationToken cancellationToken = default) =>
            new(new TurnCountingSession());

        protected override ValueTask<JsonElement> SerializeSessionCoreAsync(AgentSession session, JsonSerializerOptions? jsonSerializerOptions = null, CancellationToken cancellationToken = default) =>
            new(session.StateBag.Serialize());

        protected override ValueTask<AgentSession> DeserializeSessionCoreAsync(JsonElement serializedState, JsonSerializerOptions? jsonSerializerOptions = null, CancellationToken cancellationToken = default) =>
            new(new TurnCountingSession(AgentSessionStateBag.Deserialize(serializedState)));

        protected override Task<AgentResponse> RunCoreAsync(IEnumerable<ChatMessage> messages, AgentSession? session = null, AgentRunOptions? options = null, CancellationToken cancellationToken = default) =>
            throw new NotSupportedException();

        protected override async IAsyncEnumerable<AgentResponseUpdate> RunCoreStreamingAsync(
            IEnumerable<ChatMessage> messages,
            AgentSession? session = null,
            AgentRunOptions? options = null,
            [EnumeratorCancellation] CancellationToken cancellationToken = default)
        {
            int turn = 1;
            if (session is not null)
            {
                if (session.StateBag.TryGetValue("turn", out string? previousTurn))
                {
                    turn = int.Parse(previousTurn!, CultureInfo.InvariantCulture) + 1;
                }

                session.StateBag.SetValue("turn", turn.ToString(CultureInfo.InvariantCulture));
            }

            await Task.Yield();
            yield return new AgentResponseUpdate
            {
                MessageId = "message-1",
                Role = ChatRole.Assistant,
                Contents = [new TextContent($"{name} turn {turn}")]
            };
        }
    }

    private sealed class TurnCountingSession : AgentSession
    {
        public TurnCountingSession()
        {
        }

        public TurnCountingSession(AgentSessionStateBag stateBag)
            : base(stateBag)
        {
        }
    }
}
