// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Linq;
using System.Runtime.CompilerServices;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Moq;
using OpenTelemetry.Trace;

namespace Microsoft.Agents.AI.UnitTests;

/// <summary>
/// Unit tests verifying that a <see cref="ChatClientAgent"/> rolls up the usage of the sub-agents it invokes into its
/// own <see cref="AgentResponse.Usage"/>.
/// </summary>
public class ChatClientAgent_SubAgentUsageTests
{
    // Every scripted model call made by a tool-calling agent reports this usage, and such an agent makes two model
    // calls per run (one requesting the tool calls, one producing the final answer).
    private const long OwnInputPerCall = 10;
    private const long OwnOutputPerCall = 5;
    private const long OwnInputPerRun = 2 * OwnInputPerCall;
    private const long OwnOutputPerRun = 2 * OwnOutputPerCall;

    /// <summary>
    /// Verify that the usage of a sub-agent invoked through AsAIFunction is added to the parent's usage.
    /// </summary>
    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task Run_SubAgentViaAsAIFunction_ParentUsageIncludesSubAgentUsageAsync(bool streaming)
    {
        // Arrange
        ChatClientAgent child = CreateTextAgent("Child", Usage(100, 50));
        ChatClientAgent parent = CreateToolCallingAgent("Parent", child.AsAIFunction());

        // Act
        AgentResponse response = await RunAsync(parent, streaming);

        // Assert
        AssertUsage(response.Usage, OwnInputPerRun + 100, OwnOutputPerRun + 50);
    }

    /// <summary>
    /// Verify that a streaming run ends with an update carrying only the rolled-up sub-agent usage.
    /// </summary>
    [Fact]
    public async Task RunStreamingAsync_SubAgentViaAsAIFunction_LastUpdateCarriesSubAgentUsageAsync()
    {
        // Arrange
        ChatClientAgent child = CreateTextAgent("Child", Usage(100, 50));
        ChatClientAgent parent = CreateToolCallingAgent("Parent", child.AsAIFunction());

        // Act
        List<AgentResponseUpdate> updates = [];
        await foreach (AgentResponseUpdate update in parent.RunStreamingAsync("question"))
        {
            updates.Add(update);
        }

        // Assert
        AgentResponseUpdate last = updates[updates.Count - 1];
        Assert.Null(last.Role);
        Assert.Equal(parent.Id, last.AgentId);
        UsageContent usageContent = Assert.IsType<UsageContent>(Assert.Single(last.Contents));
        Assert.True(SubAgentUsageScope.IsSubAgentUsageContent(usageContent));
        AssertUsage(usageContent.Details, 100, 50);
    }

    /// <summary>
    /// Verify that in a chain A → B → C every agent's usage is counted exactly once.
    /// </summary>
    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task Run_NestedSubAgents_CountsEachLayerOnceAsync(bool streaming)
    {
        // Arrange
        ChatClientAgent c = CreateTextAgent("C", Usage(1000, 500));
        ChatClientAgent b = CreateToolCallingAgent("B", c.AsAIFunction());
        ChatClientAgent a = CreateToolCallingAgent("A", b.AsAIFunction());

        // Act
        AgentResponse response = await RunAsync(a, streaming);

        // Assert: A's own usage + B's own usage + C's usage, each once.
        AssertUsage(response.Usage, (2 * OwnInputPerRun) + 1000, (2 * OwnOutputPerRun) + 500);
    }

    /// <summary>
    /// Verify that the usage of sub-agents invoked concurrently is summed correctly.
    /// </summary>
    [Fact]
    public async Task RunAsync_ConcurrentSubAgentCalls_SumsAllSubAgentUsageAsync()
    {
        // Arrange: three tool calls in one response, invoked concurrently. Each child waits until all three have started,
        // so the usage is reported concurrently.
        const int CallCount = 3;
        int started = 0;
        var allStarted = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
        var child = new TestAIAgent
        {
            NameFunc = () => "Child",
            RunAsyncFunc = async (_, _, _, cancellationToken) =>
            {
                if (Interlocked.Increment(ref started) == CallCount)
                {
                    allStarted.TrySetResult(true);
                }

                await Task.WhenAny(allStarted.Task, Task.Delay(TimeSpan.FromSeconds(10), cancellationToken));
                return new AgentResponse(new ChatMessage(ChatRole.Assistant, "child answer")) { Usage = Usage(100, 50) };
            },
        };

        IChatClient chatClient = new ChatClientBuilder(CreateToolCallingClient("Child", CallCount))
            .UseFunctionInvocation(configure: f => f.AllowConcurrentInvocation = true)
            .Build();
        var parent = new ChatClientAgent(chatClient, new ChatClientAgentOptions
        {
            Name = "Parent",
            ChatOptions = new() { Tools = [child.AsAIFunction()] },
        });

        // Act
        AgentResponse response = await parent.RunAsync("question");

        // Assert
        Assert.Equal(CallCount, started);
        AssertUsage(response.Usage, OwnInputPerRun + (CallCount * 100), OwnOutputPerRun + (CallCount * 50));
    }

    /// <summary>
    /// Verify that a sub-agent reporting no usage leaves the parent's usage unchanged.
    /// </summary>
    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task Run_SubAgentWithNullUsage_ParentUsageUnchangedAsync(bool streaming)
    {
        // Arrange
        ChatClientAgent child = CreateTextAgent("Child", usage: null);
        ChatClientAgent parent = CreateToolCallingAgent("Parent", child.AsAIFunction());

        // Act
        List<AgentResponseUpdate> updates = [];
        AgentResponse response;
        if (streaming)
        {
            await foreach (AgentResponseUpdate update in parent.RunStreamingAsync("question"))
            {
                updates.Add(update);
            }

            response = updates.ToAgentResponse();
        }
        else
        {
            response = await parent.RunAsync("question");
        }

        // Assert
        AssertUsage(response.Usage, OwnInputPerRun, OwnOutputPerRun);
        Assert.DoesNotContain(updates, u => u.Contents.Any(SubAgentUsageScope.IsSubAgentUsageContent));
    }

    /// <summary>
    /// Verify that a function created by AsAIFunction does nothing with usage when no agent run is in progress.
    /// </summary>
    [Fact]
    public async Task AsAIFunction_NoScope_DoesNotRecordUsageAsync()
    {
        // Arrange
        SubAgentUsageScope.Current = null;
        AIFunction function = CreateTextAgent("Child", Usage(100, 50)).AsAIFunction();

        // Act
        object? result = await function.InvokeAsync(new AIFunctionArguments { ["query"] = "question" });

        // Assert
        Assert.NotNull(result);
        Assert.Null(SubAgentUsageScope.Current);
    }

    /// <summary>
    /// Verify that a function created by AsAIFunction adds the sub-agent's usage to the scope in progress, and that the
    /// sub-agent itself runs without the caller's scope, so its usage is only counted at the call boundary.
    /// </summary>
    [Fact]
    public async Task AsAIFunction_WithScope_AddsSubAgentUsageAndClearsScopeForSubAgentAsync()
    {
        // Arrange
        SubAgentUsageScope.UsageAccumulator? scopeSeenByChild = new();
        var child = new TestAIAgent
        {
            NameFunc = () => "Child",
            RunAsyncFunc = (_, _, _, _) =>
            {
                scopeSeenByChild = SubAgentUsageScope.Current;
                return Task.FromResult(new AgentResponse(new ChatMessage(ChatRole.Assistant, "child answer")) { Usage = Usage(100, 50) });
            },
        };
        var accumulator = new SubAgentUsageScope.UsageAccumulator();
        SubAgentUsageScope.Current = accumulator;

        // Act
        await child.AsAIFunction().InvokeAsync(new AIFunctionArguments { ["query"] = "question" });

        // Assert
        Assert.Null(scopeSeenByChild);
        Assert.Same(accumulator, SubAgentUsageScope.Current);
        AssertUsage(accumulator.GetTotal(), 100, 50);
    }

    /// <summary>
    /// Verify that the invoke_agent span reports the agent's own usage only, while the response includes the sub-agent usage.
    /// </summary>
    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task Run_WithOpenTelemetry_SpanExcludesSubAgentUsageAsync(bool streaming)
    {
        // Arrange
        string sourceName = Guid.NewGuid().ToString();
        var activities = new List<Activity>();
        using TracerProvider tracerProvider = OpenTelemetry.Sdk.CreateTracerProviderBuilder()
            .AddSource(sourceName)
            .AddInMemoryExporter(activities)
            .Build();

        ChatClientAgent child = CreateTextAgent("Child", Usage(100, 50));
        AIAgent parent = CreateToolCallingAgent("Parent", child.AsAIFunction())
            .AsBuilder()
            .UseOpenTelemetry(sourceName)
            .Build();

        // Act
        AgentResponse response = await RunAsync(parent, streaming);

        // Assert
        AssertUsage(response.Usage, OwnInputPerRun + 100, OwnOutputPerRun + 50);

        Activity invokeAgent;
        lock (activities)
        {
            invokeAgent = Assert.Single(activities, a => (a.GetTagItem("gen_ai.operation.name") as string) == "invoke_agent");
        }

        Assert.Equal(OwnInputPerRun, Convert.ToInt64(invokeAgent.GetTagItem("gen_ai.usage.input_tokens")));
        Assert.Equal(OwnOutputPerRun, Convert.ToInt64(invokeAgent.GetTagItem("gen_ai.usage.output_tokens")));
    }

    /// <summary>
    /// Verify that the usage of a background agent is charged to the parent run that observes its completion through the
    /// wait tool, and not again in a later run.
    /// </summary>
    [Fact]
    public async Task RunAsync_BackgroundAgentObservedByWaitTool_ChargedOnceAsync()
    {
        // Arrange
        ChatClientAgent worker = CreateTextAgent("Worker", Usage(100, 50));
        var provider = new BackgroundAgentsProvider([worker]);

        int callIndex = 0;
        var parentClient = new ScriptedChatClient(_ =>
        {
            ChatMessage message = Interlocked.Increment(ref callIndex) switch
            {
                1 => new(ChatRole.Assistant, [new FunctionCallContent("call1", "background_agents_start_task", new Dictionary<string, object?>
                {
                    ["agentName"] = "Worker",
                    ["input"] = "do the work",
                    ["description"] = "work",
                })]),
                2 => new(ChatRole.Assistant, [new FunctionCallContent("call2", "background_agents_wait_for_first_completion", new Dictionary<string, object?>
                {
                    ["taskIds"] = new List<int> { 1 },
                })]),
                _ => new(ChatRole.Assistant, "done"),
            };

            return new ChatResponse(message) { Usage = Usage(OwnInputPerCall, OwnOutputPerCall) };
        });

        var parent = new ChatClientAgent(parentClient, new ChatClientAgentOptions
        {
            Name = "Parent",
            AIContextProviders = [provider],
        });
        AgentSession session = await parent.CreateSessionAsync();

        // Act
        AgentResponse first = await parent.RunAsync("start the work", session);
        AgentResponse second = await parent.RunAsync("anything else?", session);

        // Assert
        Assert.Equal(4, callIndex);
        AssertUsage(first.Usage, (3 * OwnInputPerCall) + 100, (3 * OwnOutputPerCall) + 50);
        AssertUsage(second.Usage, OwnInputPerCall, OwnOutputPerCall);
    }

    /// <summary>
    /// Verify that the usage of a background agent that finished between parent runs is charged once, to the next parent
    /// run, and not again when the task is later finalized by a tool.
    /// </summary>
    [Fact]
    public async Task BackgroundAgentsProvider_RunFinishedBetweenParentRuns_ChargedOnceToNextRunAsync()
    {
        // Arrange
        ChatClientAgent worker = CreateTextAgent("Worker", Usage(100, 50));
        var provider = new BackgroundAgentsProvider([worker]);
        var session = new ChatClientAgentSession();

        var firstRun = new SubAgentUsageScope.UsageAccumulator();
        SubAgentUsageScope.Current = firstRun;
        AIContext firstContext = await InvokeProviderAsync(provider, session);
        await GetTool(firstContext, "background_agents_start_task").InvokeAsync(new AIFunctionArguments
        {
            ["agentName"] = "Worker",
            ["input"] = "do the work",
            ["description"] = "work",
        });

        // Wait for the background run to finish without finalizing it.
        string runtimeStateKey = provider.StateKeys[1];
        Assert.True(session.StateBag.TryGetValue(runtimeStateKey, out BackgroundAgentRuntimeState? runtimeState, AgentJsonUtilities.DefaultOptions));
        Task<AgentResponse> backgroundRun;
        lock (runtimeState!.SyncRoot)
        {
            backgroundRun = runtimeState.InFlightTasks[1];
        }

        await backgroundRun;

        // Act: the next parent run observes the finished run when its context is provided.
        var secondRun = new SubAgentUsageScope.UsageAccumulator();
        SubAgentUsageScope.Current = secondRun;
        await InvokeProviderAsync(provider, session);

        // A third parent run observes it again and then finalizes it through a tool.
        var thirdRun = new SubAgentUsageScope.UsageAccumulator();
        SubAgentUsageScope.Current = thirdRun;
        AIContext thirdContext = await InvokeProviderAsync(provider, session);
        object? result = await GetTool(thirdContext, "background_agents_get_task_results").InvokeAsync(new AIFunctionArguments { ["taskId"] = 1 });

        // Assert
        Assert.Null(firstRun.GetTotal());
        AssertUsage(secondRun.GetTotal(), 100, 50);
        Assert.Null(thirdRun.GetTotal());
        Assert.Contains("child answer", result?.ToString());
    }

    /// <summary>
    /// Verify that a sub-agent's usage counts toward the LoopAgent token budget.
    /// </summary>
    [Fact]
    public async Task LoopAgent_SubAgentUsage_TriggersTokenBudgetAsync()
    {
        // Arrange: each iteration costs 30 own tokens plus 150 sub-agent tokens. Without the sub-agent usage, the budget
        // would not be reached before the iteration cap.
        int childCalls = 0;
        var child = new TestAIAgent
        {
            NameFunc = () => "Child",
            RunAsyncFunc = (_, _, _, _) =>
            {
                Interlocked.Increment(ref childCalls);
                return Task.FromResult(new AgentResponse(new ChatMessage(ChatRole.Assistant, "child answer")) { Usage = Usage(100, 50) });
            },
        };
        ChatClientAgent parent = CreateToolCallingAgent("Parent", child.AsAIFunction());
        var loop = new LoopAgent(parent, LoopTestHelpers.While(_ => true), new LoopAgentOptions { MaxTokens = 200, MaxIterations = 10 });

        // Act
        AgentResponse response = await loop.RunAsync("task", new ChatClientAgentSession());

        // Assert: 180 < 200 after iteration 1, 360 >= 200 after iteration 2.
        Assert.Equal(2, childCalls);
        Assert.NotNull(response.AdditionalProperties);
        Assert.Equal(LoopExitReason.TokenBudgetExceeded, response.AdditionalProperties![LoopExitReason.AdditionalPropertiesKey]);
    }

    private static UsageDetails Usage(long input, long output) =>
        new() { InputTokenCount = input, OutputTokenCount = output, TotalTokenCount = input + output };

    private static void AssertUsage(UsageDetails? usage, long expectedInput, long expectedOutput)
    {
        Assert.NotNull(usage);
        Assert.Equal(expectedInput, usage!.InputTokenCount);
        Assert.Equal(expectedOutput, usage.OutputTokenCount);
        Assert.Equal(expectedInput + expectedOutput, usage.TotalTokenCount);
    }

    private static async Task<AgentResponse> RunAsync(AIAgent agent, bool streaming)
    {
        if (!streaming)
        {
            return await agent.RunAsync("question");
        }

        List<AgentResponseUpdate> updates = [];
        await foreach (AgentResponseUpdate update in agent.RunStreamingAsync("question"))
        {
            updates.Add(update);
        }

        return updates.ToAgentResponse();
    }

    /// <summary>Creates an agent that answers with text, reporting <paramref name="usage"/>.</summary>
    private static ChatClientAgent CreateTextAgent(string name, UsageDetails? usage) =>
        new(
            new ScriptedChatClient(_ => new ChatResponse(new ChatMessage(ChatRole.Assistant, "child answer"))
            {
                Usage = usage is null ? null : Usage(usage.InputTokenCount!.Value, usage.OutputTokenCount!.Value),
            }),
            new ChatClientAgentOptions { Name = name });

    /// <summary>Creates an agent that calls <paramref name="tool"/> once and then answers with text.</summary>
    private static ChatClientAgent CreateToolCallingAgent(string name, AIFunction tool) =>
        new(CreateToolCallingClient(tool.Name, callCount: 1), new ChatClientAgentOptions
        {
            Name = name,
            ChatOptions = new() { Tools = [tool] },
        });

    /// <summary>
    /// Creates a chat client that requests <paramref name="callCount"/> calls to <paramref name="toolName"/> when the last
    /// message is not a tool result, and answers with text otherwise. Every call reports the same own usage.
    /// </summary>
    private static ScriptedChatClient CreateToolCallingClient(string toolName, int callCount) =>
        new(messages =>
        {
            ChatMessage message = messages[messages.Count - 1].Contents.OfType<FunctionResultContent>().Any()
                ? new(ChatRole.Assistant, "parent answer")
                : new(ChatRole.Assistant, Enumerable.Range(0, callCount)
                    .Select(i => (AIContent)new FunctionCallContent($"call{i}", toolName, new Dictionary<string, object?> { ["query"] = "sub question" }))
                    .ToList());

            return new ChatResponse(message) { Usage = Usage(OwnInputPerCall, OwnOutputPerCall) };
        });

    private static async Task<AIContext> InvokeProviderAsync(BackgroundAgentsProvider provider, AgentSession session)
    {
#pragma warning disable MAAI001
        var context = new AIContextProvider.InvokingContext(new Mock<AIAgent>().Object, session, new AIContext());
#pragma warning restore MAAI001
        return await provider.InvokingAsync(context);
    }

    private static AIFunction GetTool(AIContext context, string name) =>
        (AIFunction)context.Tools!.First(t => t is AIFunction f && f.Name == name);

    /// <summary>A chat client whose responses are produced by a callback, streamed as the equivalent updates.</summary>
    private sealed class ScriptedChatClient(Func<IList<ChatMessage>, ChatResponse> handler) : IChatClient
    {
        public Task<ChatResponse> GetResponseAsync(IEnumerable<ChatMessage> messages, ChatOptions? options = null, CancellationToken cancellationToken = default) =>
            Task.FromResult(handler(messages.ToList()));

        public async IAsyncEnumerable<ChatResponseUpdate> GetStreamingResponseAsync(
            IEnumerable<ChatMessage> messages, ChatOptions? options = null, [EnumeratorCancellation] CancellationToken cancellationToken = default)
        {
            await Task.Yield();
            foreach (ChatResponseUpdate update in handler(messages.ToList()).ToChatResponseUpdates())
            {
                yield return update;
            }
        }

        public object? GetService(Type serviceType, object? serviceKey = null) =>
            serviceKey is null && serviceType.IsInstanceOfType(this) ? this : null;

        public void Dispose()
        {
        }
    }
}
