// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Net;
using System.Net.Http;
using System.Net.Http.Headers;
using System.Threading.Tasks;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.TestHost;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.DependencyInjection;
using Moq;

namespace Microsoft.Agents.AI.DevUI.UnitTests;

public class DevUIAccessControlTests
{
    private static WebApplicationBuilder NewBuilder()
    {
        var builder = WebApplication.CreateBuilder();
        builder.WebHost.UseTestServer();

        var mockChatClient = new Mock<IChatClient>();
        var agent = new ChatClientAgent(mockChatClient.Object, "Test", "agent-name");
        builder.Services.AddKeyedSingleton<AIAgent>("agent-name", agent);

        return builder;
    }

    private static void SimulateRemoteIp(WebApplication app, IPAddress remoteIp)
    {
        app.Use(async (HttpContext ctx, RequestDelegate next) =>
        {
            ctx.Connection.RemoteIpAddress = remoteIp;
            await next(ctx);
        });
    }

    [Fact]
    public async Task NonLoopbackRequest_ReturnsForbiddenByDefaultAsync()
    {
        var builder = NewBuilder();
        builder.Services.AddDevUI();

        using var app = builder.Build();
        SimulateRemoteIp(app, IPAddress.Parse("192.0.2.1"));
        app.MapDevUI();
        await app.StartAsync();

        var response = await app.GetTestClient().GetAsync(new Uri("/v1/entities", UriKind.Relative));

        Assert.Equal(HttpStatusCode.Forbidden, response.StatusCode);
    }

    [Fact]
    public async Task NonLoopbackRequest_IsAllowedWhenAllowRemoteAccessAsync()
    {
        var builder = NewBuilder();
        builder.Services.AddDevUI(o => o.AllowRemoteAccess = true);

        using var app = builder.Build();
        SimulateRemoteIp(app, IPAddress.Parse("192.0.2.1"));
        app.MapDevUI();
        await app.StartAsync();

        var response = await app.GetTestClient().GetAsync(new Uri("/v1/entities", UriKind.Relative));

        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
    }

    [Fact]
    public async Task LoopbackRequest_WithAuthTokenSet_RequiresBearerHeaderAsync()
    {
        var builder = NewBuilder();
        builder.Services.AddDevUI(o => o.AuthToken = "secret-token");

        using var app = builder.Build();
        SimulateRemoteIp(app, IPAddress.Loopback);
        app.MapDevUI();
        await app.StartAsync();

        var response = await app.GetTestClient().GetAsync(new Uri("/v1/entities", UriKind.Relative));

        Assert.Equal(HttpStatusCode.Unauthorized, response.StatusCode);
    }

    [Fact]
    public async Task LoopbackRequest_WithCorrectBearerToken_SucceedsAsync()
    {
        var builder = NewBuilder();
        builder.Services.AddDevUI(o => o.AuthToken = "secret-token");

        using var app = builder.Build();
        SimulateRemoteIp(app, IPAddress.Loopback);
        app.MapDevUI();
        await app.StartAsync();

        using var request = new HttpRequestMessage(HttpMethod.Get, new Uri("/v1/entities", UriKind.Relative));
        request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", "secret-token");
        var response = await app.GetTestClient().SendAsync(request);

        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
    }

    [Fact]
    public async Task EnvironmentVariableToken_IsEnforcedWhenAuthTokenNotConfiguredAsync()
    {
        const string EnvVar = "DEVUI_AUTH_TOKEN";
        const string EnvToken = "env-token";
        var previous = Environment.GetEnvironmentVariable(EnvVar);
        Environment.SetEnvironmentVariable(EnvVar, EnvToken);

        WebApplication? app = null;
        try
        {
            var builder = NewBuilder();
            builder.Services.AddDevUI();

            app = builder.Build();

            // Force singleton construction so the env var is captured before we
            // restore it; otherwise tests running in parallel can pick up the
            // leaked DEVUI_AUTH_TOKEN.
            _ = app.Services.GetRequiredService<DevUIAuthFilter>();
        }
        finally
        {
            Environment.SetEnvironmentVariable(EnvVar, previous);
        }

        await using (app)
        {
            SimulateRemoteIp(app, IPAddress.Loopback);
            app.MapDevUI();
            await app.StartAsync();

            var missing = await app.GetTestClient().GetAsync(new Uri("/v1/entities", UriKind.Relative));
            Assert.Equal(HttpStatusCode.Unauthorized, missing.StatusCode);

            using var request = new HttpRequestMessage(HttpMethod.Get, new Uri("/v1/entities", UriKind.Relative));
            request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", EnvToken);
            var accepted = await app.GetTestClient().SendAsync(request);
            Assert.Equal(HttpStatusCode.OK, accepted.StatusCode);
        }
    }

    [Fact]
    public async Task MetaEndpoint_IsReachableWithoutAuthenticationAsync()
    {
        var builder = NewBuilder();
        builder.Services.AddDevUI(o => o.AuthToken = "secret-token");

        using var app = builder.Build();
        SimulateRemoteIp(app, IPAddress.Loopback);
        app.MapDevUI();
        await app.StartAsync();

        var response = await app.GetTestClient().GetAsync(new Uri("/meta", UriKind.Relative));

        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        var body = await response.Content.ReadAsStringAsync();
        Assert.Contains("\"auth_required\":true", body);
    }

    [Fact]
    public async Task LoopbackRequest_WithWrongBearerToken_ReturnsUnauthorizedAsync()
    {
        var builder = NewBuilder();
        builder.Services.AddDevUI(o => o.AuthToken = "secret-token");

        using var app = builder.Build();
        SimulateRemoteIp(app, IPAddress.Loopback);
        app.MapDevUI();
        await app.StartAsync();

        using var request = new HttpRequestMessage(HttpMethod.Get, new Uri("/v1/entities", UriKind.Relative));
        request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", "not-the-token");
        var response = await app.GetTestClient().SendAsync(request);

        Assert.Equal(HttpStatusCode.Unauthorized, response.StatusCode);
    }
}
