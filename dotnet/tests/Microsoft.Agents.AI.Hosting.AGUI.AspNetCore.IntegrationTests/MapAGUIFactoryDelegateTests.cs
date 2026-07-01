// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Net.Http;
using System.Text;
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
/// Integration tests for the per-request factory-delegate overload of
/// <c>MapAGUI(endpoints, agentName, pattern, Func&lt;IServiceProvider, string, AIAgent&gt;)</c>.
/// Unlike the startup-capture overloads, the factory is invoked once per request from the request's
/// <see cref="IServiceProvider"/>.
/// </summary>
public sealed class MapAGUIFactoryDelegateTests : IAsyncDisposable
{
    private WebApplication? _app;
    private HttpClient? _client;

    [Fact]
    public async Task MapAGUI_WithFactoryDelegate_InvokesFactoryPerRequest_AndStreamsAsync()
    {
        // Arrange - map the endpoint with a factory that records how many times it is invoked.
        int factoryInvocations = 0;
        await this.SetupTestServerWithFactoryAsync((_, name) =>
        {
            Interlocked.Increment(ref factoryInvocations);
            return new FakeSessionAgent(name);
        });

        var chatClient = new AGUIChatClient(this._client!, "", null);
        AIAgent agent = chatClient.AsAIAgent(instructions: null, name: "assistant", description: "Sample assistant", tools: []);
        AgentSession session = await agent.CreateSessionAsync();

        // Act - two turns => two HTTP requests.
        List<AgentResponseUpdate> firstTurn = [];
        await foreach (AgentResponseUpdate update in agent.RunStreamingAsync([new ChatMessage(ChatRole.User, "First")], session, new AgentRunOptions(), CancellationToken.None))
        {
            firstTurn.Add(update);
        }

        List<AgentResponseUpdate> secondTurn = [];
        await foreach (AgentResponseUpdate update in agent.RunStreamingAsync([new ChatMessage(ChatRole.User, "Second")], session, new AgentRunOptions(), CancellationToken.None))
        {
            secondTurn.Add(update);
        }

        // Assert - the factory ran once per request (not captured once at startup), and the agent streamed.
        factoryInvocations.Should().Be(2, "the factory delegate is invoked per request");
        firstTurn.Should().NotBeEmpty();
        firstTurn.ToAgentResponse().Messages[0].Text.Should().Contain("Hello from session agent");
    }

    [Fact]
    public async Task MapAGUI_WithFactoryDelegate_WhenFactoryReturnsNull_FailsTheRequestAsync()
    {
        // Arrange - a factory that returns null should surface a clear failure when a request arrives.
        await this.SetupTestServerWithFactoryAsync((_, _) => null!);

        const string Json = """
            {"threadId":"t1","runId":"r1","messages":[{"id":"m1","role":"user","content":"hi"}],"tools":[],"context":[],"state":{}}
            """;
        using StringContent content = new(Json, Encoding.UTF8, "application/json");

        // Act
        Func<Task> act = async () =>
        {
            using HttpResponseMessage response = await this._client!.PostAsync((Uri?)null, content);
            response.EnsureSuccessStatusCode();
        };

        // Assert - the factory returning null surfaces a clear InvalidOperationException naming the agent.
        (await act.Should().ThrowAsync<InvalidOperationException>())
            .WithMessage("*factory for 'factory-agent' returned null*");
    }

    private async Task SetupTestServerWithFactoryAsync(Func<IServiceProvider, string, AIAgent> factory)
    {
        WebApplicationBuilder builder = WebApplication.CreateBuilder();
        builder.WebHost.UseTestServer();
        builder.Services.AddAGUI();

        this._app = builder.Build();

        // Per-request factory overload — no keyed AIAgent registration required.
        this._app.MapAGUI("factory-agent", "/agent", factory);

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
