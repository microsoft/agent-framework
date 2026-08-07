// Copyright (c) Microsoft. All rights reserved.

using System;
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
