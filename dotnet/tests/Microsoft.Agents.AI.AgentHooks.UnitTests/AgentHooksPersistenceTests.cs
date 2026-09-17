// Copyright (c) Microsoft. All rights reserved.

using System.Linq;
using System.Text.Json.Nodes;
using System.Threading.Tasks;
using AgentHooks;
using Microsoft.Extensions.AI;
using static Microsoft.Agents.AI.AgentHooks.UnitTests.TestHelpers;

namespace Microsoft.Agents.AI.AgentHooks.UnitTests;

/// <summary>
/// Verdict-before-durability: denied content never becomes durable, transformed content
/// persists post-transform, per-service-call persistence is covered by its own verdict,
/// and nested runs persist inline at their own boundaries.
/// </summary>
public class AgentHooksPersistenceTests
{
    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task DeniedOutputNeverBecomesDurableHistoryAsync(bool streaming)
    {
        // Arrange
        var provider = new RecordingHistoryProvider();
        var client = new MockChatClient().EnqueueText("secret");
        var agent = client.AsAIAgentWithAgentHooks(
            new AgentHooksOptions(new PointGuard(InterceptionPoint.Output, Verdict.Deny("egress_blocked"))),
            new ChatClientAgentOptions { ChatHistoryProvider = provider });
        var session = await agent.CreateSessionAsync();

        // Act
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

        // Assert: neither the denied response nor the denied turn's input persisted.
        Assert.Equal(0, provider.StoreCalls);
        Assert.Empty(provider.Stored);
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task TransformedOutputIsPersistedPostTransformAsync(bool streaming)
    {
        // Arrange
        var provider = new RecordingHistoryProvider();
        var client = new MockChatClient().EnqueueText("raw output");
        var transform = TransformTarget(new JsonObject { ["content"] = "[final]" });
        var agent = client.AsAIAgentWithAgentHooks(
            new AgentHooksOptions(new PointGuard(InterceptionPoint.Output, transform)),
            new ChatClientAgentOptions { ChatHistoryProvider = provider });
        var session = await agent.CreateSessionAsync();

        // Act
        if (streaming)
        {
            _ = await CollectAsync(agent.RunStreamingAsync(UserMessage("hi"), session));
        }
        else
        {
            _ = await agent.RunAsync(UserMessage("hi"), session);
        }

        // Assert: what became durable is the verdicted (transformed) content.
        Assert.Equal(1, provider.StoreCalls);
        string storedText = string.Concat(provider.Stored.Where(m => m.Role == ChatRole.Assistant).Select(m => m.Text));
        Assert.Equal("[final]", storedText);
    }

    [Fact]
    public async Task PermittedRunPersistsExactlyOnceAsync()
    {
        // Arrange
        var provider = new RecordingHistoryProvider();
        var client = new MockChatClient().EnqueueText("fine");
        var agent = client.AsAIAgentWithAgentHooks(
            new AgentHooksOptions(new AllowGuard()),
            new ChatClientAgentOptions { ChatHistoryProvider = provider });
        var session = await agent.CreateSessionAsync();

        // Act
        _ = await agent.RunAsync(UserMessage("hi"), session);

        // Assert
        Assert.Equal(1, provider.StoreCalls);
        Assert.Contains(provider.Stored, message => message.Text == "fine");
        Assert.Contains(provider.Stored, message => message.Text == "hi");
    }

    [Fact]
    public async Task DeniedOutputNeverReachesContextProvidersAsync()
    {
        // Arrange
        var contextProvider = new RecordingContextProvider();
        var client = new MockChatClient().EnqueueText("secret");
        var agent = client.AsAIAgentWithAgentHooks(
            new AgentHooksOptions(new PointGuard(InterceptionPoint.Output, Verdict.Deny("no"))),
            new ChatClientAgentOptions { AIContextProviders = [contextProvider] });
        var session = await agent.CreateSessionAsync();

        // Act
        _ = await Assert.ThrowsAsync<InterceptionBlockedException>(() => agent.RunAsync(UserMessage("hi"), session));

        // Assert
        Assert.Equal(0, contextProvider.StoreCalls);
    }

    [Fact]
    public async Task PermittedRunReachesContextProvidersPostVerdictAsync()
    {
        // Arrange
        var contextProvider = new RecordingContextProvider();
        var client = new MockChatClient().EnqueueText("raw");
        var transform = TransformTarget(new JsonObject { ["content"] = "[final]" });
        var agent = client.AsAIAgentWithAgentHooks(
            new AgentHooksOptions(new PointGuard(InterceptionPoint.Output, transform)),
            new ChatClientAgentOptions { AIContextProviders = [contextProvider] });
        var session = await agent.CreateSessionAsync();

        // Act
        _ = await agent.RunAsync(UserMessage("hi"), session);

        // Assert
        Assert.Equal(1, contextProvider.StoreCalls);
        Assert.Contains(contextProvider.StoredResponses, message => message.Text == "[final]");
    }

    [Fact]
    public async Task PerServiceCallPersistenceIsCoveredByItsOwnVerdictAsync()
    {
        // Arrange: per-service-call persistence with a run whose output is denied.
        var provider = new RecordingHistoryProvider();
        var client = new MockChatClient()
            .EnqueueFunctionCall("call-1", "get_weather", new() { ["location"] = "Paris" })
            .EnqueueText("done");
        var options = AgentOptionsWithTools(WeatherTool());
        options.ChatHistoryProvider = provider;
        options.RequirePerServiceCallChatHistoryPersistence = true;
        var agent = client.AsAIAgentWithAgentHooks(
            new AgentHooksOptions(new PointGuard(InterceptionPoint.Output, Verdict.Deny("egress_blocked"))),
            options);
        var session = await agent.CreateSessionAsync();

        // Act
        _ = await Assert.ThrowsAsync<InterceptionBlockedException>(() => agent.RunAsync(UserMessage("weather?"), session));

        // Assert: history persisted under a permitted post_model_call verdict remains
        // durable even though the run's output was later denied.
        Assert.True(provider.StoreCalls >= 1);
        Assert.Contains(provider.Stored, message => message.Contents.OfType<FunctionCallContent>().Any());
    }

    [Fact]
    public async Task DeniedModelResponseNeverPersistsPerServiceCallAsync()
    {
        // Arrange: per-service-call persistence with the first model response denied.
        var provider = new RecordingHistoryProvider();
        var client = new MockChatClient().EnqueueText("secret");
        var options = new ChatClientAgentOptions
        {
            ChatHistoryProvider = provider,
            RequirePerServiceCallChatHistoryPersistence = true,
        };
        var agent = client.AsAIAgentWithAgentHooks(
            new AgentHooksOptions(new PointGuard(InterceptionPoint.PostModelCall, Verdict.Deny("bad_response"))),
            options);
        var session = await agent.CreateSessionAsync();

        // Act
        _ = await Assert.ThrowsAsync<InterceptionBlockedException>(() => agent.RunAsync(UserMessage("hi"), session));

        // Assert: neither the denied response nor the denied turn's request messages persisted.
        Assert.DoesNotContain(provider.Stored, message => message.Text == "secret");
        Assert.DoesNotContain(provider.Stored, message => message.Text == "hi");
    }

    [Fact]
    public async Task PerServiceCallPersistenceStillPersistsOnAllowAsync()
    {
        // Arrange
        var provider = new RecordingHistoryProvider();
        var client = new MockChatClient()
            .EnqueueFunctionCall("call-1", "get_weather", new() { ["location"] = "Paris" })
            .EnqueueText("done");
        var options = AgentOptionsWithTools(WeatherTool());
        options.ChatHistoryProvider = provider;
        options.RequirePerServiceCallChatHistoryPersistence = true;
        var agent = client.AsAIAgentWithAgentHooks(new AgentHooksOptions(new AllowGuard()), options);
        var session = await agent.CreateSessionAsync();

        // Act
        var response = await agent.RunAsync(UserMessage("weather?"), session);

        // Assert: both service calls persisted.
        Assert.Equal("done", response.Text);
        Assert.True(provider.StoreCalls >= 2);
        Assert.Contains(provider.Stored, message => message.Text == "done");
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task OuterDenyNeverDropsPermittedNestedRunHistoryAsync(bool streaming)
    {
        // Arrange: a guarded sub-agent (own provider, own session) invoked as a tool of
        // a guarded outer agent whose output is denied.
        var subProvider = new RecordingHistoryProvider();
        var subClient = new MockChatClient().EnqueueText("sub answer");
        var subAgent = subClient.AsAIAgentWithAgentHooks(
            new AgentHooksOptions(new AllowGuard()),
            new ChatClientAgentOptions { ChatHistoryProvider = subProvider });
        var subTool = AIFunctionFactory.Create(
            async () =>
            {
                var subSession = await subAgent.CreateSessionAsync();
                return (await subAgent.RunAsync(UserMessage("inner"), subSession)).Text;
            },
            "ask_sub_agent");

        var outerProvider = new RecordingHistoryProvider();
        var outerClient = new MockChatClient()
            .EnqueueFunctionCall("call-1", "ask_sub_agent", [])
            .EnqueueText("outer secret");
        var outerOptions = AgentOptionsWithTools(subTool);
        outerOptions.ChatHistoryProvider = outerProvider;
        var outerAgent = outerClient.AsAIAgentWithAgentHooks(
            new AgentHooksOptions(new PointGuard(InterceptionPoint.Output, Verdict.Deny("egress_blocked"))),
            outerOptions);
        var outerSession = await outerAgent.CreateSessionAsync();

        // Act
        if (streaming)
        {
            _ = await Assert.ThrowsAsync<InterceptionBlockedException>(async () =>
            {
                await foreach (var _ in outerAgent.RunStreamingAsync(UserMessage("go"), outerSession))
                {
                }
            });
        }
        else
        {
            _ = await Assert.ThrowsAsync<InterceptionBlockedException>(() => outerAgent.RunAsync(UserMessage("go"), outerSession));
        }

        // Assert: the outer deny dropped only the outer run's persistence; the nested
        // run's fully-permitted history persisted inline at its own run boundary.
        Assert.Empty(outerProvider.Stored);
        Assert.Contains(subProvider.Stored, message => message.Text == "sub answer");
    }

    [Fact]
    public async Task PerRunHistoryProviderOverrideIsGatedTooAsync()
    {
        // Arrange: a per-run ChatHistoryProvider override smuggled through the run
        // options would bypass the construction-time wrapper; the agent seam wraps it.
        var overrideProvider = new RecordingHistoryProvider();
        var client = new MockChatClient().EnqueueText("secret");
        var agent = client.AsAIAgentWithAgentHooks(
            new AgentHooksOptions(new PointGuard(InterceptionPoint.Output, Verdict.Deny("egress_blocked"))));
        var session = await agent.CreateSessionAsync();
        var runOptions = new ChatClientAgentRunOptions
        {
            ChatOptions = new ChatOptions { AdditionalProperties = [] },
        };
        runOptions.ChatOptions.AdditionalProperties!.Add<ChatHistoryProvider>(overrideProvider);

        // Act
        _ = await Assert.ThrowsAsync<InterceptionBlockedException>(
            () => agent.RunAsync(UserMessage("hi"), session, runOptions));

        // Assert
        Assert.Empty(overrideProvider.Stored);
    }
}
