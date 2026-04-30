// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Linq;
using Azure.AI.AgentServer.Responses;
using Microsoft.Agents.AI.Foundry.Hosting;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.DependencyInjection;
using Moq;
using OpenAI.Responses;

namespace Microsoft.Agents.AI.Foundry.Hosting.UnitTests;

public class ServiceCollectionExtensionsTests
{
    [Fact]
    public void AddFoundryResponses_RegistersResponseHandler()
    {
        var services = new ServiceCollection();
        services.AddLogging();

        services.AddFoundryResponses();

        var descriptor = services.FirstOrDefault(
            d => d.ServiceType == typeof(ResponseHandler));
        Assert.NotNull(descriptor);
        Assert.Equal(typeof(AgentFrameworkResponseHandler), descriptor.ImplementationType);
    }

    [Fact]
    public void AddFoundryResponses_CalledTwice_RegistersOnce()
    {
        var services = new ServiceCollection();
        services.AddLogging();

        services.AddFoundryResponses();
        services.AddFoundryResponses();

        var count = services.Count(d => d.ServiceType == typeof(ResponseHandler));
        Assert.Equal(1, count);
    }

    [Fact]
    public void AddFoundryResponses_NullServices_ThrowsArgumentNullException()
    {
        Assert.Throws<ArgumentNullException>(
            () => FoundryHostingExtensions.AddFoundryResponses(null!));
    }

    [Fact]
    public void AddFoundryResponses_WithAgent_RegistersAgentAndHandler()
    {
        var services = new ServiceCollection();
        services.AddLogging();
        var mockAgent = new Mock<AIAgent>();

        services.AddFoundryResponses(mockAgent.Object);

        var handlerDescriptor = services.FirstOrDefault(
            d => d.ServiceType == typeof(ResponseHandler));
        Assert.NotNull(handlerDescriptor);

        var agentDescriptor = services.FirstOrDefault(
            d => d.ServiceType == typeof(AIAgent));
        Assert.NotNull(agentDescriptor);
    }

    [Fact]
    public void AddFoundryResponses_WithNullAgent_ThrowsArgumentNullException()
    {
        var services = new ServiceCollection();
        Assert.Throws<ArgumentNullException>(
            () => services.AddFoundryResponses(null!));
    }

    [Fact]
    public void ApplyOpenTelemetry_NonInstrumentedAgent_WrapsWithOpenTelemetryAgent()
    {
        var mockAgent = new Mock<AIAgent>();

        var result = FoundryHostingExtensions.ApplyOpenTelemetry(mockAgent.Object);

        Assert.NotNull(result.GetService<OpenTelemetryAgent>());
    }

    [Fact]
    public void ApplyOpenTelemetry_AlreadyInstrumentedAgent_ReturnsSameReference()
    {
        var mockAgent = new Mock<AIAgent>();
        var instrumented = mockAgent.Object.AsBuilder()
            .UseOpenTelemetry()
            .Build();

        var result = FoundryHostingExtensions.ApplyOpenTelemetry(instrumented);

        Assert.Same(instrumented, result);
    }

    [Fact]
    public void TryApplyUserAgent_AgentWithoutChatClient_NoOp()
    {
        // Arrange: agent.GetService<IChatClient>() returns null.
        var mockAgent = new Mock<AIAgent>();

        // Act
        var result = FoundryHostingExtensions.TryApplyUserAgent(mockAgent.Object);

        // Assert
        Assert.Same(mockAgent.Object, result);
    }

    [Fact]
    public void TryApplyUserAgent_AgentWithNonMeaiChatClient_NoOp()
    {
        // Arrange: chat client that does not return MEAI's OpenAIResponsesChatClient via GetService.
        var mockChatClient = new Mock<IChatClient>();
        mockChatClient.Setup(c => c.GetService(It.IsAny<Type>(), It.IsAny<object?>())).Returns(null!);

        var mockAgent = new Mock<AIAgent>();
        mockAgent.Setup(a => a.GetService(typeof(IChatClient), It.IsAny<object?>())).Returns(mockChatClient.Object);

        // Act
        var result = FoundryHostingExtensions.TryApplyUserAgent(mockAgent.Object);

        // Assert
        Assert.Same(mockAgent.Object, result);
    }

    [Fact]
    public void MeaiOpenAIResponsesChatClient_TypeFullName_ReflectionGuard()
    {
        // Guards the polyfill's reflection target type-name.
        var meaiType = typeof(MicrosoftExtensionsAIResponsesExtensions).Assembly
            .GetType("Microsoft.Extensions.AI.OpenAIResponsesChatClient");
        Assert.NotNull(meaiType);
        Assert.True(typeof(IChatClient).IsAssignableFrom(meaiType!),
            $"Expected MEAI {meaiType!.FullName} to implement IChatClient.");
    }
}
