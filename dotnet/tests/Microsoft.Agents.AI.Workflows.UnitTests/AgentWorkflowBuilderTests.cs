// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Runtime.CompilerServices;
using System.Text;
using System.Text.Json;
using System.Text.RegularExpressions;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.InProc;
using Microsoft.Extensions.AI;

#pragma warning disable SYSLIB1045 // Use GeneratedRegex
#pragma warning disable RCS1186 // Use Regex instance instead of static method

namespace Microsoft.Agents.AI.Workflows.UnitTests;

public class AgentWorkflowBuilderTests
{
    [Fact]
    public void BuildSequential_InvalidArguments_Throws()
    {
        Assert.Throws<ArgumentNullException>("agents", () => AgentWorkflowBuilder.BuildSequential(workflowName: null!, null!));
        Assert.Throws<ArgumentException>("agents", () => AgentWorkflowBuilder.BuildSequential());
    }

    [Fact]
    public void BuildConcurrent_InvalidArguments_Throws()
    {
        Assert.Throws<ArgumentNullException>("agents", () => AgentWorkflowBuilder.BuildConcurrent(null!));
    }

    [Fact]
    public void BuildGroupChat_InvalidArguments_Throws()
    {
        Assert.Throws<ArgumentNullException>("managerFactory", () => AgentWorkflowBuilder.CreateGroupChatBuilderWith(null!));

        var groupChat = AgentWorkflowBuilder.CreateGroupChatBuilderWith(_ => new RoundRobinGroupChatManager([new DoubleEchoAgent("a1")]));
        Assert.NotNull(groupChat);
        Assert.Throws<ArgumentNullException>("agents", () => groupChat.AddParticipants(null!));
        Assert.Throws<ArgumentNullException>("agents", () => groupChat.AddParticipants([null!]));
        Assert.Throws<ArgumentNullException>("agents", () => groupChat.AddParticipants(new DoubleEchoAgent("a1"), null!));

        Assert.Throws<ArgumentNullException>("agents", () => new RoundRobinGroupChatManager(null!));
    }

    [Fact]
    public void GroupChatManager_MaximumIterationCount_Invalid_Throws()
    {
        var manager = new RoundRobinGroupChatManager([new DoubleEchoAgent("a1")]);

        const int DefaultMaxIterations = 40;
        Assert.Equal(DefaultMaxIterations, manager.MaximumIterationCount);
        Assert.Throws<ArgumentOutOfRangeException>("value", void () => manager.MaximumIterationCount = 0);
        Assert.Throws<ArgumentOutOfRangeException>("value", void () => manager.MaximumIterationCount = -1);
        Assert.Equal(DefaultMaxIterations, manager.MaximumIterationCount);

        manager.MaximumIterationCount = 30;
        Assert.Equal(30, manager.MaximumIterationCount);

        manager.MaximumIterationCount = 1;
        Assert.Equal(1, manager.MaximumIterationCount);

        manager.MaximumIterationCount = int.MaxValue;
        Assert.Equal(int.MaxValue, manager.MaximumIterationCount);
    }

    [Fact]
    public void BuildGroupChat_WithNameAndDescription_SetsWorkflowNameAndDescription()
    {
        const string WorkflowName = "Test Group Chat";
        const string WorkflowDescription = "A test group chat workflow";

        var workflow = AgentWorkflowBuilder
            .CreateGroupChatBuilderWith(agents => new RoundRobinGroupChatManager(agents) { MaximumIterationCount = 2 })
            .AddParticipants(new DoubleEchoAgent("agent1"), new DoubleEchoAgent("agent2"))
            .WithName(WorkflowName)
            .WithDescription(WorkflowDescription)
            .Build();

        Assert.Equal(WorkflowName, workflow.Name);
        Assert.Equal(WorkflowDescription, workflow.Description);
    }

    [Fact]
    public void BuildGroupChat_WithNameOnly_SetsWorkflowName()
    {
        const string WorkflowName = "Named Group Chat";

        var workflow = AgentWorkflowBuilder
            .CreateGroupChatBuilderWith(agents => new RoundRobinGroupChatManager(agents) { MaximumIterationCount = 2 })
            .AddParticipants(new DoubleEchoAgent("agent1"))
            .WithName(WorkflowName)
            .Build();

        Assert.Equal(WorkflowName, workflow.Name);
        Assert.Null(workflow.Description);
    }

    [Fact]
    public void BuildGroupChat_WithoutNameOrDescription_DefaultsToNull()
    {
        var workflow = AgentWorkflowBuilder
            .CreateGroupChatBuilderWith(agents => new RoundRobinGroupChatManager(agents) { MaximumIterationCount = 2 })
            .AddParticipants(new DoubleEchoAgent("agent1"))
            .Build();

        Assert.Null(workflow.Name);
        Assert.Null(workflow.Description);
    }

    [Theory]
    [InlineData(1)]
    [InlineData(2)]
    [InlineData(3)]
    [InlineData(4)]
    [InlineData(5)]
    public async Task BuildSequential_AgentsRunInOrderAsync(int numAgents)
    {
        var workflow = AgentWorkflowBuilder.BuildSequential(
            from i in Enumerable.Range(1, numAgents)
            select new DoubleEchoAgent($"agent{i}"));

        for (int iter = 0; iter < 3; iter++)
        {
            const string UserInput = "abc";
            (string updateText, List<ChatMessage>? result, _, _) = await RunWorkflowAsync(workflow, [new ChatMessage(ChatRole.User, UserInput)]);

            Assert.NotNull(result);
            Assert.Equal(numAgents + 1, result.Count);

            Assert.Equal(ChatRole.User, result[0].Role);
            Assert.Null(result[0].AuthorName);
            Assert.Equal(UserInput, result[0].Text);

            string[] texts = new string[numAgents + 1];
            texts[0] = UserInput;
            string expectedTotal = string.Empty;
            for (int i = 1; i < numAgents + 1; i++)
            {
                string id = $"agent{((i - 1) % numAgents) + 1}";
                texts[i] = $"{id}{Double(string.Concat(texts.Take(i)))}";
                Assert.Equal(ChatRole.Assistant, result[i].Role);
                Assert.Equal(id, result[i].AuthorName);
                Assert.Equal(texts[i], result[i].Text);
                expectedTotal += texts[i];
            }

            Assert.Equal(expectedTotal, updateText);
            Assert.Equal(UserInput + expectedTotal, string.Concat(result));

            static string Double(string s) => s + s;
        }
    }

    private class DoubleEchoAgent(string name) : AIAgent
    {
        public override string Name => name;

        protected override ValueTask<AgentSession> CreateSessionCoreAsync(CancellationToken cancellationToken = default)
            => new(new DoubleEchoAgentSession());

        protected override ValueTask<AgentSession> DeserializeSessionCoreAsync(JsonElement serializedState, JsonSerializerOptions? jsonSerializerOptions = null, CancellationToken cancellationToken = default)
            => new(new DoubleEchoAgentSession());

        protected override ValueTask<JsonElement> SerializeSessionCoreAsync(AgentSession session, JsonSerializerOptions? jsonSerializerOptions = null, CancellationToken cancellationToken = default)
            => default;

        protected override Task<AgentResponse> RunCoreAsync(
            IEnumerable<ChatMessage> messages, AgentSession? session = null, AgentRunOptions? options = null, CancellationToken cancellationToken = default) =>
            throw new NotImplementedException();

        protected override async IAsyncEnumerable<AgentResponseUpdate> RunCoreStreamingAsync(
            IEnumerable<ChatMessage> messages, AgentSession? session = null, AgentRunOptions? options = null, [EnumeratorCancellation] CancellationToken cancellationToken = default)
        {
            await Task.Yield();

            var contents = messages.SelectMany(m => m.Contents).ToList();
            string id = Guid.NewGuid().ToString("N");
            yield return new AgentResponseUpdate(ChatRole.Assistant, this.Name) { AuthorName = this.Name, MessageId = id };
            yield return new AgentResponseUpdate(ChatRole.Assistant, contents) { AuthorName = this.Name, MessageId = id };
            yield return new AgentResponseUpdate(ChatRole.Assistant, contents) { AuthorName = this.Name, MessageId = id };
        }
    }

    private sealed class DoubleEchoAgentSession() : AgentSession();

    [Fact]
    public async Task BuildConcurrent_AgentsRunInParallelAsync()
    {
        StrongBox<TaskCompletionSource<bool>> barrier = new();
        StrongBox<int> remaining = new();

        var workflow = AgentWorkflowBuilder.BuildConcurrent(
        [
            new DoubleEchoAgentWithBarrier("agent1", barrier, remaining),
            new DoubleEchoAgentWithBarrier("agent2", barrier, remaining),
        ]);

        for (int iter = 0; iter < 3; iter++)
        {
            barrier.Value = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
            remaining.Value = 2;

            (string updateText, List<ChatMessage>? result, _, _) = await RunWorkflowAsync(workflow, [new ChatMessage(ChatRole.User, "abc")]);
            Assert.NotEmpty(updateText);
            Assert.NotNull(result);

            // TODO: https://github.com/microsoft/agent-framework/issues/784
            // These asserts are flaky until we guarantee message delivery order.
            Assert.Single(Regex.Matches(updateText, "agent1"));
            Assert.Single(Regex.Matches(updateText, "agent2"));
            Assert.Equal(4, Regex.Matches(updateText, "abc").Count);
            Assert.Equal(2, result.Count);
        }
    }

    [Theory]
    [InlineData(1)]
    [InlineData(2)]
    [InlineData(3)]
    [InlineData(4)]
    [InlineData(5)]
    public async Task BuildGroupChat_AgentsRunInOrderAsync(int maxIterations)
    {
        const int NumAgents = 3;
        var workflow = AgentWorkflowBuilder.CreateGroupChatBuilderWith(agents => new RoundRobinGroupChatManager(agents) { MaximumIterationCount = maxIterations })
            .AddParticipants(new DoubleEchoAgent("agent1"), new DoubleEchoAgent("agent2"))
            .AddParticipants(new DoubleEchoAgent("agent3"))
            .Build();

        for (int iter = 0; iter < 3; iter++)
        {
            const string UserInput = "abc";
            (string updateText, List<ChatMessage>? result, _, _) = await RunWorkflowAsync(workflow, [new ChatMessage(ChatRole.User, UserInput)]);

            Assert.NotNull(result);
            Assert.Equal(maxIterations + 1, result.Count);

            Assert.Equal(ChatRole.User, result[0].Role);
            Assert.Null(result[0].AuthorName);
            Assert.Equal(UserInput, result[0].Text);

            string[] texts = new string[maxIterations + 1];
            texts[0] = UserInput;
            string expectedTotal = string.Empty;
            for (int i = 1; i < maxIterations + 1; i++)
            {
                string id = $"agent{((i - 1) % NumAgents) + 1}";
                texts[i] = $"{id}{Double(string.Concat(texts.Take(i)))}";
                Assert.Equal(ChatRole.Assistant, result[i].Role);
                Assert.Equal(id, result[i].AuthorName);
                Assert.Equal(texts[i], result[i].Text);
                expectedTotal += texts[i];
            }

            Assert.Equal(expectedTotal, updateText);
            Assert.Equal(UserInput + expectedTotal, string.Concat(result));

            static string Double(string s) => s + s;
        }
    }

    private sealed record WorkflowRunResult(string UpdateText, List<ChatMessage>? Result, CheckpointInfo? LastCheckpoint, List<RequestInfoEvent> PendingRequests);

    private static async Task<WorkflowRunResult> RunWorkflowCheckpointedAsync(
        Workflow workflow, List<ChatMessage> input, InProcessExecutionEnvironment environment, CheckpointInfo? fromCheckpoint = null)
    {
        await using StreamingRun run =
            fromCheckpoint != null ? await environment.ResumeStreamingAsync(workflow, fromCheckpoint)
                                   : await environment.OpenStreamingAsync(workflow);

        await run.TrySendMessageAsync(input);
        await run.TrySendMessageAsync(new TurnToken(emitEvents: true));

        return await ProcessWorkflowRunAsync(run);
    }

    private static async Task<WorkflowRunResult> ProcessWorkflowRunAsync(StreamingRun run)
    {
        StringBuilder sb = new();
        WorkflowOutputEvent? output = null;
        CheckpointInfo? lastCheckpoint = null;

        List<RequestInfoEvent> pendingRequests = [];

        await foreach (WorkflowEvent evt in run.WatchStreamAsync(blockOnPendingRequest: false).ConfigureAwait(false))
        {
            switch (evt)
            {
                case AgentResponseUpdateEvent responseUpdate:
                    sb.Append(responseUpdate.Data);
                    break;

                case RequestInfoEvent requestInfo:
                    pendingRequests.Add(requestInfo);
                    break;

                case WorkflowOutputEvent e:
                    output = e;
                    break;

                case WorkflowErrorEvent errorEvent:
                    Assert.Fail($"Workflow execution failed with error: {errorEvent.Exception}");
                    break;

                case SuperStepCompletedEvent stepCompleted:
                    lastCheckpoint = stepCompleted.CompletionInfo?.Checkpoint;
                    break;
            }
        }

        return new(sb.ToString(), output?.As<List<ChatMessage>>(), lastCheckpoint, pendingRequests);
    }

    private static Task<WorkflowRunResult> RunWorkflowAsync(
        Workflow workflow, List<ChatMessage> input, ExecutionEnvironment executionEnvironment = ExecutionEnvironment.InProcess_Lockstep)
        => RunWorkflowCheckpointedAsync(workflow, input, executionEnvironment.ToWorkflowExecutionEnvironment());

    private sealed class DoubleEchoAgentWithBarrier(string name, StrongBox<TaskCompletionSource<bool>> barrier, StrongBox<int> remaining) : DoubleEchoAgent(name)
    {
        protected override async IAsyncEnumerable<AgentResponseUpdate> RunCoreStreamingAsync(
            IEnumerable<ChatMessage> messages, AgentSession? session = null, AgentRunOptions? options = null, [EnumeratorCancellation] CancellationToken cancellationToken = default)
        {
            if (Interlocked.Decrement(ref remaining.Value) == 0)
            {
                barrier.Value!.SetResult(true);
            }

            await barrier.Value!.Task.ConfigureAwait(false);

            await foreach (var update in base.RunCoreStreamingAsync(messages, session, options, cancellationToken))
            {
                await Task.Yield();
                yield return update;
            }
        }
    }
}
