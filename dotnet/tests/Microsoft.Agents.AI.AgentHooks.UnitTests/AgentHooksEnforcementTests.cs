// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using AgentHooks;
using Microsoft.Extensions.AI;
using static Microsoft.Agents.AI.AgentHooks.UnitTests.TestHelpers;

namespace Microsoft.Agents.AI.AgentHooks.UnitTests;

public class AgentHooksEnforcementTests
{
    // -------------------------------------------------------------------------
    // Session shape and projections
    // -------------------------------------------------------------------------

    [Fact]
    public async Task FullToolRunEmitsCompleteOrderedSessionAsync()
    {
        // Arrange
        var client = new MockChatClient()
            .EnqueueFunctionCall("call-1", "get_weather", new() { ["location"] = "Paris" })
            .EnqueueText("It is sunny.");
        var guard = new AllowGuard();
        var records = new ConcurrentQueue<InterceptionRecord>();
        var agent = client.AsAIAgentWithAgentHooks(
            new AgentHooksOptions(guard) { RecordSink = records.Enqueue },
            AgentOptionsWithTools(WeatherTool()));

        // Act
        var response = await agent.RunAsync(UserMessage("weather in paris?"));

        // Assert
        Assert.Equal("It is sunny.", response.Text);
        Assert.Equal(
            [
                "agent_startup", "input",
                "pre_model_call", "post_model_call",
                "pre_tool_call", "post_tool_call",
                "pre_model_call", "post_model_call",
                "output", "agent_shutdown",
            ],
            guard.Points);
        Assert.All(records, record => Assert.Equal(records.First().SessionId, record.SessionId));
    }

    [Fact]
    public async Task InputProjectionIsFaithfulAsync()
    {
        // Arrange
        var client = new MockChatClient().EnqueueText("hi");
        var guard = new AllowGuard();
        var agent = client.AsAIAgentWithAgentHooks(new AgentHooksOptions(guard));

        // Act
        _ = await agent.RunAsync(UserMessage("hello agent"));

        // Assert: a single plain-text message projects as its content string.
        var input = guard.Context("input");
        Assert.Equal("hello agent", input["input"]?["content"]?.GetValue<string>());
        Assert.Equal("user", input["input"]?["role"]?.GetValue<string>());
        var startup = guard.Context("agent_startup");
        Assert.NotNull(startup["agent_init"]?["tools_registered"]);
    }

    [Fact]
    public async Task RichContentIsPreservedInProjectionsAsync()
    {
        // Arrange
        var image = new DataContent(new byte[] { 1, 2, 3 }, "image/png");
        var client = new MockChatClient()
            .EnqueueResponse(new ChatResponse(new ChatMessage(ChatRole.Assistant, [new TextContent("look"), image])));
        var guard = new AllowGuard();
        var agent = client.AsAIAgentWithAgentHooks(new AgentHooksOptions(guard));

        // Act
        var response = await agent.RunAsync(UserMessage("show me"));

        // Assert: rich content is projected as content objects, not flattened to text,
        // and the untouched response keeps the original content instances.
        var output = guard.Context("output");
        var parts = Assert.IsType<JsonArray>(output["output"]?["content"]);
        var contentList = Assert.IsType<JsonArray>(parts[0]?["content"]);
        Assert.Equal(2, contentList.Count);
        Assert.Same(image, response.Messages.SelectMany(m => m.Contents).OfType<DataContent>().Single());
    }

    [Fact]
    public async Task ToolCallsRideToolCallsProjectionAsync()
    {
        // Arrange
        var client = new MockChatClient()
            .EnqueueFunctionCall("call-1", "get_weather", new() { ["location"] = "Paris" })
            .EnqueueText("done");
        var guard = new AllowGuard();
        var agent = client.AsAIAgentWithAgentHooks(new AgentHooksOptions(guard), AgentOptionsWithTools(WeatherTool()));

        // Act
        _ = await agent.RunAsync(UserMessage("weather?"));

        // Assert: the host-executed call is in tool_calls with faithful args.
        var postModel = guard.Contexts("post_model_call")[0];
        var calls = Assert.IsType<JsonArray>(postModel["response"]?["tool_calls"]);
        Assert.Equal("get_weather", calls[0]?["name"]?.GetValue<string>());
        Assert.Equal("Paris", calls[0]?["args"]?["location"]?.GetValue<string>());
    }

    // -------------------------------------------------------------------------
    // Deny before execution, per seam
    // -------------------------------------------------------------------------

    [Fact]
    public async Task InputDenyBlocksRunBeforeModelCallAsync()
    {
        // Arrange
        var client = new MockChatClient().EnqueueText("never");
        var agent = client.AsAIAgentWithAgentHooks(
            new AgentHooksOptions(new PointGuard(InterceptionPoint.Input, Verdict.Deny("blocked_input"))));

        // Act / Assert
        var exception = await Assert.ThrowsAsync<InterceptionBlockedException>(() => agent.RunAsync(UserMessage("hi")));
        Assert.Equal("blocked_input", exception.Result.Verdict.Reason);
        Assert.Equal(0, client.CallCount);
    }

    [Fact]
    public async Task PreModelCallDenyBlocksModelDispatchAsync()
    {
        // Arrange
        var client = new MockChatClient().EnqueueText("never");
        var agent = client.AsAIAgentWithAgentHooks(
            new AgentHooksOptions(new PointGuard(InterceptionPoint.PreModelCall, Verdict.Deny("no_model"))));

        // Act / Assert
        _ = await Assert.ThrowsAsync<InterceptionBlockedException>(() => agent.RunAsync(UserMessage("hi")));
        Assert.Equal(0, client.CallCount);
    }

    [Fact]
    public async Task PostModelCallDenyDiscardsResponseAsync()
    {
        // Arrange
        var client = new MockChatClient().EnqueueText("secret");
        var agent = client.AsAIAgentWithAgentHooks(
            new AgentHooksOptions(new PointGuard(InterceptionPoint.PostModelCall, Verdict.Deny("bad_response"))));

        // Act / Assert
        _ = await Assert.ThrowsAsync<InterceptionBlockedException>(() => agent.RunAsync(UserMessage("hi")));
        Assert.Equal(1, client.CallCount);
    }

    [Fact]
    public async Task PreToolCallDenyBlocksToolAndContinuesLoopAsync()
    {
        // Arrange
        bool invoked = false;
        var client = new MockChatClient()
            .EnqueueFunctionCall("call-1", "get_weather", new() { ["location"] = "Paris" })
            .EnqueueText("recovered");
        var agent = client.AsAIAgentWithAgentHooks(
            new AgentHooksOptions(new PointGuard(InterceptionPoint.PreToolCall, Verdict.Deny("tool_blocked"))),
            AgentOptionsWithTools(WeatherTool(_ => invoked = true)));

        // Act
        var response = await agent.RunAsync(UserMessage("weather?"));

        // Assert: the tool never ran, the model saw a tool-error payload, the loop continued.
        Assert.False(invoked);
        Assert.Equal("recovered", response.Text);
        var secondRequest = client.Requests[1];
        var result = secondRequest.SelectMany(m => m.Contents).OfType<FunctionResultContent>().Single();
        string serialized = System.Text.Json.JsonSerializer.Serialize(result.Result);
        Assert.Contains("blocked by agent-hooks at pre_tool_call", serialized, StringComparison.Ordinal);
        Assert.Contains("tool_blocked", serialized, StringComparison.Ordinal);
    }

    [Fact]
    public async Task PostToolCallDenyDiscardsResultAsync()
    {
        // Arrange
        var client = new MockChatClient()
            .EnqueueFunctionCall("call-1", "get_weather", new() { ["location"] = "Paris" })
            .EnqueueText("recovered");
        var agent = client.AsAIAgentWithAgentHooks(
            new AgentHooksOptions(new PointGuard(InterceptionPoint.PostToolCall, Verdict.Deny("result_blocked"))),
            AgentOptionsWithTools(WeatherTool()));

        // Act
        var response = await agent.RunAsync(UserMessage("weather?"));

        // Assert: the result was discarded and replaced with a tool-error payload.
        Assert.Equal("recovered", response.Text);
        var result = client.Requests[1].SelectMany(m => m.Contents).OfType<FunctionResultContent>().Single();
        string serialized = System.Text.Json.JsonSerializer.Serialize(result.Result);
        Assert.DoesNotContain("weather:Paris", serialized, StringComparison.Ordinal);
        Assert.Contains("result_blocked", serialized, StringComparison.Ordinal);
    }

    [Fact]
    public async Task OutputDenyBlocksResponseAsync()
    {
        // Arrange
        var client = new MockChatClient().EnqueueText("secret");
        var agent = client.AsAIAgentWithAgentHooks(
            new AgentHooksOptions(new PointGuard(InterceptionPoint.Output, Verdict.Deny("egress_blocked"))));

        // Act / Assert
        var exception = await Assert.ThrowsAsync<InterceptionBlockedException>(() => agent.RunAsync(UserMessage("hi")));
        Assert.Equal("egress_blocked", exception.Result.Verdict.Reason);
    }

    // -------------------------------------------------------------------------
    // Transform write-back, per seam
    // -------------------------------------------------------------------------

    [Fact]
    public async Task InputTransformWritesBackIntoRunMessagesAsync()
    {
        // Arrange
        var client = new MockChatClient().EnqueueText("ok");
        var transform = TransformTarget(new JsonObject { ["content"] = "[clean]", ["role"] = "user" });
        var agent = client.AsAIAgentWithAgentHooks(
            new AgentHooksOptions(new PointGuard(InterceptionPoint.Input, transform)));

        // Act
        _ = await agent.RunAsync(UserMessage("dirty input"));

        // Assert: the model received exactly the transformed input.
        Assert.Equal("[clean]", client.Requests[0].Last().Text);
    }

    [Fact]
    public async Task PreModelCallTransformWritesBackIntoRequestAsync()
    {
        // Arrange
        var client = new MockChatClient().EnqueueText("ok");
        var transform = TransformTarget(new JsonArray(new JsonObject { ["role"] = "user", ["content"] = "[redacted]" }));
        var agent = client.AsAIAgentWithAgentHooks(
            new AgentHooksOptions(new PointGuard(InterceptionPoint.PreModelCall, transform)));

        // Act
        _ = await agent.RunAsync(UserMessage("sensitive"));

        // Assert
        Assert.Equal("[redacted]", client.Requests[0].Single().Text);
    }

    [Fact]
    public async Task PreToolCallTransformWritesBackIntoArgumentsAsync()
    {
        // Arrange
        string? seenLocation = null;
        var client = new MockChatClient()
            .EnqueueFunctionCall("call-1", "get_weather", new() { ["location"] = "Paris" })
            .EnqueueText("done");
        var transform = TransformTarget(new JsonObject { ["location"] = "Berlin" });
        var agent = client.AsAIAgentWithAgentHooks(
            new AgentHooksOptions(new PointGuard(InterceptionPoint.PreToolCall, transform)),
            AgentOptionsWithTools(WeatherTool(location => seenLocation = location)));

        // Act
        _ = await agent.RunAsync(UserMessage("weather?"));

        // Assert: the tool executed the approved (transformed) arguments.
        Assert.Equal("Berlin", seenLocation);
    }

    [Fact]
    public async Task PostToolCallTransformWritesBackIntoResultAsync()
    {
        // Arrange
        var client = new MockChatClient()
            .EnqueueFunctionCall("call-1", "get_weather", new() { ["location"] = "Paris" })
            .EnqueueText("done");
        var transform = TransformTarget((JsonNode)"weather:[redacted]");
        var agent = client.AsAIAgentWithAgentHooks(
            new AgentHooksOptions(new PointGuard(InterceptionPoint.PostToolCall, transform)),
            AgentOptionsWithTools(WeatherTool()));

        // Act
        _ = await agent.RunAsync(UserMessage("weather?"));

        // Assert: the model saw the transformed result, not the raw one.
        var result = client.Requests[1].SelectMany(m => m.Contents).OfType<FunctionResultContent>().Single();
        string serialized = System.Text.Json.JsonSerializer.Serialize(result.Result);
        Assert.Contains("weather:[redacted]", serialized, StringComparison.Ordinal);
        Assert.DoesNotContain("weather:Paris", serialized, StringComparison.Ordinal);
    }

    [Fact]
    public async Task PostModelCallTransformWritesBackIntoResponseAsync()
    {
        // Arrange
        var client = new MockChatClient().EnqueueText("raw");
        var transform = TransformTarget(new JsonObject
        {
            ["content"] = "[filtered]",
            ["tool_calls"] = new JsonArray(),
            ["finish_reason"] = "stop",
        });
        var agent = client.AsAIAgentWithAgentHooks(
            new AgentHooksOptions(new PointGuard(InterceptionPoint.PostModelCall, transform)));

        // Act
        var response = await agent.RunAsync(UserMessage("hi"));

        // Assert
        Assert.Equal("[filtered]", response.Text);
    }

    [Fact]
    public async Task OutputTransformWritesBackIntoResponseAsync()
    {
        // Arrange
        var client = new MockChatClient().EnqueueText("raw output");
        var transform = TransformTarget(new JsonObject { ["content"] = "[final]" });
        var agent = client.AsAIAgentWithAgentHooks(
            new AgentHooksOptions(new PointGuard(InterceptionPoint.Output, transform)));

        // Act
        var response = await agent.RunAsync(UserMessage("hi"));

        // Assert
        Assert.Equal("[final]", response.Text);
    }

    // -------------------------------------------------------------------------
    // Streaming: buffered, zero egress on deny, no divergence
    // -------------------------------------------------------------------------

    [Fact]
    public async Task StreamingBuffersUntilAllVerdictsPermitAsync()
    {
        // Arrange
        var client = new MockChatClient().EnqueueText("streamed text");
        var guard = new AllowGuard();
        var agent = client.AsAIAgentWithAgentHooks(new AgentHooksOptions(guard));

        // Act
        var updates = await CollectAsync(agent.RunStreamingAsync(UserMessage("hi")));

        // Assert: content egressed and every point was emitted before release.
        Assert.Equal("streamed text", string.Concat(updates.Select(u => u.Text)));
        Assert.Contains("output", guard.Points);
    }

    [Fact]
    public async Task StreamingOutputDenyReleasesNothingAsync()
    {
        // Arrange
        var client = new MockChatClient().EnqueueText("secret");
        var agent = client.AsAIAgentWithAgentHooks(
            new AgentHooksOptions(new PointGuard(InterceptionPoint.Output, Verdict.Deny("egress_blocked"))));

        // Act
        int released = 0;
        var exception = await Assert.ThrowsAsync<InterceptionBlockedException>(async () =>
        {
            await foreach (var _ in agent.RunStreamingAsync(UserMessage("hi")))
            {
                released++;
            }
        });

        // Assert: the deny surfaced at consumption with zero updates egressed.
        Assert.Equal(0, released);
        Assert.Equal("egress_blocked", exception.Result.Verdict.Reason);
    }

    [Fact]
    public async Task StreamingPostModelCallDenyReleasesNothingAsync()
    {
        // Arrange
        var client = new MockChatClient().EnqueueText("secret");
        var agent = client.AsAIAgentWithAgentHooks(
            new AgentHooksOptions(new PointGuard(InterceptionPoint.PostModelCall, Verdict.Deny("bad_response"))));

        // Act
        int released = 0;
        _ = await Assert.ThrowsAsync<InterceptionBlockedException>(async () =>
        {
            await foreach (var _ in agent.RunStreamingAsync(UserMessage("hi")))
            {
                released++;
            }
        });

        // Assert
        Assert.Equal(0, released);
    }

    [Fact]
    public async Task StreamingOutputTransformRewritesUpdatesAsync()
    {
        // Arrange
        var client = new MockChatClient().EnqueueText("raw");
        var transform = TransformTarget(new JsonObject { ["content"] = "[final]" });
        var agent = client.AsAIAgentWithAgentHooks(
            new AgentHooksOptions(new PointGuard(InterceptionPoint.Output, transform)));

        // Act
        var updates = await CollectAsync(agent.RunStreamingAsync(UserMessage("hi")));

        // Assert: released updates are re-derived from the verdicted response — streamed
        // egress never diverges from the transformed content.
        Assert.Equal("[final]", string.Concat(updates.Select(u => u.Text)));
    }

    // -------------------------------------------------------------------------
    // Error paths: fail closed, complete trail
    // -------------------------------------------------------------------------

    [Fact]
    public async Task ToolExceptionIsBracketedWithErrorPostToolCallAsync()
    {
        // Arrange
        var tool = AIFunctionFactory.Create(
            new Func<string, string>(location => throw new InvalidOperationException("tool exploded")), "get_weather");
        var client = new MockChatClient()
            .EnqueueFunctionCall("call-1", "get_weather", new() { ["location"] = "Paris" })
            .EnqueueText("recovered");
        var guard = new AllowGuard();
        var agent = client.AsAIAgentWithAgentHooks(new AgentHooksOptions(guard), AgentOptionsWithTools(tool));

        // Act
        _ = await agent.RunAsync(UserMessage("weather?"));

        // Assert: the errored call is bracketed with is_error=true and only the
        // exception type name crosses the boundary.
        var postTool = guard.Context("post_tool_call");
        Assert.True(postTool["tool_result"]?["is_error"]?.GetValue<bool>());
        Assert.Equal("InvalidOperationException", postTool["tool_result"]?["value"]?.GetValue<string>());
    }

    [Fact]
    public async Task InterceptorCrashAtToolSeamFailsClosedAndHaltsRunAsync()
    {
        // Arrange
        bool invoked = false;
        var client = new MockChatClient()
            .EnqueueFunctionCall("call-1", "get_weather", new() { ["location"] = "Paris" })
            .EnqueueText("never");
        var agent = client.AsAIAgentWithAgentHooks(
            new AgentHooksOptions(new CrashingGuard(InterceptionPoint.PreToolCall)),
            AgentOptionsWithTools(WeatherTool(_ => invoked = true)));

        // Act / Assert: the crash synthesizes a host_error deny, the tool never runs,
        // and the whole run halts instead of continuing unguarded.
        var exception = await Assert.ThrowsAsync<InterceptionBlockedException>(() => agent.RunAsync(UserMessage("weather?")));
        Assert.False(invoked);
        Assert.StartsWith("host_error:", exception.Result.Verdict.Reason, StringComparison.Ordinal);
    }

    [Fact]
    public async Task InterceptorCrashAtInputFailsClosedAsync()
    {
        // Arrange
        var client = new MockChatClient().EnqueueText("never");
        var agent = client.AsAIAgentWithAgentHooks(
            new AgentHooksOptions(new CrashingGuard(InterceptionPoint.Input)));

        // Act / Assert
        var exception = await Assert.ThrowsAsync<InterceptionBlockedException>(() => agent.RunAsync(UserMessage("hi")));
        Assert.StartsWith("host_error:", exception.Result.Verdict.Reason, StringComparison.Ordinal);
        Assert.Equal(0, client.CallCount);
    }

    [Fact]
    public async Task DeniedRunStillClosesSessionTrailAsync()
    {
        // Arrange
        var client = new MockChatClient().EnqueueText("secret");
        var guard = new AllowGuard();
        var agent = client.AsAIAgentWithAgentHooks(
            new AgentHooksOptions(guard).AddInterceptor(new PointGuard(InterceptionPoint.Output, Verdict.Deny("no"))));

        // Act
        _ = await Assert.ThrowsAsync<InterceptionBlockedException>(() => agent.RunAsync(UserMessage("hi")));

        // Assert: the trail is closed with an error shutdown.
        var shutdown = guard.Context("agent_shutdown");
        Assert.Equal("error", shutdown["summary"]?["reason"]?.GetValue<string>());
    }

    // -------------------------------------------------------------------------
    // Concurrency and session scoping
    // -------------------------------------------------------------------------

    [Fact]
    public async Task ConcurrentRunsAreIsolatedAsync()
    {
        // Arrange
        var client = new MockChatClient();
        for (int i = 0; i < 8; i++)
        {
            _ = client.EnqueueText("ok");
        }

        var records = new ConcurrentQueue<InterceptionRecord>();
        var agent = client.AsAIAgentWithAgentHooks(
            new AgentHooksOptions(new AllowGuard()) { RecordSink = records.Enqueue });

        // Act
        await Task.WhenAll(Enumerable.Range(0, 8).Select(i => agent.RunAsync(UserMessage($"run {i}"))));

        // Assert: eight distinct per-run sessions, each with a complete bracket.
        var sessions = records.GroupBy(record => record.SessionId).ToList();
        Assert.Equal(8, sessions.Count);
        Assert.All(sessions, session =>
        {
            Assert.Contains(session, record => record.InterceptionPoint == InterceptionPoint.AgentStartup);
            Assert.Contains(session, record => record.InterceptionPoint == InterceptionPoint.Output);
            Assert.Contains(session, record => record.InterceptionPoint == InterceptionPoint.AgentShutdown);
        });
    }

    [Fact]
    public async Task SequentialRunsGetFreshSessionsAsync()
    {
        // Arrange
        var client = new MockChatClient().EnqueueText("one").EnqueueText("two");
        var records = new ConcurrentQueue<InterceptionRecord>();
        var agent = client.AsAIAgentWithAgentHooks(
            new AgentHooksOptions(new AllowGuard()) { RecordSink = records.Enqueue });

        // Act
        _ = await agent.RunAsync(UserMessage("first"));
        _ = await agent.RunAsync(UserMessage("second"));

        // Assert
        Assert.Equal(2, records.Select(record => record.SessionId).Distinct().Count());
    }

    [Fact]
    public async Task HostOwnedSessionSpansRunsAsync()
    {
        // Arrange
        var guard = new AllowGuard();
        var emitter = new InterceptionEmitter().Register(guard);
        var builder = new AgentContextBuilder("host-agent", "host", "session-42");
        var client = new MockChatClient().EnqueueText("one").EnqueueText("two");
        var agent = client.AsAIAgentWithAgentHooks(emitter, builder);

        // Act
        _ = await agent.RunAsync(UserMessage("first"));
        _ = await agent.RunAsync(UserMessage("second"));

        // Assert: only per-run points, one shared session, continuous sequence.
        Assert.DoesNotContain("agent_startup", guard.Points);
        Assert.DoesNotContain("agent_shutdown", guard.Points);
        Assert.All(emitter.Records, record => Assert.Equal("session-42", record.SessionId));
        Assert.Equal(emitter.Records.Count, emitter.Records.Select(record => record.Sequence).Distinct().Count());
    }

    // -------------------------------------------------------------------------
    // Modes and the approval seam
    // -------------------------------------------------------------------------

    [Fact]
    public async Task EvaluateOnlyRecordsButNeverBlocksAsync()
    {
        // Arrange
        var client = new MockChatClient().EnqueueText("flows");
        var records = new ConcurrentQueue<InterceptionRecord>();
        var agent = client.AsAIAgentWithAgentHooks(
            new AgentHooksOptions(new PointGuard(InterceptionPoint.Input, Verdict.Deny("would_block")))
            {
                Mode = EnforcementMode.EvaluateOnly,
                RecordSink = records.Enqueue,
            });

        // Act
        var response = await agent.RunAsync(UserMessage("hi"));

        // Assert: the deny is recorded but the run proceeds untouched.
        Assert.Equal("flows", response.Text);
        var inputRecord = records.Single(record => record.InterceptionPoint == InterceptionPoint.Input);
        Assert.Equal(Decision.Deny, inputRecord.Verdict.Decision);
        Assert.True(inputRecord.Proceeds);
    }

    [Fact]
    public async Task LiftableDenyIsResolvedThroughTheApprovalSeamAsync()
    {
        // Arrange: a liftable deny plus a resolver that approves it.
        var client = new MockChatClient().EnqueueText("approved output");
        var resolver = new ApprovingResolver();
        var agent = client.AsAIAgentWithAgentHooks(
            new AgentHooksOptions(new PointGuard(InterceptionPoint.Output, Verdict.Escalate("needs_review")))
            {
                Resolver = resolver,
            });

        // Act
        var response = await agent.RunAsync(UserMessage("hi"));

        // Assert: the approval lifted the deny and the run egressed.
        Assert.Equal("approved output", response.Text);
        Assert.True(resolver.Consulted);
    }

    private sealed class ApprovingResolver : IApprovalResolver
    {
        public bool Consulted { get; private set; }

        public ValueTask<ApprovalResolution> ResolveAsync(ApprovalRequest request, CancellationToken ct = default)
        {
            this.Consulted = true;
            return new(new ApprovalResolution(ApprovalOutcome.Approve, request.ContextIdentity, Verdict.Allow));
        }
    }

    // -------------------------------------------------------------------------
    // Misuse fails closed (partial-install impossibility)
    // -------------------------------------------------------------------------

    [Fact]
    public async Task ExtractedChatClientFailsClosedOutsideItsRunAsync()
    {
        // Arrange
        var client = new MockChatClient().EnqueueText("never");
        var agent = client.AsAIAgentWithAgentHooks(new AgentHooksOptions(new AllowGuard()));
        var extracted = agent.GetService<IChatClient>();
        Assert.NotNull(extracted);

        // Act / Assert: the chat seam refuses to run without its agent seam's state.
        _ = await Assert.ThrowsAsync<InvalidOperationException>(
            () => extracted!.GetResponseAsync(UserMessage("hi")));
        Assert.Equal(0, client.CallCount);
    }

    [Fact]
    public async Task ForeignSeamNestingFailsLoudlyAsync()
    {
        // Arrange: agent B is (mis)built over agent A's guarded chat client, so A's chat
        // seam runs inside B's run state.
        var client = new MockChatClient().EnqueueText("never");
        var configurationA = new AgentHooksConfiguration
        {
            Interceptors = [new KeyValuePair<string?, IInterceptor>(null, new AllowGuard())],
        };
        var clientOfA = new AgentHooksChatClient(client, configurationA);
        var agentB = clientOfA.AsAIAgentWithAgentHooks(new AgentHooksOptions(new AllowGuard()));

        // Act / Assert
        var exception = await Assert.ThrowsAsync<InvalidOperationException>(() => agentB.RunAsync(UserMessage("hi")));
        Assert.Contains("different agent-hooks installation", exception.Message, StringComparison.Ordinal);
        Assert.Equal(0, client.CallCount);
    }

    [Fact]
    public void FactoryRequiresInterceptors()
    {
        // Arrange
        var client = new MockChatClient();

        // Act / Assert
        _ = Assert.Throws<ArgumentException>(() => client.AsAIAgentWithAgentHooks(new AgentHooksOptions()));
    }

    [Fact]
    public async Task NestedGuardedAgentsStayIsolatedAsync()
    {
        // Arrange: a guarded sub-agent invoked as a tool of a guarded outer agent.
        var subClient = new MockChatClient().EnqueueText("sub says hi");
        var subGuard = new AllowGuard();
        var subAgent = subClient.AsAIAgentWithAgentHooks(new AgentHooksOptions(subGuard));
        var subTool = AIFunctionFactory.Create(
            async () => (await subAgent.RunAsync(UserMessage("inner"))).Text, "ask_sub_agent");

        var outerClient = new MockChatClient()
            .EnqueueFunctionCall("call-1", "ask_sub_agent", [])
            .EnqueueText("outer done");
        var outerGuard = new AllowGuard();
        var outerAgent = outerClient.AsAIAgentWithAgentHooks(
            new AgentHooksOptions(outerGuard), AgentOptionsWithTools(subTool));

        // Act
        var response = await outerAgent.RunAsync(UserMessage("go"));

        // Assert: both runs completed with their own complete, separate sessions.
        Assert.Equal("outer done", response.Text);
        Assert.Contains("pre_tool_call", outerGuard.Points);
        Assert.Equal(
            ["agent_startup", "input", "pre_model_call", "post_model_call", "output", "agent_shutdown"],
            subGuard.Points);
        Assert.DoesNotContain("pre_tool_call", subGuard.Points);
    }
}
