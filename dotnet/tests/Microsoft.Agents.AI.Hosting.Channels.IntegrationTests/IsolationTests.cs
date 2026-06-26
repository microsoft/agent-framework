// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Net;
using System.Net.Http;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Hosting.Channels.IntegrationTests.Support;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;

namespace Microsoft.Agents.AI.Hosting.Channels.IntegrationTests;

/// <summary>
/// End-to-end coverage of the Foundry isolation-header lift: the host installs the lifting endpoint filter
/// only when <c>FOUNDRY_HOSTING_ENVIRONMENT</c> is set, then lifts <c>x-agent-user-isolation-key</c> /
/// <c>x-agent-chat-isolation-key</c> into <see cref="IsolationKeys.Current"/> for the request and resets it
/// afterwards. Runs in a non-parallel collection because the gate is a process-wide environment variable.
/// </summary>
[Collection("IsolationEnvironment")]
public class IsolationTests
{
    private const string FoundryFlag = "FOUNDRY_HOSTING_ENVIRONMENT";

    [Fact]
    public async Task Headers_IgnoredWithoutFoundryFlagAsync()
    {
        // Arrange - flag explicitly cleared
        using var env = new EnvVarScope(FoundryFlag, null);
        await using var app = await TestHostApp.StartAsync(b => b.AddAgentFrameworkHost(new FakeChatAgent()).AddChannel(new IsolationProbeChannel()));

        // Act
        var body = await GetProbeAsync(app, ("alice-uid", "general-cid"));

        // Assert - filter not installed, so Current stays null
        Assert.Equal("absent", body);
    }

    [Fact]
    public async Task BothHeaders_LiftedUnderFoundryFlagAsync()
    {
        // Arrange
        using var env = new EnvVarScope(FoundryFlag, "1");
        await using var app = await TestHostApp.StartAsync(b => b.AddAgentFrameworkHost(new FakeChatAgent()).AddChannel(new IsolationProbeChannel()));

        // Act
        var body = await GetProbeAsync(app, ("alice-uid", "general-cid"));

        // Assert
        Assert.Equal("user=alice-uid;chat=general-cid", body);
    }

    [Fact]
    public async Task OnlyUserHeader_LiftedAsync()
    {
        // Arrange
        using var env = new EnvVarScope(FoundryFlag, "1");
        await using var app = await TestHostApp.StartAsync(b => b.AddAgentFrameworkHost(new FakeChatAgent()).AddChannel(new IsolationProbeChannel()));

        // Act
        var body = await GetProbeAsync(app, ("alice-uid", null));

        // Assert
        Assert.Equal("user=alice-uid;chat=", body);
    }

    [Fact]
    public async Task OnlyChatHeader_LiftedAsync()
    {
        // Arrange
        using var env = new EnvVarScope(FoundryFlag, "1");
        await using var app = await TestHostApp.StartAsync(b => b.AddAgentFrameworkHost(new FakeChatAgent()).AddChannel(new IsolationProbeChannel()));

        // Act
        var body = await GetProbeAsync(app, (null, "general-cid"));

        // Assert
        Assert.Equal("user=;chat=general-cid", body);
    }

    [Fact]
    public async Task NoHeaders_AbsentUnderFlagAsync()
    {
        // Arrange
        using var env = new EnvVarScope(FoundryFlag, "1");
        await using var app = await TestHostApp.StartAsync(b => b.AddAgentFrameworkHost(new FakeChatAgent()).AddChannel(new IsolationProbeChannel()));

        // Act
        var body = await GetProbeAsync(app, (null, null));

        // Assert - filter is installed but a no-op without headers
        Assert.Equal("absent", body);
    }

    [Fact]
    public async Task EmptyUserHeader_TreatedAsAbsentAsync()
    {
        // Arrange
        using var env = new EnvVarScope(FoundryFlag, "1");
        await using var app = await TestHostApp.StartAsync(b => b.AddAgentFrameworkHost(new FakeChatAgent()).AddChannel(new IsolationProbeChannel()));

        // Act - present-but-empty user header must not bind an empty key
        var body = await GetProbeAsync(app, ("", "general-cid"));

        // Assert
        Assert.Equal("user=;chat=general-cid", body);
    }

    [Fact]
    public async Task ResetsAcrossRequests_NoLeakAsync()
    {
        // Arrange
        using var env = new EnvVarScope(FoundryFlag, "1");
        await using var app = await TestHostApp.StartAsync(b => b.AddAgentFrameworkHost(new FakeChatAgent()).AddChannel(new IsolationProbeChannel()));

        // Act - a bound request followed by a header-less request
        var first = await GetProbeAsync(app, ("alice-uid", null));
        var second = await GetProbeAsync(app, (null, null));

        // Assert - the second request does not inherit alice-uid
        Assert.Equal("user=alice-uid;chat=", first);
        Assert.Equal("absent", second);
    }

    [Fact]
    public async Task ConcurrentRequests_AreIsolatedAsync()
    {
        // Arrange
        using var env = new EnvVarScope(FoundryFlag, "1");
        await using var app = await TestHostApp.StartAsync(b => b.AddAgentFrameworkHost(new FakeChatAgent()).AddChannel(new IsolationProbeChannel()));

        // Act - parallel requests with distinct user keys must not bleed
        var alice = GetProbeAsync(app, ("alice-uid", null));
        var bob = GetProbeAsync(app, ("bob-uid", null));
        var results = await Task.WhenAll(alice, bob);

        // Assert
        Assert.Equal("user=alice-uid;chat=", results[0]);
        Assert.Equal("user=bob-uid;chat=", results[1]);
    }

    [Fact]
    public async Task Accessor_ResolvesFromDIAsync()
    {
        // Arrange / Act
        await using var app = await TestHostApp.StartAsync(b => b.AddAgentFrameworkHost(new FakeChatAgent()).AddChannel(new IsolationProbeChannel()));
        var accessor = app.Services.GetService<IIsolationKeysAccessor>();

        // Assert - the host registers the accessor for downstream providers
        Assert.NotNull(accessor);
    }

    [Fact]
    public async Task Host_StartsAndStopsUnderFoundryFlagAsync()
    {
        // Arrange / Act - installing the filter must not disturb host lifecycle (non-request scopes)
        using var env = new EnvVarScope(FoundryFlag, "1");
        await using var app = await TestHostApp.StartAsync(b => b.AddAgentFrameworkHost(new FakeChatAgent()).AddChannel(new IsolationProbeChannel()));

        // Act - a plain request still succeeds
        var body = await GetProbeAsync(app, (null, null));

        // Assert
        Assert.Equal("absent", body);
    }

    private static async Task<string> GetProbeAsync(TestHostApp app, (string? User, string? Chat) headers)
    {
        using var request = new HttpRequestMessage(HttpMethod.Get, new Uri("http://localhost/probe"));
        if (headers.User is not null)
        {
            request.Headers.TryAddWithoutValidation(IsolationKeys.UserHeader, headers.User);
        }

        if (headers.Chat is not null)
        {
            request.Headers.TryAddWithoutValidation(IsolationKeys.ChatHeader, headers.Chat);
        }

        var response = await app.Client.SendAsync(request);
        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        return await response.Content.ReadAsStringAsync();
    }
}

/// <summary>Disables parallelization for isolation tests that mutate the process-wide Foundry env var.</summary>
[CollectionDefinition("IsolationEnvironment", DisableParallelization = true)]
public class IsolationEnvironmentDefinition
{
}
