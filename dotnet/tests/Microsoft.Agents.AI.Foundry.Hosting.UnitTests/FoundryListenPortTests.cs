// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections;
using System.Collections.Generic;
using System.Net;
using System.Reflection;
using Microsoft.AspNetCore.Server.Kestrel.Core;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Options;
using Moq;

namespace Microsoft.Agents.AI.Foundry.Hosting.UnitTests;

/// <summary>
/// Verifies that <c>AddFoundryResponses</c> adds a Kestrel listener on the Foundry hosted-runtime
/// port for a plain <c>WebApplication.CreateBuilder</c> (Tier 3) host, so a source (ZIP) deployed
/// agent passes the platform readiness probe with no Dockerfile pinning the port, and that it
/// leaves the addresses of a host running outside Foundry alone.
/// </summary>
/// <remarks>
/// Every case supplies its values through an in-memory <see cref="IConfiguration"/>, so no test
/// mutates the process environment and the class stays safe to run in parallel.
/// </remarks>
public sealed class FoundryListenPortTests
{
    private const string AspNetCoreUrlsKey = "ASPNETCORE_URLS";

    [Fact]
    public void AddFoundryResponses_WhenHosted_ListensOnFoundryPort()
    {
        // Arrange
        var services = CreateServices();

        // Act
        services.AddFoundryResponses();

        // Assert
        Assert.Equal([FoundryHostingExtensions.DefaultListenPort], GetCodeBackedPorts(services));
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
        Assert.Equal([FoundryHostingExtensions.DefaultListenPort], GetCodeBackedPorts(services));
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
        Assert.Empty(GetCodeBackedPorts(services));
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
            [AspNetCoreUrlsKey] = "http://+:80",
        });

        // Act
        services.AddFoundryResponses();

        // Assert
        Assert.Equal([FoundryHostingExtensions.DefaultListenPort], GetCodeBackedPorts(services));
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
        Assert.Equal([9099], GetCodeBackedPorts(services));
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
        var exception = Assert.Throws<InvalidOperationException>(() => GetCodeBackedPorts(services));
        Assert.Contains(port, exception.Message, StringComparison.Ordinal);
    }

    [Fact]
    public void AddFoundryResponses_CalledTwiceWhenHosted_ListensOnFoundryPortOnce()
    {
        // Arrange
        var services = CreateServices();

        // Act
        services.AddFoundryResponses();
        services.AddFoundryResponses();

        // Assert: a duplicate ListenAnyIP on the same port fails Kestrel startup with
        // "address already in use", so the listener must be added exactly once.
        Assert.Equal([FoundryHostingExtensions.DefaultListenPort], GetCodeBackedPorts(services));
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

    /// <summary>
    /// Builds the service provider, resolves the applied <see cref="KestrelServerOptions"/>, and
    /// returns the ports of every code-configured listener (those added via <c>ListenAnyIP</c>).
    /// </summary>
    private static List<int> GetCodeBackedPorts(IServiceCollection services)
    {
        using var provider = services.BuildServiceProvider();
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
