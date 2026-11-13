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
using Microsoft.Extensions.AI;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging.Abstractions;
using Moq;
using OpenTelemetry;
using OpenTelemetry.Trace;
using MeaiTextContent = Microsoft.Extensions.AI.TextContent;

namespace Microsoft.Agents.AI.Foundry.Hosting.UnitTests;

/// <summary>
/// Tests that verify OTel spans are actually emitted and captured through the
/// <see cref="AgentFrameworkResponseHandler"/> pipeline when
/// <see cref="ServiceCollectionExtensions.ApplyOpenTelemetry"/> wraps the resolved agent.
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
        var activities = new ConcurrentActivityList();
        using var tracerProvider = Sdk.CreateTracerProviderBuilder()
            .AddSource(ResponsesSourceName)
            .AddInMemoryExporter(activities)
            .Build();

        var agent = new TelemetryTestAgent();
        var services = new ServiceCollection();
        services.AddSingleton<AgentSessionStore>(new TestAgentSessionStore());
        var sp = services.BuildServiceProvider();

        var handler = new AgentFrameworkResponseHandler(sp, new FoundryHostedAgentSource(agent), NullLogger<AgentFrameworkResponseHandler>.Instance);
        var (request, context) = BuildRequest();

        // Act — enumerate all events so the span completes before asserting
        await foreach (var _ in handler.CreateAsync(request, context, CancellationToken.None)) { }

        // Assert — filter by agent name to isolate this test's span from any parallel test spans
        var mySpan = Assert.Single(activities.Snapshot().Where(a => TelemetryTestAgent.AgentName.Equals(a.GetTagItem("gen_ai.agent.name"))).ToList());
        Assert.Equal("invoke_agent", mySpan.GetTagItem("gen_ai.operation.name"));
        Assert.NotNull(mySpan.GetTagItem("gen_ai.agent.id"));
    }

    [Fact]
    public async Task CreateAsync_SingletonFactoryAgent_EmitsInvokeAgentSpanAsync()
    {
        // Arrange
        var activities = new ConcurrentActivityList();
        using var tracerProvider = Sdk.CreateTracerProviderBuilder()
            .AddSource(ResponsesSourceName)
            .AddInMemoryExporter(activities)
            .Build();

        var services = new ServiceCollection();
        services.AddSingleton<AgentSessionStore>(new TestAgentSessionStore());
        var sp = services.BuildServiceProvider();
        var agentSource = new FoundryHostedAgentSource(_ => new TelemetryTestAgent(), ServiceLifetime.Singleton, sp);

        var handler = new AgentFrameworkResponseHandler(sp, agentSource, NullLogger<AgentFrameworkResponseHandler>.Instance);
        var (request, context) = BuildRequest();

        // Act
        await foreach (var _ in handler.CreateAsync(request, context, CancellationToken.None)) { }

        // Assert — filter by agent name to isolate this test's span
        var mySpan = Assert.Single(activities.Snapshot().Where(a => TelemetryTestAgent.AgentName.Equals(a.GetTagItem("gen_ai.agent.name"))).ToList());
        Assert.Equal("invoke_agent", mySpan.GetTagItem("gen_ai.operation.name"));
    }

    [Fact]
    public async Task CreateAsync_AlreadyInstrumentedAgent_EmitsSingleSpanPerRunAsync()
    {
        // Arrange — use a unique source for the pre-wrapped agent distinct from ResponsesSourceName.
        // If ApplyOpenTelemetry double-wraps, an extra span would appear on ResponsesSourceName.
        // If it correctly skips wrapping, only the pre-wrap's unique source emits spans.
        var preWrapSource = Guid.NewGuid().ToString();
        var preWrapActivities = new ConcurrentActivityList();
        var responsesActivities = new ConcurrentActivityList();

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
        services.AddSingleton<AgentSessionStore>(new TestAgentSessionStore());
        var sp = services.BuildServiceProvider();

        var handler = new AgentFrameworkResponseHandler(sp, new FoundryHostedAgentSource(preWrapped), NullLogger<AgentFrameworkResponseHandler>.Instance);

        // Act
        var (request, context) = BuildRequest();
        await foreach (var _ in handler.CreateAsync(request, context, CancellationToken.None)) { }

        // Assert — pre-wrap source emits exactly 1 span (agent ran)
        var preWrapSnapshot = preWrapActivities.Snapshot();
        Assert.Single(preWrapSnapshot);
        Assert.Equal("invoke_agent", preWrapSnapshot[0].GetTagItem("gen_ai.operation.name"));

        // ResponsesSourceName emits 0 spans — ApplyOpenTelemetry skipped wrapping the pre-instrumented agent
        Assert.DoesNotContain(responsesActivities.Snapshot(), a => TelemetryTestAgent.AgentName.Equals(a.GetTagItem("gen_ai.agent.name")));
    }

    [Fact]
    public async Task CreateAsync_DefaultAgent_SpanDisplayNameContainsAgentNameAsync()
    {
        // Arrange
        var activities = new ConcurrentActivityList();
        using var tracerProvider = Sdk.CreateTracerProviderBuilder()
            .AddSource(ResponsesSourceName)
            .AddInMemoryExporter(activities)
            .Build();

        var agent = new TelemetryTestAgent();
        var services = new ServiceCollection();
        services.AddSingleton<AgentSessionStore>(new TestAgentSessionStore());
        var sp = services.BuildServiceProvider();

        var handler = new AgentFrameworkResponseHandler(sp, new FoundryHostedAgentSource(agent), NullLogger<AgentFrameworkResponseHandler>.Instance);
        var (request, context) = BuildRequest();

        // Act
        await foreach (var _ in handler.CreateAsync(request, context, CancellationToken.None)) { }

        // Assert — display name follows "invoke_agent {Name}({Id})" convention; filter by agent name to isolate
        var mySpan = Assert.Single(activities.Snapshot().Where(a => TelemetryTestAgent.AgentName.Equals(a.GetTagItem("gen_ai.agent.name"))).ToList());
        Assert.Contains("invoke_agent", mySpan.DisplayName, StringComparison.Ordinal);
        Assert.Contains(TelemetryTestAgent.AgentName, mySpan.DisplayName, StringComparison.Ordinal);
    }

    [Fact]
    public async Task CreateAsync_ReusedAgent_IsWrappedOnceAndTheWrapperIsDisposedWithTheHandlerAsync()
    {
        // Arrange
        var activities = new ConcurrentActivityList();
        using var tracerProvider = Sdk.CreateTracerProviderBuilder()
            .AddSource(ResponsesSourceName)
            .AddInMemoryExporter(activities)
            .Build();

        string agentName = UniqueAgentName();
        var store = new ServedAgentRecordingStore();
        var services = new ServiceCollection();
        services.AddSingleton<AgentSessionStore>(store);
        var sp = services.BuildServiceProvider();
        var handler = new AgentFrameworkResponseHandler(sp, new FoundryHostedAgentSource(new TelemetryTestAgent(agentName)), NullLogger<AgentFrameworkResponseHandler>.Instance);

        // Act: two responses, then shutdown, then one more run through the agent hosting served.
        await DrainAsync(handler);
        await DrainAsync(handler);
        AIAgent servedAgent = Assert.Single(store.Agents.Distinct());
        int spansWhileServing = CountSpans(activities, agentName);
        handler.Dispose();
        await foreach (var _ in servedAgent.RunStreamingAsync([new ChatMessage(ChatRole.User, "Hello")])) { }

        // Assert: one telemetry wrapper served both responses, and it stopped emitting once disposed.
        Assert.IsType<OpenTelemetryAgent>(servedAgent);
        Assert.Equal(2, spansWhileServing);
        Assert.Equal(2, CountSpans(activities, agentName));
    }

    [Fact]
    public async Task Dispose_AgentWithItsOwnTelemetry_LeavesThatTelemetryToTheCallerAsync()
    {
        // Arrange
        var preWrapSource = Guid.NewGuid().ToString();
        var activities = new ConcurrentActivityList();
        using var tracerProvider = Sdk.CreateTracerProviderBuilder()
            .AddSource(preWrapSource)
            .AddInMemoryExporter(activities)
            .Build();

        string agentName = UniqueAgentName();
        AIAgent preWrapped = new TelemetryTestAgent(agentName).AsBuilder()
            .UseOpenTelemetry(sourceName: preWrapSource)
            .Build();
        var services = new ServiceCollection();
        services.AddSingleton<AgentSessionStore>(new TestAgentSessionStore());
        var sp = services.BuildServiceProvider();
        var handler = new AgentFrameworkResponseHandler(sp, new FoundryHostedAgentSource(preWrapped), NullLogger<AgentFrameworkResponseHandler>.Instance);

        // Act
        await DrainAsync(handler);
        handler.Dispose();
        await foreach (var _ in preWrapped.RunStreamingAsync([new ChatMessage(ChatRole.User, "Hello")])) { }

        // Assert: hosting added no wrapper of its own, and the caller's telemetry keeps working.
        Assert.Equal(2, CountSpans(activities, agentName));
    }

    [Theory]
    [InlineData(ServiceLifetime.Scoped)]
    [InlineData(ServiceLifetime.Transient)]
    public async Task CreateAsync_PerRunAgent_IsWrappedAndTheWrapperIsDisposedWithTheRunAsync(ServiceLifetime lifetime)
    {
        // Arrange
        var activities = new ConcurrentActivityList();
        using var tracerProvider = Sdk.CreateTracerProviderBuilder()
            .AddSource(ResponsesSourceName)
            .AddInMemoryExporter(activities)
            .Build();

        string agentName = UniqueAgentName();
        var store = new ServedAgentRecordingStore();
        var services = new ServiceCollection();
        services.AddSingleton<AgentSessionStore>(store);
        var sp = services.BuildServiceProvider();
        var agentSource = new FoundryHostedAgentSource(
            _ => new TelemetryTestAgent(agentName),
            lifetime,
            sp);
        var handler = new AgentFrameworkResponseHandler(sp, agentSource, NullLogger<AgentFrameworkResponseHandler>.Instance);

        // Act: finish one response, then run through the telemetry wrapper that response used.
        await DrainAsync(handler);
        AIAgent servedAgent = Assert.Single(store.Agents.Distinct());
        int spansWhileServing = CountSpans(activities, agentName);
        await foreach (var _ in servedAgent.RunStreamingAsync([new ChatMessage(ChatRole.User, "Hello")])) { }

        // Assert: hosting added telemetry for the run, then disposed it before disposing the factory agent.
        Assert.IsType<OpenTelemetryAgent>(servedAgent);
        Assert.Equal(1, spansWhileServing);
        Assert.Equal(1, CountSpans(activities, agentName));
    }

    [Theory]
    [InlineData(ServiceLifetime.Scoped)]
    [InlineData(ServiceLifetime.Transient)]
    public async Task CreateAsync_PerRunAgentWithItsOwnTelemetry_IsNotWrappedByHostingAsync(ServiceLifetime lifetime)
    {
        // Arrange
        var ownSource = Guid.NewGuid().ToString();
        var ownActivities = new ConcurrentActivityList();
        var responsesActivities = new ConcurrentActivityList();
        using var ownProvider = Sdk.CreateTracerProviderBuilder()
            .AddSource(ownSource)
            .AddInMemoryExporter(ownActivities)
            .Build();
        using var responsesProvider = Sdk.CreateTracerProviderBuilder()
            .AddSource(ResponsesSourceName)
            .AddInMemoryExporter(responsesActivities)
            .Build();

        string agentName = UniqueAgentName();
        var services = new ServiceCollection();
        services.AddSingleton<AgentSessionStore>(new TestAgentSessionStore());
        var sp = services.BuildServiceProvider();
        var agentSource = new FoundryHostedAgentSource(
            _ => new TelemetryTestAgent(agentName).AsBuilder().UseOpenTelemetry(sourceName: ownSource).Build(),
            lifetime,
            sp);
        var handler = new AgentFrameworkResponseHandler(sp, agentSource, NullLogger<AgentFrameworkResponseHandler>.Instance);

        // Act
        await DrainAsync(handler);
        await DrainAsync(handler);

        // Assert: each response is traced once by the factory-supplied telemetry.
        Assert.Equal(2, CountSpans(ownActivities, agentName));
        Assert.Equal(0, CountSpans(responsesActivities, agentName));
    }

    [Fact]
    public async Task CreateAsync_PerRunAgentWhenTelemetryIsNotRequired_RunsWithoutAgentTelemetryAsync()
    {
        // Arrange
        var activities = new ConcurrentActivityList();
        using var tracerProvider = Sdk.CreateTracerProviderBuilder()
            .AddSource(ResponsesSourceName)
            .AddInMemoryExporter(activities)
            .Build();

        string agentName = UniqueAgentName();
        var services = new ServiceCollection();
        services.AddSingleton<AgentSessionStore>(new TestAgentSessionStore());
        var sp = services.BuildServiceProvider();
        var agentSource = new FoundryHostedAgentSource(
            _ => new TelemetryTestAgent(agentName),
            ServiceLifetime.Scoped,
            sp);
        var handler = new AgentFrameworkResponseHandler(
            sp,
            agentSource,
            NullLogger<AgentFrameworkResponseHandler>.Instance,
            new FoundryResponsesServerOptions { RequireOpenTelemetryAgent = false });

        // Act
        await DrainAsync(handler);

        // Assert: hosting adds no telemetry to an agent created per response.
        Assert.Equal(0, CountSpans(activities, agentName));
    }

    private static string UniqueAgentName() => $"telemetry-agent-{Guid.NewGuid():N}";

    private static int CountSpans(ConcurrentActivityList activities, string agentName) =>
        activities.Snapshot().Count(a => agentName.Equals(a.GetTagItem("gen_ai.agent.name")));

    private static async Task DrainAsync(AgentFrameworkResponseHandler handler)
    {
        var (request, context) = BuildRequest();
        await foreach (var _ in handler.CreateAsync(request, context, CancellationToken.None)) { }
    }

    private static (CreateResponse request, ResponseContext context) BuildRequest()
    {
        var request = new CreateResponse { Model = "test" };

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

        private readonly string _name;

        public TelemetryTestAgent(string name = AgentName)
        {
            this._name = name;
        }

        public override string? Name => this._name;

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

    /// <summary>
    /// Thread-safe <see cref="ICollection{Activity}"/> used by OTel's InMemoryExporter to capture
    /// activities emitted on globally-listened sources. Required because the exporter writes into
    /// the supplied collection from background Activity completion callbacks while the test thread
    /// may be enumerating it for assertions, and other tests in the same assembly may emit on the
    /// same source concurrently. A plain <see cref="List{Activity}"/> trips
    /// "Collection was modified; enumeration operation may not execute." in that scenario.
    /// </summary>
    private sealed class ConcurrentActivityList : ICollection<Activity>
    {
        private readonly List<Activity> _items = new();
        private readonly object _gate = new();

        public int Count { get { lock (this._gate) { return this._items.Count; } } }
        public bool IsReadOnly => false;

        public void Add(Activity item) { lock (this._gate) { this._items.Add(item); } }
        public void Clear() { lock (this._gate) { this._items.Clear(); } }
        public bool Contains(Activity item) { lock (this._gate) { return this._items.Contains(item); } }
        public void CopyTo(Activity[] array, int arrayIndex) { lock (this._gate) { this._items.CopyTo(array, arrayIndex); } }
        public bool Remove(Activity item) { lock (this._gate) { return this._items.Remove(item); } }

        public Activity[] Snapshot()
        {
            lock (this._gate) { return this._items.ToArray(); }
        }

        public IEnumerator<Activity> GetEnumerator() => ((IEnumerable<Activity>)this.Snapshot()).GetEnumerator();
        System.Collections.IEnumerator System.Collections.IEnumerable.GetEnumerator() => this.GetEnumerator();
    }
}
