// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Linq;
using System.Net;
using System.Threading.Tasks;
using Azure.AI.AgentServer.Responses;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.TestHost;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
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

    // ── /readiness auto-mapping (Foundry container-image-spec §2) ────────────────

    [Fact]
    public async Task MapFoundryResponses_MapsReadinessEndpoint_WhenTier3HostHasNotMappedItAsync()
    {
        // Arrange: Tier 3 host (WebApplication.CreateBuilder, no AgentHost) — Core SDK does
        // NOT map /readiness in this case, so MapFoundryResponses must cover the gap.
        using var host = await BuildTestHostAsync(static app => app.MapFoundryResponses());

        // Act
        var response = await host.GetTestClient().GetAsync(new Uri("/readiness", UriKind.Relative));

        // Assert
        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
    }

    [Fact]
    public async Task MapFoundryResponses_DoesNotDuplicateReadiness_WhenAlreadyMappedAsync()
    {
        // Arrange: developer already mapped /readiness with a custom body. The auto-map
        // must detect the existing route and leave it untouched (no AmbiguousMatchException
        // at runtime, no override of the developer's response).
        const string CustomBody = "ready-from-developer";
        using var host = await BuildTestHostAsync(static app =>
        {
            app.MapGet("/readiness", () => Results.Text("ready-from-developer"));
            app.MapFoundryResponses();
        });

        // Act
        var response = await host.GetTestClient().GetAsync(new Uri("/readiness", UriKind.Relative));

        // Assert
        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        var body = await response.Content.ReadAsStringAsync();
        Assert.Equal(CustomBody, body);
    }

    [Fact]
    public async Task MapFoundryResponses_CalledTwice_StillOnlyMapsReadinessOnceAsync()
    {
        // Arrange: defensive coverage for callers that map the responses pipeline twice
        // (e.g. once at the root and once under "openai/v1" in the existing AF samples).
        using var host = await BuildTestHostAsync(static app =>
        {
            app.MapFoundryResponses();
            app.MapFoundryResponses("openai/v1");
        });

        // Act + Assert: a single GET /readiness must succeed without ambiguous-match throw.
        var response = await host.GetTestClient().GetAsync(new Uri("/readiness", UriKind.Relative));
        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
    }

    private static async Task<IHost> BuildTestHostAsync(Action<WebApplication> configure)
    {
        var builder = WebApplication.CreateBuilder();
        builder.WebHost.UseTestServer();

        var mockAgent = new Mock<AIAgent>();
        mockAgent.SetupGet(a => a.Name).Returns("test-agent");
        builder.Services.AddFoundryResponses(mockAgent.Object);

        var app = builder.Build();
        configure(app);
        await app.StartAsync();
        return app;
    }
}
