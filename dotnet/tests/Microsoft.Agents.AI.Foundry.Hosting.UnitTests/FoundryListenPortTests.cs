// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections;
using System.Collections.Generic;
using System.Net;
using System.Reflection;
using System.Threading.Tasks;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Server.Kestrel.Core;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Options;
using Moq;

namespace Microsoft.Agents.AI.Foundry.Hosting.UnitTests;

/// <summary>
/// Verifies that <c>AddFoundryResponses</c> adds a Kestrel listener on the Foundry hosted-runtime
/// port for a plain <c>WebApplication.CreateBuilder</c> (Tier 3) host, does not duplicate the
/// listener owned by <c>AgentHost.CreateBuilder</c> (Tier 2), and leaves the addresses of a host
/// running outside Foundry alone.
/// </summary>
/// <remarks>
/// Every case supplies its values through an in-memory <see cref="IConfiguration"/>, so no test
/// mutates the process environment and the class stays safe to run in parallel.
/// </remarks>
public sealed class FoundryListenPortTests
{
    [Fact]
    public void AddFoundryResponses_WhenHosted_ListensOnFoundryPort()
    {
        // Arrange
        var services = CreateServices();

        // Act
        services.AddFoundryResponses();

        // Assert
        Assert.Equal("http://+:8088", GetConfiguredListenUrl(services));
    }

    [Fact]
    public void AddFoundryResponses_WithAgentWhenHosted_ListensOnFoundryPort()
    {
        // Arrange
        var services = CreateServices();
        var mockAgent = new Mock<AIAgent>();
        mockAgent.SetupGet(a => a.Name).Returns("test-agent");

        // Act
        services.AddFoundryResponses(mockAgent.Object);

        // Assert
        Assert.Equal("http://+:8088", GetConfiguredListenUrl(services));
    }

    [Fact]
    public void AddFoundryResponses_WhenNotHosted_LeavesAddressesAlone()
    {
        // Arrange: outside a Foundry container the host keeps whatever addresses it resolved from
        // configuration, so registering the Responses protocol must not add a listener.
        var services = CreateServices(hosted: false);

        // Act
        services.AddFoundryResponses();

        // Assert
        Assert.Null(GetConfiguredListenUrl(services));
    }

    [Fact]
    public void AddFoundryResponses_WhenHostedWithAspNetCoreUrlsSet_StillListensOnFoundryPort()
    {
        // Arrange: the .NET base image used by source (ZIP) deploy sets ASPNETCORE_URLS to port 80.
        // Inside Foundry the listener must still be added, because a listener configured in code
        // takes precedence over that setting. Skipping it here would leave the container on port 80
        // and fail every invocation with HTTP 424 session_not_ready.
        var services = CreateServices(settings: new Dictionary<string, string?>
        {
            [WebHostDefaults.ServerUrlsKey] = "http://+:80",
        });

        // Act
        services.AddFoundryResponses();

        // Assert
        Assert.Equal("http://+:8088", GetConfiguredListenUrl(services));
    }

    [Fact]
    public void AddFoundryResponses_WhenHostedWithPortSet_ListensOnConfiguredPort()
    {
        // Arrange: the platform sets PORT only when it needs a port other than the default.
        var services = CreateServices(settings: new Dictionary<string, string?>
        {
            [FoundryHostingExtensions.ListenPortKey] = "9099",
        });

        // Act
        services.AddFoundryResponses();

        // Assert
        Assert.Equal("http://+:9099", GetConfiguredListenUrl(services));
    }

    [Theory]
    [InlineData("0")]
    [InlineData("65536")]
    [InlineData("not-a-port")]
    public void AddFoundryResponses_WhenHostedWithInvalidPort_Throws(string port)
    {
        // Arrange
        var services = CreateServices(settings: new Dictionary<string, string?>
        {
            [FoundryHostingExtensions.ListenPortKey] = port,
        });
        services.AddFoundryResponses();

        // Act & Assert
        var exception = Assert.Throws<InvalidOperationException>(() => GetConfiguredListenUrl(services));
        Assert.Contains(port, exception.Message, StringComparison.Ordinal);
    }

    [Fact]
    public void AddFoundryResponses_CalledTwiceWhenHosted_ConfiguresFoundryUrlIdempotently()
    {
        // Arrange
        var services = CreateServices();

        // Act
        services.AddFoundryResponses();
        services.AddFoundryResponses();

        // Assert
        Assert.Equal("http://+:8088", GetConfiguredListenUrl(services));
    }

    [Fact]
    public void AddFoundryResponses_WithStandaloneAgentServerCore_ListensOnFoundryPortOnce()
    {
        // Arrange
        var services = CreateServices();
        services.AddAgentServerCore();

        // Act
        services.AddFoundryResponses();

        // Assert
        Assert.Equal("http://+:8088", GetConfiguredListenUrl(services));
    }

    [Fact]
    public void AddFoundryResponses_WithStandaloneAgentServerCoreInstance_ListensOnFoundryPortOnce()
    {
        // Arrange
        var services = CreateServices();
        services.AddSingleton(new ServerVersionRegistry());
        services.AddAgentServerCore();

        // Act
        services.AddFoundryResponses();

        // Assert
        Assert.Equal("http://+:8088", GetConfiguredListenUrl(services));
    }

    [Fact]
    public async Task AddFoundryResponses_WithAgentHostBuilder_ListensOnFoundryPortOnceAsync()
    {
        // Arrange
        var builder = AgentHost.CreateBuilder(
        [
            $"--{FoundryHostingExtensions.FoundryHostingEnvironmentKey}=foundry",
        ]);
        var mockAgent = new Mock<AIAgent>();
        mockAgent.SetupGet(a => a.Name).Returns("test-agent");

        // Act
        builder.Services.AddFoundryResponses(mockAgent.Object);
        var app = builder.Build();

        // Assert
        try
        {
            Assert.Equal("http://+:8088", GetConfiguredListenUrl(app.App.Services));
            Assert.Equal([FoundryHostingExtensions.DefaultListenPort], GetCodeBackedPorts(app.App.Services));
        }
        finally
        {
            await app.App.DisposeAsync();
        }
    }

    /// <summary>
    /// Builds a service collection whose <see cref="IConfiguration"/> carries the supplied values,
    /// marking the process as Foundry-hosted unless <paramref name="hosted"/> says otherwise.
    /// </summary>
    private static ServiceCollection CreateServices(bool hosted = true, Dictionary<string, string?>? settings = null)
    {
        settings ??= [];
        if (hosted)
        {
            settings[FoundryHostingExtensions.FoundryHostingEnvironmentKey] = "foundry";
        }

        var services = new ServiceCollection();
        services.AddLogging();
        services.AddSingleton<IConfiguration>(new ConfigurationBuilder().AddInMemoryCollection(settings).Build());
        return services;
    }

    private static string? GetConfiguredListenUrl(IServiceCollection services)
    {
        using var provider = services.BuildServiceProvider();
        return GetConfiguredListenUrl(provider);
    }

    private static string? GetConfiguredListenUrl(IServiceProvider provider)
    {
        // ASP.NET resolves startup filters before reading this URL and starting the server.
        _ = provider.GetServices<IStartupFilter>();
        return provider.GetRequiredService<IConfiguration>()[WebHostDefaults.ServerUrlsKey];
    }

    /// <summary>
    /// Returns the ports of every code-configured listener, which are added via <c>ListenAnyIP</c>.
    /// </summary>
    private static List<int> GetCodeBackedPorts(IServiceProvider provider)
    {
        var options = provider.GetRequiredService<IOptions<KestrelServerOptions>>().Value;

        var property = typeof(KestrelServerOptions).GetProperty(
            "CodeBackedListenOptions",
            BindingFlags.Instance | BindingFlags.NonPublic);
        Assert.NotNull(property);

        var listenOptions = (IEnumerable)property!.GetValue(options)!;
        var ports = new List<int>();
        foreach (var listenOption in listenOptions)
        {
            if (listenOption.GetType().GetProperty("IPEndPoint")?.GetValue(listenOption) is IPEndPoint endpoint)
            {
                ports.Add(endpoint.Port);
            }
        }

        return ports;
    }
}
