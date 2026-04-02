// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Linq;
using Azure.AI.AgentServer.Responses;
using Microsoft.Extensions.DependencyInjection;
using Moq;

namespace Microsoft.Agents.AI.Hosting.AzureAIResponses.UnitTests;

public class ServiceCollectionExtensionsTests
{
    [Fact]
    public void AddAgentFrameworkHandler_RegistersResponseHandler()
    {
        var services = new ServiceCollection();
        services.AddLogging();

        services.AddAgentFrameworkHandler();

        var descriptor = services.FirstOrDefault(
            d => d.ServiceType == typeof(ResponseHandler));
        Assert.NotNull(descriptor);
        Assert.Equal(typeof(AgentFrameworkResponseHandler), descriptor.ImplementationType);
    }

    [Fact]
    public void AddAgentFrameworkHandler_CalledTwice_RegistersOnce()
    {
        var services = new ServiceCollection();
        services.AddLogging();

        services.AddAgentFrameworkHandler();
        services.AddAgentFrameworkHandler();

        var count = services.Count(d => d.ServiceType == typeof(ResponseHandler));
        Assert.Equal(1, count);
    }

    [Fact]
    public void AddAgentFrameworkHandler_NullServices_ThrowsArgumentNullException()
    {
        Assert.Throws<ArgumentNullException>(
            () => AgentFrameworkResponsesServiceCollectionExtensions.AddAgentFrameworkHandler(null!));
    }

    [Fact]
    public void AddAgentFrameworkHandler_WithAgent_RegistersAgentAndHandler()
    {
        var services = new ServiceCollection();
        services.AddLogging();
        var mockAgent = new Mock<AIAgent>();

        services.AddAgentFrameworkHandler(mockAgent.Object);

        var handlerDescriptor = services.FirstOrDefault(
            d => d.ServiceType == typeof(ResponseHandler));
        Assert.NotNull(handlerDescriptor);

        var agentDescriptor = services.FirstOrDefault(
            d => d.ServiceType == typeof(AIAgent));
        Assert.NotNull(agentDescriptor);
    }

    [Fact]
    public void AddAgentFrameworkHandler_WithNullAgent_ThrowsArgumentNullException()
    {
        var services = new ServiceCollection();
        Assert.Throws<ArgumentNullException>(
            () => services.AddAgentFrameworkHandler(null!));
    }
}
