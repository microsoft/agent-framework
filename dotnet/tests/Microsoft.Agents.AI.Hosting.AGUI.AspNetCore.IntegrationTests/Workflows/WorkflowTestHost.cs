// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Net.Http;
using System.Threading.Tasks;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Hosting.Server;
using Microsoft.AspNetCore.TestHost;
using Microsoft.Extensions.DependencyInjection;

namespace Microsoft.Agents.AI.Hosting.AGUI.AspNetCore.IntegrationTests.Workflows;

internal sealed class WorkflowTestHost : IAsyncDisposable
{
    private readonly WebApplication _app;

    private WorkflowTestHost(WebApplication app, HttpClient client)
    {
        this._app = app;
        this.Client = client;
    }

    public HttpClient Client { get; }

    public static async Task<WorkflowTestHost> StartAsync(AIAgent agent, bool persistSession = false)
    {
        WebApplicationBuilder builder = WebApplication.CreateBuilder();
        builder.WebHost.UseTestServer();
        builder.Services.AddAGUIServer();

        if (persistSession)
        {
            string agentName = agent.Name ?? throw new InvalidOperationException("A named agent is required for session persistence.");
            builder.Services.AddAIAgent(agentName, (_, _) => agent)
                .WithInMemorySessionStore(withIsolation: false);
        }

        WebApplication app = builder.Build();
        if (persistSession)
        {
            app.MapAGUIServer(agent.Name!, "/agent");
        }
        else
        {
            app.MapAGUIServer("/agent", agent);
        }
        await app.StartAsync();

        TestServer server = app.Services.GetRequiredService<IServer>() as TestServer
            ?? throw new InvalidOperationException("TestServer not found.");
        HttpClient client = server.CreateClient();
        client.BaseAddress = new Uri("http://localhost/agent");
        return new WorkflowTestHost(app, client);
    }

    public async ValueTask DisposeAsync()
    {
        this.Client.Dispose();
        await this._app.DisposeAsync();
    }
}
