// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Net;
using System.Net.Http;
using System.Net.Http.Headers;
using System.Threading.Tasks;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.TestHost;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.DependencyInjection;
using Moq;

[assembly: Xunit.v3.Parallelization(Mode = Xunit.Sdk.ParallelMode.None)]

namespace Microsoft.Agents.AI.DevUI.UnitTests;

public class DevUIAccessControlTests
{
    private static WebApplicationBuilder NewBuilder(IPAddress? startupRemoteIp = null)
    {
        var builder = WebApplication.CreateBuilder();
        builder.WebHost.UseTestServer();

        if (startupRemoteIp is not null)
        {
            builder.Services.AddSingleton<IStartupFilter>(new RemoteIpStartupFilter(startupRemoteIp));
        }

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

    [Fact]
    public async Task StandardResponsesRoute_WithForeignHost_ReturnsForbiddenAsync()
    {
        // Arrange
        var builder = NewBuilder(IPAddress.Loopback);
        builder.Services.AddDevUI();
        using var app = builder.Build();
        app.MapPost("/v1/responses", () => Results.Ok());
        await app.StartAsync();
        using var request = new HttpRequestMessage(HttpMethod.Post, new Uri("/v1/responses", UriKind.Relative));
        request.Headers.Host = "attacker.example";

        // Act
        var response = await app.GetTestClient().SendAsync(request);

        // Assert
        Assert.Equal(HttpStatusCode.Forbidden, response.StatusCode);
    }

    [Theory]
    [InlineData("localhost")]
    [InlineData("127.0.0.1")]
    [InlineData("[::1]")]
    public async Task StandardResponsesRoute_WithLoopbackHost_SucceedsAsync(string host)
    {
        // Arrange
        var builder = NewBuilder(IPAddress.Loopback);
        builder.Services.AddDevUI();
        using var app = builder.Build();
        app.MapPost("/v1/responses", () => Results.Ok());
        await app.StartAsync();
        using var request = new HttpRequestMessage(HttpMethod.Post, new Uri("/v1/responses", UriKind.Relative));
        request.Headers.Host = host;

        // Act
        var response = await app.GetTestClient().SendAsync(request);

        // Assert
        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
    }

    [Fact]
    public async Task StandardResponsesRoute_WithForeignOrigin_ReturnsForbiddenBeforeHandlerAsync()
    {
        // Arrange
        var handlerInvoked = false;
        var builder = NewBuilder(IPAddress.Loopback);
        builder.Services.AddDevUI();
        using var app = builder.Build();
        app.MapPost("/v1/responses", () =>
        {
            handlerInvoked = true;
            return Results.Ok();
        });
        await app.StartAsync();
        using var request = new HttpRequestMessage(HttpMethod.Post, new Uri("/v1/responses", UriKind.Relative));
        request.Headers.TryAddWithoutValidation("Origin", "https://attacker.example");

        // Act
        var response = await app.GetTestClient().SendAsync(request);

        // Assert
        Assert.Equal(HttpStatusCode.Forbidden, response.StatusCode);
        Assert.False(handlerInvoked);
    }

    [Fact]
    public async Task StandardResponsesRoute_WithCrossSiteFetchMetadata_ReturnsForbiddenAsync()
    {
        // Arrange
        var builder = NewBuilder(IPAddress.Loopback);
        builder.Services.AddDevUI();
        using var app = builder.Build();
        app.MapPost("/v1/responses", () => Results.Ok());
        await app.StartAsync();
        using var request = new HttpRequestMessage(HttpMethod.Post, new Uri("/v1/responses", UriKind.Relative));
        request.Headers.TryAddWithoutValidation("Sec-Fetch-Site", "cross-site");

        // Act
        var response = await app.GetTestClient().SendAsync(request);

        // Assert
        Assert.Equal(HttpStatusCode.Forbidden, response.StatusCode);
    }

    [Fact]
    public async Task StandardResponsesRoute_WithMatchingOrigin_SucceedsAsync()
    {
        // Arrange
        var builder = NewBuilder(IPAddress.Loopback);
        builder.Services.AddDevUI();
        using var app = builder.Build();
        app.MapPost("/v1/responses", () => Results.Ok());
        await app.StartAsync();
        using var request = new HttpRequestMessage(HttpMethod.Post, new Uri("/v1/responses", UriKind.Relative));
        request.Headers.TryAddWithoutValidation("Origin", "http://localhost");

        // Act
        var response = await app.GetTestClient().SendAsync(request);

        // Assert
        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
    }

    [Fact]
    public async Task StandardResponsesRoute_WithoutBrowserHeaders_SucceedsAsync()
    {
        // Arrange
        var builder = NewBuilder(IPAddress.Loopback);
        builder.Services.AddDevUI();
        using var app = builder.Build();
        app.MapPost("/v1/responses", () => Results.Ok());
        await app.StartAsync();

        // Act
        var response = await app.GetTestClient().PostAsync(
            new Uri("/v1/responses", UriKind.Relative),
            content: null);

        // Assert
        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
    }

    [Fact]
    public async Task StandardConversationsDescendantRoute_WithForeignHost_ReturnsForbiddenAsync()
    {
        // Arrange
        var builder = NewBuilder(IPAddress.Loopback);
        builder.Services.AddDevUI();
        using var app = builder.Build();
        app.MapGet("/v1/conversations/conversation-id", () => Results.Ok());
        await app.StartAsync();
        using var request = new HttpRequestMessage(
            HttpMethod.Get,
            new Uri("/v1/conversations/conversation-id", UriKind.Relative));
        request.Headers.Host = "attacker.example";

        // Act
        var response = await app.GetTestClient().SendAsync(request);

        // Assert
        Assert.Equal(HttpStatusCode.Forbidden, response.StatusCode);
    }

    [Theory]
    [InlineData("/devui/")]
    [InlineData("/v1/entities")]
    public async Task DevUIRoute_WithConfiguredToken_RequiresBearerHeaderAsync(string path)
    {
        // Arrange
        var builder = NewBuilder();
        builder.Services.AddDevUI(options =>
        {
            options.AllowRemoteAccess = true;
            options.AuthToken = "secret-token";
        });
        using var app = builder.Build();
        app.MapDevUI();
        await app.StartAsync();

        // Act
        var response = await app.GetTestClient().GetAsync(new Uri(path, UriKind.Relative));

        // Assert
        Assert.Equal(HttpStatusCode.Unauthorized, response.StatusCode);
        Assert.Equal("Bearer", response.Headers.WwwAuthenticate.ToString());
    }

    [Theory]
    [InlineData("/v1/responses")]
    [InlineData("/v1/conversations")]
    public async Task StandardBackendRoute_WithConfiguredToken_DoesNotRequireBearerHeaderAsync(string path)
    {
        // Arrange
        var builder = NewBuilder();
        builder.Services.AddDevUI(options =>
        {
            options.AllowRemoteAccess = true;
            options.AuthToken = "secret-token";
        });
        using var app = builder.Build();
        app.MapPost(path, () => Results.Ok());
        await app.StartAsync();

        // Act
        var response = await app.GetTestClient().PostAsync(
            new Uri(path, UriKind.Relative),
            content: null);

        // Assert
        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        Assert.Empty(response.Headers.WwwAuthenticate);
    }

    [Fact]
    public async Task StandardResponsesRoute_WithRemoteAccess_SkipsDevUIAccessChecksAsync()
    {
        // Arrange
        var builder = NewBuilder(IPAddress.Parse("192.0.2.1"));
        builder.Services.AddDevUI(options =>
        {
            options.AllowRemoteAccess = true;
            options.AuthToken = "secret-token";
        });
        using var app = builder.Build();
        app.MapPost("/v1/responses", () => Results.Ok());
        await app.StartAsync();
        using var request = new HttpRequestMessage(HttpMethod.Post, new Uri("/v1/responses", UriKind.Relative));
        request.Headers.Host = "remote.example";
        request.Headers.TryAddWithoutValidation("Origin", "https://attacker.example");
        request.Headers.TryAddWithoutValidation("Sec-Fetch-Site", "cross-site");

        // Act
        var response = await app.GetTestClient().SendAsync(request);

        // Assert
        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
    }

    [Fact]
    public async Task StandardResponsesPreflight_WithConfiguredToken_ReachesHandlerAsync()
    {
        // Arrange
        var builder = NewBuilder(IPAddress.Loopback);
        builder.Services.AddDevUI(options => options.AuthToken = "secret-token");
        using var app = builder.Build();
        app.MapMethods("/v1/responses", [HttpMethods.Options], () => Results.NoContent());
        await app.StartAsync();
        using var request = new HttpRequestMessage(HttpMethod.Options, new Uri("/v1/responses", UriKind.Relative));
        request.Headers.TryAddWithoutValidation("Origin", "https://frontend.example");
        request.Headers.TryAddWithoutValidation("Access-Control-Request-Method", "POST");

        // Act
        var response = await app.GetTestClient().SendAsync(request);

        // Assert
        Assert.Equal(HttpStatusCode.NoContent, response.StatusCode);
        Assert.Empty(response.Headers.WwwAuthenticate);
    }

    [Fact]
    public async Task PathBaseStandardResponsesDescendantRoute_WithForeignHost_ReturnsForbiddenBeforeHandlerAsync()
    {
        // Arrange
        var handlerInvoked = false;
        var builder = NewBuilder(IPAddress.Loopback);
        builder.Services.AddDevUI();
        using var app = builder.Build();
        app.UsePathBase("/agent");
        app.MapPost("/v1/responses/response-id", () =>
        {
            handlerInvoked = true;
            return Results.Ok();
        });
        await app.StartAsync();
        using var request = new HttpRequestMessage(
            HttpMethod.Post,
            new Uri("/agent/v1/responses/response-id", UriKind.Relative));
        request.Headers.Host = "attacker.example";

        // Act
        var response = await app.GetTestClient().SendAsync(request);

        // Assert
        Assert.Equal(HttpStatusCode.Forbidden, response.StatusCode);
        Assert.False(handlerInvoked);
    }

    [Fact]
    public async Task PathBaseStandardConversationsRoute_WithLoopbackHost_ReachesHandlerAsync()
    {
        // Arrange
        var handlerInvoked = false;
        var builder = NewBuilder(IPAddress.Loopback);
        builder.Services.AddDevUI();
        using var app = builder.Build();
        app.UsePathBase("/agent");
        app.MapGet("/v1/conversations", () =>
        {
            handlerInvoked = true;
            return Results.Ok();
        });
        await app.StartAsync();
        using var request = new HttpRequestMessage(
            HttpMethod.Get,
            new Uri("/agent/v1/conversations", UriKind.Relative));
        request.Headers.Host = "localhost";

        // Act
        var response = await app.GetTestClient().SendAsync(request);

        // Assert
        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        Assert.True(handlerInvoked);
    }

    [Fact]
    public async Task PathBaseSimilarResponsesRoute_WithForeignHost_ReachesHandlerAsync()
    {
        // Arrange
        var handlerInvoked = false;
        var builder = NewBuilder(IPAddress.Loopback);
        builder.Services.AddDevUI();
        using var app = builder.Build();
        app.UsePathBase("/agent");
        app.MapPost("/v1/responses-other", () =>
        {
            handlerInvoked = true;
            return Results.Ok();
        });
        await app.StartAsync();
        using var request = new HttpRequestMessage(
            HttpMethod.Post,
            new Uri("/agent/v1/responses-other", UriKind.Relative));
        request.Headers.Host = "attacker.example";

        // Act
        var response = await app.GetTestClient().SendAsync(request);

        // Assert
        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        Assert.True(handlerInvoked);
    }

    [Fact]
    public async Task UnrelatedApplicationRoute_IsNotProtectedAsync()
    {
        // Arrange
        var builder = NewBuilder(IPAddress.Parse("192.0.2.1"));
        builder.Services.AddDevUI();
        using var app = builder.Build();
        app.MapPost("/application", () => Results.Ok());
        await app.StartAsync();
        using var request = new HttpRequestMessage(HttpMethod.Post, new Uri("/application", UriKind.Relative));
        request.Headers.Host = "attacker.example";
        request.Headers.TryAddWithoutValidation("Origin", "https://attacker.example");
        request.Headers.TryAddWithoutValidation("Sec-Fetch-Site", "cross-site");

        // Act
        var response = await app.GetTestClient().SendAsync(request);

        // Assert
        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
    }

    [Fact]
    public void AddDevUI_WhenCalledRepeatedly_RegistersOneStartupFilter()
    {
        // Arrange
        var services = new ServiceCollection();

        // Act
        services.AddDevUI();
        services.AddDevUI();
        using var provider = services.BuildServiceProvider();
        var startupFilters = provider.GetServices<IStartupFilter>();

        // Assert
        Assert.Single(startupFilters, filter => filter is DevUIAccessControlStartupFilter);
    }

    private sealed class RemoteIpStartupFilter(IPAddress remoteIp) : IStartupFilter
    {
        public Action<IApplicationBuilder> Configure(Action<IApplicationBuilder> next)
            => app =>
            {
                app.Use(async (context, following) =>
                {
                    context.Connection.RemoteIpAddress = remoteIp;
                    await following(context);
                });
                next(app);
            };
    }
}
