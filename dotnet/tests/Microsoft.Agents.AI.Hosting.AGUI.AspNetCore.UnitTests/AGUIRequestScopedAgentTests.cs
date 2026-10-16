// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using System.Globalization;
using System.Net;
using System.Net.Http;
using System.Runtime.CompilerServices;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Routing;
using Microsoft.AspNetCore.TestHost;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;

namespace Microsoft.Agents.AI.Hosting.AGUI.AspNetCore.UnitTests;

/// <summary>
/// Verifies that AG-UI endpoints resolve hosted agents and their session services for each request.
/// </summary>
public sealed class AGUIRequestScopedAgentTests : IAsyncDisposable
{
    private WebApplication? _app;
    private HttpClient? _client;

    [Fact]
    public async Task MapAGUIServer_WithScopedAgent_ResolvesAgentFromRequestScopeAsync()
    {
        // Arrange
        ConcurrentQueue<TurnCountingAgent> createdAgents = new();
        await this.StartAsync(
            services =>
            {
                services.AddScoped<RequestDependency>();
                services.AddAIAgent(
                    "assistant",
                    (sp, name) =>
                    {
                        TurnCountingAgent agent = new(name, sp.GetRequiredService<RequestDependency>().Id);
                        createdAgents.Enqueue(agent);
                        return agent;
                    },
                    ServiceLifetime.Scoped)
                    .WithInMemorySessionStore(withIsolation: false);
            },
            app => app.MapAGUIServer("assistant", "/ag-ui"));

        // Act
        string firstResponse = await this.PostRunAsync("/ag-ui", "thread-1");
        string secondResponse = await this.PostRunAsync("/ag-ui", "thread-1");

        // Assert
        TurnCountingAgent[] agents = [.. createdAgents];
        Assert.Equal(2, agents.Length);
        Assert.NotEqual(agents[0].Id, agents[1].Id);
        Assert.NotEqual(agents[0].Label, agents[1].Label);
        Assert.Contains("assistant turn 1", firstResponse);
        Assert.Contains("assistant turn 2", secondResponse);
    }

    [Fact]
    public async Task MapAGUIServer_WithHostedAgentBuilder_ResolvesTransientAgentPerRequestAsync()
    {
        // Arrange
        int createdAgents = 0;
        IHostedAgentBuilder? agentBuilder = null;
        await this.StartAsync(
            services =>
            {
                agentBuilder = services.AddAIAgent(
                    "assistant",
                    (_, name) =>
                    {
                        Interlocked.Increment(ref createdAgents);
                        return new TurnCountingAgent(name);
                    },
                    ServiceLifetime.Transient)
                    .WithInMemorySessionStore(withIsolation: false);
            },
            app => app.MapAGUIServer(agentBuilder!, "/ag-ui"));

        // Act
        await this.PostRunAsync("/ag-ui", "thread-1");
        string secondResponse = await this.PostRunAsync("/ag-ui", "thread-1");

        // Assert
        Assert.Equal(2, createdAgents);
        Assert.Contains("assistant turn 2", secondResponse);
    }

    [Fact]
    public async Task MapAGUIServer_WithSingletonHostedAgentBuilder_ResolvesAgentOnceAtMapTimeAsync()
    {
        // Arrange
        int createdAgents = 0;
        IHostedAgentBuilder? agentBuilder = null;
        await this.StartAsync(
            services =>
            {
                agentBuilder = services.AddAIAgent(
                    "assistant",
                    (_, name) =>
                    {
                        Interlocked.Increment(ref createdAgents);
                        return new TurnCountingAgent(name);
                    })
                    .WithInMemorySessionStore(withIsolation: false);
            },
            app =>
            {
                app.MapAGUIServer(agentBuilder!, "/ag-ui");
                Assert.Equal(1, createdAgents);
            });

        // Act
        await this.PostRunAsync("/ag-ui", "thread-1");
        string secondResponse = await this.PostRunAsync("/ag-ui", "thread-1");

        // Assert
        Assert.Equal(1, createdAgents);
        Assert.Contains("assistant turn 2", secondResponse);
    }

    [Fact]
    public async Task MapAGUIServer_WithAgent_ResolvesScopedSessionStoreFromRequestScopeAsync()
    {
        // Arrange
        InMemoryAgentSessionStore sharedStore = new();
        int createdStores = 0;
        TurnCountingAgent agent = new("assistant");
        await this.StartAsync(
            services => services.AddKeyedScoped<AgentSessionStore>("assistant", (_, _) =>
            {
                Interlocked.Increment(ref createdStores);
                return sharedStore;
            }),
            app => app.MapAGUIServer("/ag-ui", agent));

        // Act
        await this.PostRunAsync("/ag-ui", "thread-1");
        string secondResponse = await this.PostRunAsync("/ag-ui", "thread-1");

        // Assert
        Assert.Equal(2, createdStores);
        Assert.Contains("assistant turn 2", secondResponse);
    }

    [Fact]
    public async Task MapAGUIServer_WithUnregisteredAgentName_ThrowsAtMapTimeAsync()
    {
        // Arrange
        await using WebApplication app = CreateBuilder().Build();

        // Act & Assert
        InvalidOperationException exception = Assert.Throws<InvalidOperationException>(() => app.MapAGUIServer("missing", "/ag-ui"));
        Assert.Contains("missing", exception.Message);
    }

    [Fact]
    public async Task MapAGUIServer_WithAgentSelector_SelectsAgentFromRouteValueAsync()
    {
        // Arrange
        await this.StartAsync(
            services =>
            {
                services.AddAIAgent("alpha", (_, name) => new TurnCountingAgent(name), ServiceLifetime.Scoped);
                services.AddAIAgent("beta", (_, name) => new TurnCountingAgent(name), ServiceLifetime.Scoped);
            },
            app => app.MapAGUIServer("/agents/{agentId}/ag-ui", SelectAgentFromRoute));

        // Act
        string alphaResponse = await this.PostRunAsync("/agents/alpha/ag-ui", "thread-1");
        string betaResponse = await this.PostRunAsync("/agents/beta/ag-ui", "thread-1");

        // Assert
        Assert.Contains("alpha turn 1", alphaResponse);
        Assert.Contains("beta turn 1", betaResponse);
    }

    [Fact]
    public async Task MapAGUIServer_WithAgentSelectorReturningNull_ReturnsNotFoundWithoutLoadingSessionAsync()
    {
        // Arrange
        int sessionStoreResolutions = 0;
        await this.StartAsync(
            services => services.AddKeyedScoped<AgentSessionStore>(KeyedService.AnyKey, (_, _) =>
            {
                Interlocked.Increment(ref sessionStoreResolutions);
                return new InMemoryAgentSessionStore();
            }),
            app => app.MapAGUIServer("/agents/{agentId}/ag-ui", _ => null));

        // Act
        using HttpResponseMessage response = await this.SendRunAsync("/agents/unknown/ag-ui", "thread-1");

        // Assert
        Assert.Equal(HttpStatusCode.NotFound, response.StatusCode);
        Assert.Equal(0, sessionStoreResolutions);
    }

    [Fact]
    public async Task MapAGUIServer_WithAgentSelector_PersistsSessionsAcrossNewAgentInstancesAsync()
    {
        // Arrange
        await this.StartAsync(
            services => services.AddKeyedSingleton<AgentSessionStore>("dynamic", new InMemoryAgentSessionStore()),
            app => app.MapAGUIServer("/ag-ui", _ => new TurnCountingAgent("dynamic")));

        // Act
        string firstResponse = await this.PostRunAsync("/ag-ui", "thread-1");
        string secondResponse = await this.PostRunAsync("/ag-ui", "thread-1");
        string otherThreadResponse = await this.PostRunAsync("/ag-ui", "thread-2");

        // Assert
        Assert.Contains("dynamic turn 1", firstResponse);
        Assert.Contains("dynamic turn 2", secondResponse);
        Assert.Contains("dynamic turn 1", otherThreadResponse);
    }

    [Fact]
    public async Task MapAGUIServer_WithAgentSelectorReturningUnnamedAgent_FailsRequestAsync()
    {
        // Arrange
        await this.StartAsync(
            _ => { },
            app => app.MapAGUIServer("/ag-ui", _ => new TurnCountingAgent(name: null)));

        // Act & Assert
        InvalidOperationException exception = await Assert.ThrowsAsync<InvalidOperationException>(() => this.SendRunAsync("/ag-ui", "thread-1"));
        Assert.Contains("stable name", exception.Message);
    }

    public async ValueTask DisposeAsync()
    {
        this._client?.Dispose();
        if (this._app is not null)
        {
            await this._app.DisposeAsync();
        }
    }

    private static AIAgent? SelectAgentFromRoute(HttpContext context) =>
        context.GetRouteValue("agentId") is string agentId
            ? context.RequestServices.GetKeyedService<AIAgent>(agentId)
            : null;

    private static WebApplicationBuilder CreateBuilder()
    {
        WebApplicationBuilder builder = WebApplication.CreateBuilder();
        builder.WebHost.UseTestServer();
        builder.Host.UseDefaultServiceProvider(options =>
        {
            options.ValidateScopes = true;
            options.ValidateOnBuild = true;
        });
        builder.Services.AddAGUIServer();
        return builder;
    }

    private async Task StartAsync(Action<IServiceCollection> configureServices, Action<WebApplication> mapEndpoints)
    {
        WebApplicationBuilder builder = CreateBuilder();
        configureServices(builder.Services);

        this._app = builder.Build();
        mapEndpoints(this._app);
        await this._app.StartAsync();

        this._client = this._app.GetTestClient();
    }

    private async Task<string> PostRunAsync(string path, string threadId)
    {
        using HttpResponseMessage response = await this.SendRunAsync(path, threadId);
        response.EnsureSuccessStatusCode();
        return await response.Content.ReadAsStringAsync();
    }

    private async Task<HttpResponseMessage> SendRunAsync(string path, string threadId)
    {
        string json = $$$"""
            {"threadId":"{{{threadId}}}","runId":"{{{Guid.NewGuid():N}}}","messages":[{"id":"m1","role":"user","content":"hi"}],"tools":[],"context":[],"state":{}}
            """;
        using StringContent content = new(json, Encoding.UTF8, "application/json");
        return await this._client!.PostAsync(new Uri(path, UriKind.Relative), content);
    }

    [SuppressMessage("Performance", "CA1812:Avoid uninstantiated internal classes", Justification = "Instantiated via dependency injection")]
    private sealed class RequestDependency
    {
        public string Id { get; } = Guid.NewGuid().ToString("N");
    }

    private sealed class TurnCountingAgent(string? name, string? label = null) : AIAgent
    {
        public override string? Name => name;

        public string? Label => label;

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
