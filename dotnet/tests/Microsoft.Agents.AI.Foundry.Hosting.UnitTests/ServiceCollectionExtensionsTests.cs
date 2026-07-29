// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Linq;
using System.Net;
using System.Threading.Tasks;
using Azure.AI.AgentServer.Responses;
using Microsoft.Agents.AI.Workflows;
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
    public void AddFoundryResponses_WithAgent_CalledTwice_ThrowsActionable()
    {
        // Arrange: the single-agent extension is not composable; a second call must be rejected
        // with guidance to use the parameterless overload plus keyed agents for multiple agents.
        var services = new ServiceCollection();
        services.AddLogging();
        var agent = new Mock<AIAgent>().Object;

        services.AddFoundryResponses(agent);

        // Act + Assert
        var ex = Assert.Throws<InvalidOperationException>(() => services.AddFoundryResponses(agent));
        Assert.Contains("single-agent extension", ex.Message, StringComparison.OrdinalIgnoreCase);
        Assert.Contains("AddKeyedSingleton", ex.Message, StringComparison.Ordinal);
    }

    [Fact]
    public void AddFoundryResponses_ParameterlessThenWithAgent_Throws()
    {
        // Arrange: once the multi-agent path built the host-wide server, the single-agent extension
        // cannot be added on top of it.
        var services = new ServiceCollection();
        services.AddLogging();

        services.AddFoundryResponses();

        // Act + Assert
        Assert.Throws<InvalidOperationException>(
            () => services.AddFoundryResponses(new Mock<AIAgent>().Object));
    }

    [Fact]
    public void AddFoundryResponses_WithAgentThenParameterless_DoesNotThrow()
    {
        // Arrange: the single-agent extension builds the server; a later parameterless call (for
        // example from shared wiring) must be a safe no-op rather than a throw.
        var services = new ServiceCollection();
        services.AddLogging();
        services.AddFoundryResponses(new Mock<AIAgent>().Object);

        // Act
        var exception = Record.Exception(() => services.AddFoundryResponses());

        // Assert
        Assert.Null(exception);
        Assert.Equal(1, services.Count(d => d.ServiceType == typeof(ResponseHandler)));
    }

    [Fact]
    public void AddFoundryResponses_RegistersAgentRegistrationHealthCheck()
    {
        var services = new ServiceCollection();
        services.AddLogging();

        services.AddFoundryResponses();

        var provider = services.BuildServiceProvider();
        var options = provider.GetRequiredService<
            Microsoft.Extensions.Options.IOptions<
                Microsoft.Extensions.Diagnostics.HealthChecks.HealthCheckServiceOptions>>();
        Assert.Contains(options.Value.Registrations, r => r.Name == "foundry-agent-registration");
    }

    [Fact]
    public async Task ResilientWorkflowIdHealthCheck_SeesFactoryRegisteredAgentAsync()
    {
        // Arrange: resilient host with a workflow agent registered via a KEYED FACTORY (not a concrete
        // instance). Its step agents have auto-generated ids, which would break crash-recovery resume.
        var services = new ServiceCollection();
        services.AddLogging();
        services.AddFoundryResponses(o => o.ResilientBackground = true);
        services.AddKeyedSingleton<AIAgent>("wf", (sp, key) =>
        {
            var french = new StreamingTextAgent("french", "bonjour");
            var spanish = new StreamingTextAgent("spanish", "hola");
            return new WorkflowBuilder(french).AddEdge(french, spanish).Build().AsAIAgent(name: "wf-host");
        });

        var provider = services.BuildServiceProvider();
        var registration = provider
            .GetRequiredService<Microsoft.Extensions.Options.IOptions<
                Microsoft.Extensions.Diagnostics.HealthChecks.HealthCheckServiceOptions>>()
            .Value.Registrations.Single(r => r.Name == "foundry-resilient-workflow-ids");

        var check = registration.Factory(provider);
        var context = new Microsoft.Extensions.Diagnostics.HealthChecks.HealthCheckContext
        {
            Registration = new Microsoft.Extensions.Diagnostics.HealthChecks.HealthCheckRegistration(
                registration.Name,
                check,
                Microsoft.Extensions.Diagnostics.HealthChecks.HealthStatus.Unhealthy,
                tags: null),
        };

        // Act: resolving (not descriptor-reading) is what lets the check see a factory-registered agent.
        var result = await check.CheckHealthAsync(context);

        // Assert
        Assert.Equal(Microsoft.Extensions.Diagnostics.HealthChecks.HealthStatus.Unhealthy, result.Status);
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
        // Cast to bind the agent overload: the parameterless overload also accepts a single null
        // (as its optional configure callback), so the cast keeps this test targeting the agent path.
        Assert.Throws<ArgumentNullException>(
            () => services.AddFoundryResponses((AIAgent)null!));
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
