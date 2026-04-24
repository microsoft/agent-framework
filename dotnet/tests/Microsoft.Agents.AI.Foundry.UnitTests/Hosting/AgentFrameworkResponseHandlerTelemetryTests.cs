// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Linq;
using System.Runtime.CompilerServices;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Azure.AI.AgentServer.Responses;
using Azure.AI.AgentServer.Responses.Models;
using Microsoft.Agents.AI.Foundry.Hosting;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging.Abstractions;
using Moq;
using OpenTelemetry;
using OpenTelemetry.Trace;
using MeaiTextContent = Microsoft.Extensions.AI.TextContent;

namespace Microsoft.Agents.AI.Foundry.UnitTests.Hosting;

/// <summary>
/// Tests that verify OTel spans are actually emitted and captured through the
/// <see cref="AgentFrameworkResponseHandler"/> pipeline when
/// <see cref="FoundryHostingExtensions.ApplyOpenTelemetry"/> wraps the resolved agent.
/// </summary>
public class AgentFrameworkResponseHandlerTelemetryTests
{
    /// <summary>
    /// The ActivitySource name used by ApplyOpenTelemetry() — equals AgentHostTelemetry.ResponsesSourceName.
    /// Declared as a constant so the TracerProvider and assertions reference the same literal.
    /// </summary>
    private const string ResponsesSourceName = "Azure.AI.AgentServer.Responses";

    [Fact]
    public async Task CreateAsync_DefaultAgent_EmitsInvokeAgentSpanAsync()
    {
        // Arrange
        var activities = new List<Activity>();
        using var tracerProvider = Sdk.CreateTracerProviderBuilder()
            .AddSource(ResponsesSourceName)
            .AddInMemoryExporter(activities)
            .Build();

        var agent = new TelemetryTestAgent();
        var services = new ServiceCollection();
        services.AddSingleton<AgentSessionStore>(new InMemoryAgentSessionStore());
        services.AddSingleton<AIAgent>(agent);
        var sp = services.BuildServiceProvider();

        var handler = new AgentFrameworkResponseHandler(sp, NullLogger<AgentFrameworkResponseHandler>.Instance);
        var (request, context) = BuildRequest();

        // Act — enumerate all events so the span completes before asserting
        await foreach (var _ in handler.CreateAsync(request, context, CancellationToken.None)) { }

        // Assert — filter by agent name to isolate this test's span from any parallel test spans
        var mySpan = Assert.Single(activities.Where(a => TelemetryTestAgent.AgentName.Equals(a.GetTagItem("gen_ai.agent.name"))).ToList());
        Assert.Equal("invoke_agent", mySpan.GetTagItem("gen_ai.operation.name"));
        Assert.NotNull(mySpan.GetTagItem("gen_ai.agent.id"));
    }

    [Fact]
    public async Task CreateAsync_KeyedAgent_EmitsInvokeAgentSpanAsync()
    {
        // Arrange
        var activities = new List<Activity>();
        using var tracerProvider = Sdk.CreateTracerProviderBuilder()
            .AddSource(ResponsesSourceName)
            .AddInMemoryExporter(activities)
            .Build();

        var agent = new TelemetryTestAgent();
        var services = new ServiceCollection();
        services.AddSingleton<AgentSessionStore>(new InMemoryAgentSessionStore());
        services.AddKeyedSingleton<AIAgent>("keyed-agent", agent);
        var sp = services.BuildServiceProvider();

        var handler = new AgentFrameworkResponseHandler(sp, NullLogger<AgentFrameworkResponseHandler>.Instance);
        var (request, context) = BuildRequest(agentKey: "keyed-agent");

        // Act
        await foreach (var _ in handler.CreateAsync(request, context, CancellationToken.None)) { }

        // Assert — filter by agent name to isolate this test's span
        var mySpan = Assert.Single(activities.Where(a => TelemetryTestAgent.AgentName.Equals(a.GetTagItem("gen_ai.agent.name"))).ToList());
        Assert.Equal("invoke_agent", mySpan.GetTagItem("gen_ai.operation.name"));
    }

    [Fact]
    public async Task CreateAsync_AlreadyInstrumentedAgent_EmitsSingleSpanPerRunAsync()
    {
        // Arrange — use a unique source for the pre-wrapped agent distinct from ResponsesSourceName.
        // If ApplyOpenTelemetry double-wraps, an extra span would appear on ResponsesSourceName.
        // If it correctly skips wrapping, only the pre-wrap's unique source emits spans.
        var preWrapSource = Guid.NewGuid().ToString();
        var preWrapActivities = new List<Activity>();
        var responsesActivities = new List<Activity>();

        using var preWrapProvider = Sdk.CreateTracerProviderBuilder()
            .AddSource(preWrapSource)
            .AddInMemoryExporter(preWrapActivities)
            .Build();

        using var responsesProvider = Sdk.CreateTracerProviderBuilder()
            .AddSource(ResponsesSourceName)
            .AddInMemoryExporter(responsesActivities)
            .Build();

        var innerAgent = new TelemetryTestAgent();
        var preWrapped = innerAgent.AsBuilder()
            .UseOpenTelemetry(sourceName: preWrapSource)
            .Build();

        var services = new ServiceCollection();
        services.AddSingleton<AgentSessionStore>(new InMemoryAgentSessionStore());
        services.AddSingleton(preWrapped);
        var sp = services.BuildServiceProvider();

        var handler = new AgentFrameworkResponseHandler(sp, NullLogger<AgentFrameworkResponseHandler>.Instance);

        // Act
        var (request, context) = BuildRequest();
        await foreach (var _ in handler.CreateAsync(request, context, CancellationToken.None)) { }

        // Assert — pre-wrap source emits exactly 1 span (agent ran)
        Assert.Single(preWrapActivities);
        Assert.Equal("invoke_agent", preWrapActivities[0].GetTagItem("gen_ai.operation.name"));

        // ResponsesSourceName emits 0 spans — ApplyOpenTelemetry skipped wrapping the pre-instrumented agent
        Assert.DoesNotContain(responsesActivities, a => TelemetryTestAgent.AgentName.Equals(a.GetTagItem("gen_ai.agent.name")));
    }

    [Fact]
    public async Task CreateAsync_DefaultAgent_SpanDisplayNameContainsAgentNameAsync()
    {
        // Arrange
        var activities = new List<Activity>();
        using var tracerProvider = Sdk.CreateTracerProviderBuilder()
            .AddSource(ResponsesSourceName)
            .AddInMemoryExporter(activities)
            .Build();

        var agent = new TelemetryTestAgent();
        var services = new ServiceCollection();
        services.AddSingleton<AgentSessionStore>(new InMemoryAgentSessionStore());
        services.AddSingleton<AIAgent>(agent);
        var sp = services.BuildServiceProvider();

        var handler = new AgentFrameworkResponseHandler(sp, NullLogger<AgentFrameworkResponseHandler>.Instance);
        var (request, context) = BuildRequest();

        // Act
        await foreach (var _ in handler.CreateAsync(request, context, CancellationToken.None)) { }

        // Assert — display name follows "invoke_agent {Name}({Id})" convention; filter by agent name to isolate
        var mySpan = Assert.Single(activities.Where(a => TelemetryTestAgent.AgentName.Equals(a.GetTagItem("gen_ai.agent.name"))).ToList());
        Assert.Contains("invoke_agent", mySpan.DisplayName, StringComparison.Ordinal);
        Assert.Contains(TelemetryTestAgent.AgentName, mySpan.DisplayName, StringComparison.Ordinal);
    }

    private static (CreateResponse request, ResponseContext context) BuildRequest(string? agentKey = null)
    {
        var request = agentKey is null
            ? new CreateResponse { Model = "test" }
            : new CreateResponse { Model = "test", AgentReference = new AgentReference(agentKey) };

        request.Input = BinaryData.FromObjectAsJson(new[]
        {
            new { type = "message", id = "msg_1", status = "completed", role = "user",
                  content = new[] { new { type = "input_text", text = "Hello" } } }
        });

        var mockContext = new Mock<ResponseContext>("resp_" + new string('0', 46)) { CallBase = true };
        mockContext.Setup(x => x.GetHistoryAsync(It.IsAny<CancellationToken>()))
            .ReturnsAsync([]);
        mockContext.Setup(x => x.GetInputItemsAsync(It.IsAny<bool>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync([]);

        return (request, mockContext.Object);
    }

    private sealed class TelemetryTestAgent : AIAgent
    {
        public const string AgentName = "TelemetryTestAgent";

        public override string? Name => AgentName;

        protected override IAsyncEnumerable<AgentResponseUpdate> RunCoreStreamingAsync(
            IEnumerable<ChatMessage> messages,
            AgentSession? session,
            AgentRunOptions? options,
            CancellationToken cancellationToken = default) =>
            SingleUpdateAsync(new AgentResponseUpdate
            {
                MessageId = "resp_msg_1",
                Contents = [new MeaiTextContent("telemetry test response")]
            }, cancellationToken);

        protected override Task<AgentResponse> RunCoreAsync(
            IEnumerable<ChatMessage> messages,
            AgentSession? session,
            AgentRunOptions? options,
            CancellationToken cancellationToken = default) =>
            throw new NotImplementedException();

        protected override ValueTask<AgentSession> CreateSessionCoreAsync(
            CancellationToken cancellationToken = default) =>
            new(new TelemetryAgentSession());

        protected override ValueTask<JsonElement> SerializeSessionCoreAsync(
            AgentSession session,
            JsonSerializerOptions? jsonSerializerOptions,
            CancellationToken cancellationToken = default) =>
            new(JsonDocument.Parse("{}").RootElement);

        protected override ValueTask<AgentSession> DeserializeSessionCoreAsync(
            JsonElement serializedState,
            JsonSerializerOptions? jsonSerializerOptions,
            CancellationToken cancellationToken = default) =>
            new(new TelemetryAgentSession());

        private static async IAsyncEnumerable<AgentResponseUpdate> SingleUpdateAsync(
            AgentResponseUpdate update,
            [EnumeratorCancellation] CancellationToken cancellationToken = default)
        {
            await Task.Yield();
            yield return update;
        }
    }

    private sealed class TelemetryAgentSession : AgentSession;
}
