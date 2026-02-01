// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Net;
using System.Net.Http;
using System.Runtime.CompilerServices;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using FluentAssertions;
using Microsoft.Agents.AI.AGUI;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Hosting.Server;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Routing;
using Microsoft.AspNetCore.TestHost;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.DependencyInjection;

namespace Microsoft.Agents.AI.Hosting.AGUI.AspNetCore.IntegrationTests;

public sealed class DynamicAgentResolutionTests : IAsyncDisposable
{
    private WebApplication? _app;
    private HttpClient? _client;

    [Fact]
    public async Task DynamicResolution_ReturnsCorrectAgent_BasedOnRouteParameterAsync()
    {
        // Arrange
        await this.SetupTestServerWithDynamicAgentsAsync();

        // Act - Request agent1
        AGUIChatClient chatClient1 = new(this._client!, "/agents/agent1", null);
        AIAgent agent1 = chatClient1.CreateAIAgent(name: "client1", description: "Test");
        AgentThread thread1 = agent1.GetNewThread();

        List<AgentRunResponseUpdate> updates = [];
        await foreach (AgentRunResponseUpdate update in agent1.RunStreamingAsync(
            [new ChatMessage(ChatRole.User, "hello")], thread1))
        {
            updates.Add(update);
        }

        // Assert
        AgentRunResponse response = updates.ToAgentRunResponse();
        response.Messages.Should().HaveCount(1);
        response.Messages[0].Text.Should().Be("Hello from Agent 1!");
    }

    [Fact]
    public async Task DynamicResolution_Returns404_WhenAgentNotFoundAsync()
    {
        // Arrange
        await this.SetupTestServerWithDynamicAgentsAsync();

        // Act
        AGUIChatClient chatClient = new(this._client!, "/agents/nonexistent", null);
        AIAgent agent = chatClient.CreateAIAgent(name: "client", description: "Test");
        AgentThread thread = agent.GetNewThread();

        // Assert
        Func<Task> act = async () =>
        {
            await foreach (AgentRunResponseUpdate _ in agent.RunStreamingAsync(
                [new ChatMessage(ChatRole.User, "hello")], thread))
            {
            }
        };

        await act.Should().ThrowAsync<HttpRequestException>()
            .Where(ex => ex.StatusCode == HttpStatusCode.NotFound);
    }

    [Fact]
    public async Task DynamicResolution_MultipleAgentsOnDifferentRoutes_WorkIndependentlyAsync()
    {
        // Arrange
        await this.SetupTestServerWithDynamicAgentsAsync();

        // Act - Use both agents
        AGUIChatClient chatClient1 = new(this._client!, "/agents/agent1", null);
        AGUIChatClient chatClient2 = new(this._client!, "/agents/agent2", null);

        AIAgent agent1 = chatClient1.CreateAIAgent(name: "client1", description: "Test");
        AIAgent agent2 = chatClient2.CreateAIAgent(name: "client2", description: "Test");

        List<AgentRunResponseUpdate> updates1 = [];
        List<AgentRunResponseUpdate> updates2 = [];

        await foreach (AgentRunResponseUpdate update in agent1.RunStreamingAsync(
            [new ChatMessage(ChatRole.User, "hello")], agent1.GetNewThread()))
        {
            updates1.Add(update);
        }

        await foreach (AgentRunResponseUpdate update in agent2.RunStreamingAsync(
            [new ChatMessage(ChatRole.User, "hello")], agent2.GetNewThread()))
        {
            updates2.Add(update);
        }

        // Assert
        AgentRunResponse response1 = updates1.ToAgentRunResponse();
        AgentRunResponse response2 = updates2.ToAgentRunResponse();

        response1.Messages[0].Text.Should().Be("Hello from Agent 1!");
        response2.Messages[0].Text.Should().Be("Hello from Agent 2!");
    }

    [Fact]
    public async Task DynamicResolution_WithIAGUIAgentResolver_ResolvesAgentFromDIAsync()
    {
        // Arrange
        await this.SetupTestServerWithResolverAsync();

        // Act
        AGUIChatClient chatClient = new(this._client!, "/agents/resolved-agent", null);
        AIAgent agent = chatClient.CreateAIAgent(name: "client", description: "Test");
        AgentThread thread = agent.GetNewThread();

        List<AgentRunResponseUpdate> updates = [];
        await foreach (AgentRunResponseUpdate update in agent.RunStreamingAsync(
            [new ChatMessage(ChatRole.User, "hello")], thread))
        {
            updates.Add(update);
        }

        // Assert
        AgentRunResponse response = updates.ToAgentRunResponse();
        response.Messages.Should().HaveCount(1);
        response.Messages[0].Text.Should().Be("Hello from Resolver Agent!");
    }

    [Fact]
    public async Task DynamicResolution_WithIAGUIAgentResolver_Returns404WhenResolverReturnsNullAsync()
    {
        // Arrange
        await this.SetupTestServerWithResolverAsync();

        // Act
        AGUIChatClient chatClient = new(this._client!, "/agents/unknown", null);
        AIAgent agent = chatClient.CreateAIAgent(name: "client", description: "Test");
        AgentThread thread = agent.GetNewThread();

        // Assert
        Func<Task> act = async () =>
        {
            await foreach (AgentRunResponseUpdate _ in agent.RunStreamingAsync(
                [new ChatMessage(ChatRole.User, "hello")], thread))
            {
            }
        };

        await act.Should().ThrowAsync<HttpRequestException>()
            .Where(ex => ex.StatusCode == HttpStatusCode.NotFound);
    }

    [Fact]
    public void AddAGUIWithResolver_RegistersResolverAsScoped()
    {
        // Arrange
        ServiceCollection services = new();

        // Act
        services.AddAGUI<TestAgentResolver>();

        // Assert
        ServiceDescriptor? descriptor = services.FirstOrDefault(
            d => d.ServiceType == typeof(IAGUIAgentResolver));

        descriptor.Should().NotBeNull();
        descriptor!.ImplementationType.Should().Be(typeof(TestAgentResolver));
        descriptor.Lifetime.Should().Be(ServiceLifetime.Scoped);
    }

    private async Task SetupTestServerWithDynamicAgentsAsync()
    {
        WebApplicationBuilder builder = WebApplication.CreateBuilder();
        builder.WebHost.UseTestServer();
        builder.Services.AddAGUI();

        this._app = builder.Build();

        // Map with dynamic agent resolution using factory delegate
        this._app.MapAGUI("/agents/{agentId}", (context, cancellationToken) =>
        {
            string? agentId = context.GetRouteValue("agentId")?.ToString();

            AIAgent? agent = agentId switch
            {
                "agent1" => new FakeAgent("Agent 1"),
                "agent2" => new FakeAgent("Agent 2"),
                _ => null
            };

            return new ValueTask<AIAgent?>(agent);
        });

        await this._app.StartAsync();

        TestServer testServer = this._app.Services.GetRequiredService<IServer>() as TestServer
            ?? throw new InvalidOperationException("TestServer not found");

        this._client = testServer.CreateClient();
        this._client.BaseAddress = new Uri("http://localhost");
    }

    private async Task SetupTestServerWithResolverAsync()
    {
        WebApplicationBuilder builder = WebApplication.CreateBuilder();
        builder.WebHost.UseTestServer();

        // Register using the generic AddAGUI<TResolver>() method
        builder.Services.AddAGUI<TestAgentResolver>();

        this._app = builder.Build();

        // Map using the resolver-based overload (no factory delegate)
        this._app.MapAGUI("/agents/{agentId}");

        await this._app.StartAsync();

        TestServer testServer = this._app.Services.GetRequiredService<IServer>() as TestServer
            ?? throw new InvalidOperationException("TestServer not found");

        this._client = testServer.CreateClient();
        this._client.BaseAddress = new Uri("http://localhost");
    }

    public async ValueTask DisposeAsync()
    {
        this._client?.Dispose();
        if (this._app != null)
        {
            await this._app.DisposeAsync();
        }
    }

    private sealed class FakeAgent : AIAgent
    {
        private readonly string _name;

        public FakeAgent(string name)
        {
            this._name = name;
        }

        protected override string? IdCore => $"fake-{this._name.Replace(" ", "-", StringComparison.Ordinal)}";
        public override string? Description => $"Fake agent: {this._name}";

        public override AgentThread GetNewThread() => new FakeInMemoryAgentThread();

        public override AgentThread DeserializeThread(JsonElement serializedThread, JsonSerializerOptions? jsonSerializerOptions = null)
            => new FakeInMemoryAgentThread(serializedThread, jsonSerializerOptions);

        protected override async Task<AgentRunResponse> RunCoreAsync(
            IEnumerable<ChatMessage> messages,
            AgentThread? thread = null,
            AgentRunOptions? options = null,
            CancellationToken cancellationToken = default)
        {
            List<AgentRunResponseUpdate> updates = [];
            await foreach (AgentRunResponseUpdate update in this.RunStreamingAsync(messages, thread, options, cancellationToken))
            {
                updates.Add(update);
            }
            return updates.ToAgentRunResponse();
        }

        protected override async IAsyncEnumerable<AgentRunResponseUpdate> RunCoreStreamingAsync(
            IEnumerable<ChatMessage> messages,
            AgentThread? thread = null,
            AgentRunOptions? options = null,
            [EnumeratorCancellation] CancellationToken cancellationToken = default)
        {
            await Task.CompletedTask;
            yield return new AgentRunResponseUpdate
            {
                MessageId = Guid.NewGuid().ToString("N"),
                Role = ChatRole.Assistant,
                Contents = [new TextContent($"Hello from {this._name}!")]
            };
        }

        private sealed class FakeInMemoryAgentThread : InMemoryAgentThread
        {
            public FakeInMemoryAgentThread() : base() { }
            public FakeInMemoryAgentThread(JsonElement serializedThread, JsonSerializerOptions? jsonSerializerOptions = null)
                : base(serializedThread, jsonSerializerOptions) { }
        }
    }

    // Instantiated via DI in SetupTestServerWithResolverAsync
#pragma warning disable CA1812
    private sealed class TestAgentResolver : IAGUIAgentResolver
#pragma warning restore CA1812
    {
        public ValueTask<AIAgent?> ResolveAgentAsync(HttpContext context, CancellationToken cancellationToken)
        {
            string? agentId = context.GetRouteValue("agentId")?.ToString();

            AIAgent? agent = agentId switch
            {
                "resolved-agent" => new FakeAgent("Resolver Agent"),
                _ => null
            };

            return new ValueTask<AIAgent?>(agent);
        }
    }
}
