// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Net.Http;
using System.Text.RegularExpressions;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Foundry.Hosting;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Hosting.Server;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.TestHost;
using Microsoft.Extensions.DependencyInjection;
using Moq;

namespace Microsoft.Agents.AI.Foundry.UnitTests.Hosting;

/// <summary>
/// Tests for the <c>AgentFrameworkUserAgentMiddleware</c> registered by
/// <see cref="FoundryHostingExtensions.MapFoundryResponses"/>.
/// </summary>
public sealed partial class UserAgentMiddlewareTests : IAsyncDisposable
{
    private const string VersionedUserAgentPattern = @"agent-framework-dotnet/\d+\.\d+\.\d+(-[\w.]+)?";

    private WebApplication? _app;
    private HttpClient? _httpClient;

    public async ValueTask DisposeAsync()
    {
        this._httpClient?.Dispose();
        if (this._app != null)
        {
            await this._app.DisposeAsync();
        }
    }

    [Fact]
    public async Task MapFoundryResponses_NoUserAgentHeader_SetsAgentFrameworkUserAgentAsync()
    {
        // Arrange
        await this.CreateTestServerAsync();

        using var request = new HttpRequestMessage(HttpMethod.Get, "/test-ua");

        // Act
        var response = await this._httpClient!.SendAsync(request);
        var userAgent = await response.Content.ReadAsStringAsync();

        // Assert
        Assert.Matches(VersionedUserAgentPattern, userAgent);
    }

    [Fact]
    public async Task MapFoundryResponses_WithExistingUserAgent_AppendsAgentFrameworkUserAgentAsync()
    {
        // Arrange
        await this.CreateTestServerAsync();

        using var request = new HttpRequestMessage(HttpMethod.Get, "/test-ua");
        request.Headers.TryAddWithoutValidation("User-Agent", "MyApp/1.0");

        // Act
        var response = await this._httpClient!.SendAsync(request);
        var userAgent = await response.Content.ReadAsStringAsync();

        // Assert
        Assert.StartsWith("MyApp/1.0", userAgent);
        Assert.Matches(VersionedUserAgentPattern, userAgent);
    }

    [Fact]
    public async Task MapFoundryResponses_AlreadyContainsUserAgent_DoesNotDuplicateAsync()
    {
        // Arrange
        await this.CreateTestServerAsync();

        // First request to capture the actual middleware-generated value
        using var firstRequest = new HttpRequestMessage(HttpMethod.Get, "/test-ua");
        var firstResponse = await this._httpClient!.SendAsync(firstRequest);
        var middlewareValue = await firstResponse.Content.ReadAsStringAsync();

        // Act: send a second request that already contains the middleware value
        using var secondRequest = new HttpRequestMessage(HttpMethod.Get, "/test-ua");
        secondRequest.Headers.TryAddWithoutValidation("User-Agent", $"MyApp/2.0 {middlewareValue}");
        var secondResponse = await this._httpClient!.SendAsync(secondRequest);
        var userAgent = await secondResponse.Content.ReadAsStringAsync();

        // Assert: should remain unchanged (no duplication)
        Assert.Equal($"MyApp/2.0 {middlewareValue}", userAgent);
        Assert.Single(VersionedUserAgentRegex().Matches(userAgent));
    }

    [Fact]
    public async Task MapFoundryResponses_UserAgentValue_ContainsVersionAsync()
    {
        // Arrange
        await this.CreateTestServerAsync();

        using var request = new HttpRequestMessage(HttpMethod.Get, "/test-ua");

        // Act
        var response = await this._httpClient!.SendAsync(request);
        var userAgent = await response.Content.ReadAsStringAsync();

        // Assert: should match "agent-framework-dotnet/x.y.z" pattern
        Assert.Matches(VersionedUserAgentPattern, userAgent);
    }

    private async Task CreateTestServerAsync()
    {
        var builder = WebApplication.CreateBuilder();
        builder.WebHost.UseTestServer();

        var mockAgent = new Mock<AIAgent>();
        builder.Services.AddFoundryResponses(mockAgent.Object);

        this._app = builder.Build();
        this._app.MapFoundryResponses();

        // Test endpoint that echoes the User-Agent header after middleware processing
        this._app.MapGet("/test-ua", (HttpContext ctx) =>
            Results.Text(ctx.Request.Headers.UserAgent.ToString()));

        await this._app.StartAsync();

        var testServer = this._app.Services.GetRequiredService<IServer>() as TestServer
            ?? throw new InvalidOperationException("TestServer not found");

        this._httpClient = testServer.CreateClient();
    }

    [GeneratedRegex(VersionedUserAgentPattern)]
    private static partial Regex VersionedUserAgentRegex();
}
