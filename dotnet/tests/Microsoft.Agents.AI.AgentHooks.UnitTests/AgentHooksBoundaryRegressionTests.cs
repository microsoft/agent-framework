// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Threading.Tasks;
using AgentHooks;
using Microsoft.Extensions.AI;
using static Microsoft.Agents.AI.AgentHooks.UnitTests.TestHelpers;

namespace Microsoft.Agents.AI.AgentHooks.UnitTests;

/// <summary>
/// Regressions for the structural boundary with <see cref="ChatClientAgent"/>, mined
/// from the review probes: the default history provider must be gated, per-run options
/// must not open bypass routes, and seam-order inversions are rejected loudly.
/// </summary>
public class AgentHooksBoundaryRegressionTests
{
    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task DefaultProviderDeniedOutputNeverBecomesDurableAsync(bool streaming)
    {
        // Arrange: NO ChatHistoryProvider configured — the zero-config path where the
        // agent's implicit default InMemoryChatHistoryProvider must still be gated.
        const string Marker = "SECRET-TOKEN-42";
        var client = new MockChatClient().EnqueueText(Marker).EnqueueText("second turn ok");
        var agent = client.AsAIAgentWithAgentHooks(
            new AgentHooksOptions(new ContentDenyGuard(InterceptionPoint.Output, Marker)));
        var session = await agent.CreateSessionAsync();

        // Act: first run is denied at output.
        if (streaming)
        {
            _ = await Assert.ThrowsAsync<InterceptionBlockedException>(async () =>
            {
                await foreach (var _ in agent.RunStreamingAsync(UserMessage("hi"), session))
                {
                }
            });
        }
        else
        {
            _ = await Assert.ThrowsAsync<InterceptionBlockedException>(() => agent.RunAsync(UserMessage("hi"), session));
        }

        // Assert: the denied content is not in the serialized session state and does not
        // replay to the model on the next run.
        var state = await agent.SerializeSessionAsync(session);
        Assert.DoesNotContain(Marker, state.GetRawText(), StringComparison.Ordinal);

        _ = await agent.RunAsync(UserMessage("next question"), session);
        Assert.True(client.Requests.Count > 1);
        Assert.DoesNotContain(client.Requests[1], message => message.Text.Contains(Marker, StringComparison.Ordinal));
    }

    [Fact]
    public async Task DefaultProviderPermittedOutputStillPersistsAsync()
    {
        // Arrange: gating the implicit default must not break normal session history.
        var client = new MockChatClient().EnqueueText("first answer").EnqueueText("second answer");
        var agent = client.AsAIAgentWithAgentHooks(new AgentHooksOptions(new AllowGuard()));
        var session = await agent.CreateSessionAsync();

        // Act
        _ = await agent.RunAsync(UserMessage("first question"), session);
        _ = await agent.RunAsync(UserMessage("second question"), session);

        // Assert: the second request carries the first turn from session history.
        Assert.Contains(client.Requests[1], message => message.Text == "first answer");
    }

    [Fact]
    public async Task BaseAdditionalPropertiesProviderOverrideIsGatedAsync()
    {
        // Arrange: the override rides the BASE AgentRunOptions.AdditionalProperties,
        // which the agent merges into the chat options with precedence.
        var overrideProvider = new RecordingHistoryProvider();
        var client = new MockChatClient().EnqueueText("secret");
        var agent = client.AsAIAgentWithAgentHooks(
            new AgentHooksOptions(new PointGuard(InterceptionPoint.Output, Verdict.Deny("egress_blocked"))));
        var session = await agent.CreateSessionAsync();
        var runOptions = new ChatClientAgentRunOptions { AdditionalProperties = [] };
        runOptions.AdditionalProperties!.Add<ChatHistoryProvider>(overrideProvider);

        // Act
        _ = await Assert.ThrowsAsync<InterceptionBlockedException>(
            () => agent.RunAsync(UserMessage("hi"), session, runOptions));

        // Assert
        Assert.Empty(overrideProvider.Stored);
    }

    [Fact]
    public async Task BaseOverrideDisplacingWrappedChatOptionsOverrideIsGatedAsync()
    {
        // Arrange: the same provider on BOTH dictionaries — the base-level entry
        // displaces the ChatOptions-level one during the agent's options merge, so both
        // must be wrapped.
        var overrideProvider = new RecordingHistoryProvider();
        var client = new MockChatClient().EnqueueText("secret");
        var agent = client.AsAIAgentWithAgentHooks(
            new AgentHooksOptions(new PointGuard(InterceptionPoint.Output, Verdict.Deny("egress_blocked"))));
        var session = await agent.CreateSessionAsync();
        var runOptions = new ChatClientAgentRunOptions
        {
            ChatOptions = new ChatOptions { AdditionalProperties = [] },
            AdditionalProperties = [],
        };
        runOptions.ChatOptions.AdditionalProperties!.Add<ChatHistoryProvider>(overrideProvider);
        runOptions.AdditionalProperties!.Add<ChatHistoryProvider>(overrideProvider);

        // Act
        _ = await Assert.ThrowsAsync<InterceptionBlockedException>(
            () => agent.RunAsync(UserMessage("hi"), session, runOptions));

        // Assert
        Assert.Empty(overrideProvider.Stored);
    }

    [Fact]
    public async Task PlainAgentRunOptionsProviderOverrideIsGatedAsync()
    {
        // Arrange: a plain AgentRunOptions (converted to ChatClientAgentRunOptions by
        // the tool-seam decorator, preserving AdditionalProperties) must be guarded too.
        var overrideProvider = new RecordingHistoryProvider();
        var client = new MockChatClient().EnqueueText("secret");
        var agent = client.AsAIAgentWithAgentHooks(
            new AgentHooksOptions(new PointGuard(InterceptionPoint.Output, Verdict.Deny("egress_blocked"))));
        var session = await agent.CreateSessionAsync();
        var runOptions = new AgentRunOptions { AdditionalProperties = [] };
        runOptions.AdditionalProperties!.Add<ChatHistoryProvider>(overrideProvider);

        // Act
        _ = await Assert.ThrowsAsync<InterceptionBlockedException>(
            () => agent.RunAsync(UserMessage("hi"), session, runOptions));

        // Assert
        Assert.Empty(overrideProvider.Stored);
    }

    [Fact]
    public async Task ForeignGatingWrapperOverrideIsRewrappedAsync()
    {
        // Arrange: a gating wrapper belonging to a DIFFERENT agent-hooks installation
        // (e.g. extracted from another guarded agent) is passed as a per-run provider
        // override. It runs inline under this run's state — its own gate is not covering
        // here — so skipping the re-wrap because "it is already a gating wrapper" would
        // let this run's denied history persist straight through it.
        var recording = new RecordingHistoryProvider();
        var foreignConfiguration = new AgentHooksConfiguration
        {
            Interceptors = [new KeyValuePair<string?, IInterceptor>(null, new AllowGuard())],
        };
        var foreignWrapper = new AgentHooksGatingChatHistoryProvider(recording, foreignConfiguration, perServiceCallPersistence: false);
        var client = new MockChatClient().EnqueueText("secret");
        var agent = client.AsAIAgentWithAgentHooks(
            new AgentHooksOptions(new PointGuard(InterceptionPoint.Output, Verdict.Deny("egress_blocked"))));
        var session = await agent.CreateSessionAsync();
        var runOptions = new ChatClientAgentRunOptions { AdditionalProperties = [] };
        runOptions.AdditionalProperties!.Add<ChatHistoryProvider>(foreignWrapper);

        // Act
        _ = await Assert.ThrowsAsync<InterceptionBlockedException>(
            () => agent.RunAsync(UserMessage("hi"), session, runOptions));

        // Assert: the denied run's history never reached the underlying provider.
        Assert.Empty(recording.Stored);
    }

    [Fact]
    public async Task CallerRunOptionsAreNeverMutatedAsync()
    {
        // Arrange
        var overrideProvider = new RecordingHistoryProvider();
        var client = new MockChatClient().EnqueueText("fine");
        var agent = client.AsAIAgentWithAgentHooks(new AgentHooksOptions(new AllowGuard()));
        var session = await agent.CreateSessionAsync();
        var runOptions = new ChatClientAgentRunOptions { AdditionalProperties = [] };
        runOptions.AdditionalProperties!.Add<ChatHistoryProvider>(overrideProvider);

        // Act
        _ = await agent.RunAsync(UserMessage("hi"), session, runOptions);

        // Assert: copy-on-write — the caller's dictionary still holds the original,
        // unwrapped provider instance.
        _ = runOptions.AdditionalProperties.TryGetValue(out ChatHistoryProvider? stillThere);
        Assert.Same(overrideProvider, stillThere);
    }

    [Fact]
    public async Task ReusedRunOptionsAcrossSequentialRunsWorkAsync()
    {
        // Arrange: the framework's function-invocation middleware chains its factory
        // onto the options instance it receives; forwarding the caller's instance would
        // leak that factory into it and trip the rejection on the second run.
        var client = new MockChatClient().EnqueueText("one").EnqueueText("two");
        var agent = client.AsAIAgentWithAgentHooks(new AgentHooksOptions(new AllowGuard()));
        var runOptions = new ChatClientAgentRunOptions();

        // Act
        var first = await agent.RunAsync(UserMessage("a"), null, runOptions);
        var second = await agent.RunAsync(UserMessage("b"), null, runOptions);

        // Assert: both runs succeed and the caller's options were never mutated.
        Assert.Equal("one", first.Text);
        Assert.Equal("two", second.Text);
        Assert.Null(runOptions.ChatClientFactory);
    }

    [Fact]
    public async Task OuterFunctionMiddlewareCompositionIsSupportedAsync()
    {
        // Arrange: the framework's function-invocation middleware composed OUTSIDE the
        // guarded agent (outer position, outer trust). Its per-run factory wraps the
        // guarded pipeline instead of replacing it, so it must be allowed — and the
        // enforcement's own tool seam must still bracket the invocation.
        bool outerMiddlewareSaw = false;
        var client = new MockChatClient()
            .EnqueueFunctionCall("call-1", "get_weather", new() { ["location"] = "Paris" })
            .EnqueueText("done");
        var guard = new AllowGuard();
        var guarded = client.AsAIAgentWithAgentHooks(new AgentHooksOptions(guard), AgentOptionsWithTools(WeatherTool()));
        var composed = new AIAgentBuilder(guarded)
            .Use(async (agent, context, next, cancellationToken) =>
            {
                outerMiddlewareSaw = true;
                return await next(context, cancellationToken);
            })
            .Build();

        // Act
        var response = await composed.RunAsync(UserMessage("weather?"));

        // Assert
        Assert.Equal("done", response.Text);
        Assert.True(outerMiddlewareSaw);
        Assert.Contains("pre_tool_call", guard.Points);
        Assert.Contains("post_tool_call", guard.Points);
    }

    [Fact]
    public async Task CallerFactorySmuggledThroughOuterFunctionMiddlewareIsRejectedAsync()
    {
        // Arrange: a caller-supplied ChatClientFactory hidden behind the framework's
        // outer function-invocation middleware (which chains pre-existing factories into
        // its own) must still be rejected — the chain is walked.
        var client = new MockChatClient().EnqueueText("never");
        var bypassClient = new MockChatClient().EnqueueText("bypassed");
        var guarded = client.AsAIAgentWithAgentHooks(new AgentHooksOptions(new AllowGuard()));
        var composed = new AIAgentBuilder(guarded)
            .Use((agent, context, next, cancellationToken) => next(context, cancellationToken))
            .Build();
        var runOptions = new ChatClientAgentRunOptions { ChatClientFactory = _ => bypassClient };

        // Act / Assert
        var exception = await Assert.ThrowsAsync<InvalidOperationException>(
            () => composed.RunAsync(UserMessage("hi"), null, runOptions));
        Assert.Contains("ChatClientFactory", exception.Message, StringComparison.Ordinal);
        Assert.Equal(0, bypassClient.CallCount);
    }

    [Fact]
    public void RederivedUpdatesPreserveTheContinuationToken()
    {
        // Arrange: a (transformed) background streaming response carries a continuation
        // token that ToAgentResponseUpdates() does not project.
        var token = ResponseContinuationToken.FromBytes(new byte[] { 1, 2, 3 });
        var response = new AgentResponse(new ChatMessage(ChatRole.Assistant, "[final]")) { ContinuationToken = token };

        // Act
        var updates = AgentHooksAgent.RederiveUpdates(response);

        // Assert: the token rides the last released update, so the response remains resumable.
        Assert.Same(token, updates[^1].ContinuationToken);

        // And a message-less response still releases a metadata-only update carrying it.
        var empty = new AgentResponse { ContinuationToken = token };
        var emptyUpdates = AgentHooksAgent.RederiveUpdates(empty);
        Assert.Same(token, Assert.Single(emptyUpdates).ContinuationToken);
    }

    [Fact]
    public async Task PerRunChatClientFactoryIsRejectedAsync()
    {
        // Arrange: a per-run ChatClientFactory would swap out the guarded pipeline (and
        // the tool wrapping riding it) — loud rejection, nothing egresses.
        var client = new MockChatClient().EnqueueText("never");
        var bypassClient = new MockChatClient().EnqueueText("bypassed-content");
        var agent = client.AsAIAgentWithAgentHooks(new AgentHooksOptions(new AllowGuard()));
        var runOptions = new ChatClientAgentRunOptions { ChatClientFactory = _ => bypassClient };

        // Act / Assert
        var exception = await Assert.ThrowsAsync<InvalidOperationException>(
            () => agent.RunAsync(UserMessage("hi"), null, runOptions));
        Assert.Contains("ChatClientFactory", exception.Message, StringComparison.Ordinal);
        Assert.Equal(0, client.CallCount);
        Assert.Equal(0, bypassClient.CallCount);
    }

    [Fact]
    public void UseProvidedChatClientAsIsIsRejected()
    {
        // Arrange: UseProvidedChatClientAsIs signals a fully custom, do-not-touch client
        // stack — incompatible with a factory whose job is to decorate that client and
        // rely on the agent's default pipeline above it. Honoring it would silently
        // change where (and whether) the seams sit.
        var client = new MockChatClient();

        // Act / Assert
        var exception = Assert.Throws<ArgumentException>(() => client.AsAIAgentWithAgentHooks(
            new AgentHooksOptions(new AllowGuard()),
            new ChatClientAgentOptions { UseProvidedChatClientAsIs = true }));
        Assert.Contains("UseProvidedChatClientAsIs", exception.Message, StringComparison.Ordinal);
    }

    [Fact]
    public void SuppliedClientContainingFunctionInvocationIsRejected()
    {
        // Arrange: a supplied client that already contains a FunctionInvokingChatClient
        // would execute tools below the chat seam, before any post_model_call verdict.
        var mock = new MockChatClient()
            .EnqueueFunctionCall("call-1", "get_weather", new() { ["location"] = "Paris" })
            .EnqueueText("done");
        var suppliedWithFicc = new FunctionInvokingChatClient(mock);

        // Act / Assert
        var exception = Assert.Throws<ArgumentException>(
            () => suppliedWithFicc.AsAIAgentWithAgentHooks(
                new AgentHooksOptions(new AllowGuard()), AgentOptionsWithTools(WeatherTool())));
        Assert.Contains("FunctionInvokingChatClient", exception.Message, StringComparison.Ordinal);
    }

    [Fact]
    public async Task DeniedRunFailureNotificationsAreRedactedForBothProviderKindsAsync()
    {
        // Arrange: a post_model_call deny makes the inner agent's run fail, which sends
        // failure notifications to BOTH provider kinds. Those notifications must still
        // arrive (failure-cleanup contract) but with the denied turn's request messages
        // redacted.
        var historyProvider = new RecordingHistoryProvider();
        var contextProvider = new RecordingContextProvider();
        var client = new MockChatClient().EnqueueText("secret");
        var agent = client.AsAIAgentWithAgentHooks(
            new AgentHooksOptions(new PointGuard(InterceptionPoint.PostModelCall, Verdict.Deny("bad_response"))),
            new ChatClientAgentOptions
            {
                ChatHistoryProvider = historyProvider,
                AIContextProviders = [contextProvider],
            });
        var session = await agent.CreateSessionAsync();

        // Act
        _ = await Assert.ThrowsAsync<InterceptionBlockedException>(() => agent.RunAsync(UserMessage("hi"), session));

        // Assert: both providers were notified of the failure, with zero request messages.
        var historyNotification = Assert.Single(historyProvider.FailureNotifications);
        Assert.Equal(0, historyNotification.RequestMessageCount);
        var contextNotification = Assert.Single(contextProvider.FailureNotifications);
        Assert.Equal(0, contextNotification.RequestMessageCount);
        Assert.Empty(historyProvider.Stored);
        Assert.Empty(contextProvider.StoredResponses);
    }

    [Fact]
    public async Task OrdinaryFailureNotificationsPassThroughUnredactedAsync()
    {
        // Arrange: a plain model failure (no verdict involved) — providers must receive
        // the full failure notification, request messages included.
        var historyProvider = new RecordingHistoryProvider();
        var contextProvider = new RecordingContextProvider();
        var client = new MockChatClient().EnqueueThrow(new TimeoutException("model down"));
        var agent = client.AsAIAgentWithAgentHooks(
            new AgentHooksOptions(new AllowGuard()),
            new ChatClientAgentOptions
            {
                ChatHistoryProvider = historyProvider,
                AIContextProviders = [contextProvider],
            });
        var session = await agent.CreateSessionAsync();

        // Act
        _ = await Assert.ThrowsAsync<TimeoutException>(() => agent.RunAsync(UserMessage("hi"), session));

        // Assert
        var historyNotification = Assert.Single(historyProvider.FailureNotifications);
        Assert.IsType<TimeoutException>(historyNotification.Exception);
        Assert.True(historyNotification.RequestMessageCount > 0);
        var contextNotification = Assert.Single(contextProvider.FailureNotifications);
        Assert.True(contextNotification.RequestMessageCount > 0);
    }

    [Fact]
    public async Task ContextProviderAddedToolsAreBracketedByTheToolSeamAsync()
    {
        // Arrange: NO agent-level tools — the only tool is registered dynamically by a
        // context provider during run preparation, i.e. after agent_startup was emitted.
        bool invoked = false;
        var provider = new ToolAddingContextProvider(WeatherTool(_ => invoked = true));
        var client = new MockChatClient()
            .EnqueueFunctionCall("call-1", "get_weather", new() { ["location"] = "Paris" })
            .EnqueueText("done");
        var guard = new AllowGuard();
        var agent = client.AsAIAgentWithAgentHooks(
            new AgentHooksOptions(guard),
            new ChatClientAgentOptions { AIContextProviders = [provider] });
        var session = await agent.CreateSessionAsync();

        // Act
        var response = await agent.RunAsync(UserMessage("weather?"), session);

        // Assert (enforcement): the provider-added tool still flows through the guarded
        // pipeline and is bracketed by the tool seam like any other tool.
        Assert.True(invoked);
        Assert.Equal("done", response.Text);
        Assert.Contains("pre_tool_call", guard.Points);
        Assert.Contains("post_tool_call", guard.Points);

        // Assert (audit): agent_startup's tools_registered is the run-start snapshot
        // (empty here — the provider had not run yet), while the pre_model_call tools
        // projection carries the completed per-call set including the provider's tool.
        var startupTools = Assert.IsType<System.Text.Json.Nodes.JsonArray>(
            guard.Context("agent_startup")["agent_init"]?["tools_registered"]);
        Assert.Empty(startupTools);
        var callTools = Assert.IsType<System.Text.Json.Nodes.JsonArray>(guard.Contexts("pre_model_call")[0]["tools"]);
        Assert.Contains(callTools, tool => tool?["name"]?.GetValue<string>() == "get_weather");
    }

    [Fact]
    public async Task ContextProviderAddedToolDenyBlocksInvocationAsync()
    {
        // Arrange: a pre_tool_call deny must block a provider-added tool exactly like a
        // constructor-registered one.
        bool invoked = false;
        var provider = new ToolAddingContextProvider(WeatherTool(_ => invoked = true));
        var client = new MockChatClient()
            .EnqueueFunctionCall("call-1", "get_weather", new() { ["location"] = "Paris" })
            .EnqueueText("recovered");
        var agent = client.AsAIAgentWithAgentHooks(
            new AgentHooksOptions(new PointGuard(InterceptionPoint.PreToolCall, Verdict.Deny("tool_blocked"))),
            new ChatClientAgentOptions { AIContextProviders = [provider] });
        var session = await agent.CreateSessionAsync();

        // Act
        var response = await agent.RunAsync(UserMessage("weather?"), session);

        // Assert: the tool never ran and the loop continued with the tool-error payload.
        Assert.False(invoked);
        Assert.Equal("recovered", response.Text);
    }

    [Fact]
    public async Task PoisonedToolArgumentProjectionFailsClosedAsync()
    {
        // Arrange: an argument value whose serialization throws. The projection failure
        // surfaces at the chat seam (post_model_call projects the tool-call args before
        // the function loop ever invokes): the run must fail closed — no tool execution,
        // no silent continuation, gated persistence refused, trail closed as error.
        bool invoked = false;
        var tool = AIFunctionFactory.Create((object p) => { invoked = true; return "ran"; }, "poison_tool");
        var provider = new RecordingHistoryProvider();
        var options = AgentOptionsWithTools(tool);
        options.ChatHistoryProvider = provider;
        var client = new MockChatClient()
            .EnqueueFunctionCall("call-1", "poison_tool", new() { ["p"] = new PoisonedValue() })
            .EnqueueText("recovered");
        var guard = new AllowGuard();
        var agent = client.AsAIAgentWithAgentHooks(new AgentHooksOptions(guard), options);
        var session = await agent.CreateSessionAsync();

        // Act / Assert
        _ = await Assert.ThrowsAsync<ArgumentException>(() => agent.RunAsync(UserMessage("go"), session));
        Assert.False(invoked);
        Assert.Empty(provider.Stored);
        Assert.Equal("error", guard.Context("agent_shutdown")["summary"]?["reason"]?.GetValue<string>());
    }
}
