// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Net.Http;
using System.Threading.Tasks;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Hosting.Server;
using Microsoft.AspNetCore.TestHost;
using Microsoft.Extensions.DependencyInjection;

namespace Microsoft.Agents.AI.Hosting.Channels.IntegrationTests.Support;

/// <summary>
/// In-process ASP.NET Core <see cref="TestServer"/> hosting an <see cref="AgentFrameworkHost"/>. Build via
/// <see cref="StartAsync"/>, issue HTTP requests through <see cref="Client"/>, and dispose to stop (which
/// fires channel shutdown callbacks).
/// </summary>
internal sealed class TestHostApp : IAsyncDisposable
{
    private WebApplication _app = null!;

    public HttpClient Client { get; private set; } = null!;

    public IServiceProvider Services => this._app.Services;

    /// <summary>
    /// Build and start a test host. <paramref name="configureHost"/> adds the target + channels;
    /// <paramref name="configureServices"/> registers any extra services (e.g. http context accessor).
    /// </summary>
    public static async Task<TestHostApp> StartAsync(
        Func<WebApplicationBuilder, IAgentFrameworkHostBuilder> configureHost,
        Action<IServiceCollection>? configureServices = null,
        Action<WebApplication>? configureApp = null)
    {
        var builder = WebApplication.CreateBuilder();
        builder.WebHost.UseTestServer();
        configureServices?.Invoke(builder.Services);

        configureHost(builder);

        var app = builder.Build();
        configureApp?.Invoke(app);
        app.MapAgentFrameworkHost();
        await app.StartAsync().ConfigureAwait(false);

        var server = app.Services.GetRequiredService<IServer>() as TestServer
            ?? throw new InvalidOperationException("TestServer not found.");

        return new TestHostApp
        {
            _app = app,
            Client = server.CreateClient(),
        };
    }

    public async ValueTask DisposeAsync()
    {
        this.Client?.Dispose();
        await this._app.StopAsync().ConfigureAwait(false);
        await this._app.DisposeAsync().ConfigureAwait(false);
    }
}
