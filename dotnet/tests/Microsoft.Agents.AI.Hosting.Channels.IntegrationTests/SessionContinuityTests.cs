// Copyright (c) Microsoft. All rights reserved.

using System.Net.Http;
using System.Text.Json;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Hosting.Channels.IntegrationTests.Support;
using Microsoft.Agents.AI.Hosting.Channels.Responses;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;

namespace Microsoft.Agents.AI.Hosting.Channels.IntegrationTests;

/// <summary>
/// Verifies the ADR-0027 session-continuity gate end to end: identical isolation keys resolve to the same
/// cached <see cref="AgentSession"/>, different keys partition, and <see cref="AgentFrameworkHost.ResetSessionAsync"/>
/// rotates the alias. The isolation key is stamped by trusted middleware (a run hook reading a header), not
/// from the request body.
/// </summary>
public class SessionContinuityTests
{
    private const string IsoHeader = "x-iso";

    [Fact]
    public async Task SameIsolationKey_ReusesSessionAsync()
    {
        // Arrange - counting agent returns the running turn count for its session
        await using var app = await StartAsync();

        // Act - two requests with the same isolation header
        var first = await PostAsync(app, "alice");
        var second = await PostAsync(app, "alice");

        // Assert - same cached session -> count increments
        Assert.Equal("1", first);
        Assert.Equal("2", second);
    }

    [Fact]
    public async Task DifferentIsolationKey_GetsFreshSessionAsync()
    {
        // Arrange
        await using var app = await StartAsync();

        // Act
        var alice = await PostAsync(app, "alice");
        var bob = await PostAsync(app, "bob");

        // Assert - different keys partition into different sessions
        Assert.Equal("1", alice);
        Assert.Equal("1", bob);
    }

    [Fact]
    public async Task ResetSession_RotatesAliasToFreshSessionAsync()
    {
        // Arrange
        await using var app = await StartAsync();
        var host = app.Services.GetRequiredService<AgentFrameworkHost>();

        // Act
        var first = await PostAsync(app, "alice");
        var second = await PostAsync(app, "alice");
        await host.ResetSessionAsync("alice");
        var afterReset = await PostAsync(app, "alice");

        // Assert
        Assert.Equal("1", first);
        Assert.Equal("2", second);
        Assert.Equal("1", afterReset);
    }

    private static Task<TestHostApp> StartAsync() => TestHostApp.StartAsync(
        b => b
            .AddAgentFrameworkHost(new CountingAgent())
            .AddResponsesChannel(o => o.RunHook = new HeaderIsolationRunHook(
                b.Services.BuildServiceProvider().GetRequiredService<AspNetCore.Http.IHttpContextAccessor>(),
                IsoHeader)),
        services => services.AddHttpContextAccessor());

    private static async Task<string> PostAsync(TestHostApp app, string isolationKey)
    {
        using var request = new HttpRequestMessage(HttpMethod.Post, new System.Uri("http://localhost/responses"))
        {
            Content = new StringContent("{ \"input\": \"hi\" }", System.Text.Encoding.UTF8, "application/json"),
        };
        request.Headers.Add(IsoHeader, isolationKey);
        var response = await app.Client.SendAsync(request);
        var body = await response.Content.ReadAsStringAsync();

        using var doc = JsonDocument.Parse(body);
        return doc.RootElement.GetProperty("output")[0].GetProperty("content")[0].GetProperty("text").GetString()!;
    }
}
