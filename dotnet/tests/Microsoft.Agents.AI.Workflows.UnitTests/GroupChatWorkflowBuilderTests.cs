// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Runtime.CompilerServices;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using FluentAssertions;
using Microsoft.Agents.AI.Workflows.InProc;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Workflows.UnitTests;

public class GroupChatWorkflowBuilderTests
{
    [Fact]
    public void BuildGroupChat_InvalidArguments_Throws()
    {
        Assert.Throws<ArgumentNullException>("managerFactory", () => AgentWorkflowBuilder.CreateGroupChatBuilderWith(null!));

        var groupChat = AgentWorkflowBuilder.CreateGroupChatBuilderWith(_ => new RoundRobinGroupChatManager([new OrchestrationTestHelpers.DoubleEchoAgent("a1")]));
        Assert.NotNull(groupChat);
        Assert.Throws<ArgumentNullException>("agents", () => groupChat.AddParticipants(null!));
        Assert.Throws<ArgumentNullException>("agents", () => groupChat.AddParticipants([null!]));
        Assert.Throws<ArgumentNullException>("agents", () => groupChat.AddParticipants(new OrchestrationTestHelpers.DoubleEchoAgent("a1"), null!));

        Assert.Throws<ArgumentNullException>("agents", () => new RoundRobinGroupChatManager(null!));
    }

    [Fact]
    public void GroupChatManager_MaximumIterationCount_Invalid_Throws()
    {
        var manager = new RoundRobinGroupChatManager([new OrchestrationTestHelpers.DoubleEchoAgent("a1")]);

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
            .AddParticipants(new OrchestrationTestHelpers.DoubleEchoAgent("agent1"), new OrchestrationTestHelpers.DoubleEchoAgent("agent2"))
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
            .AddParticipants(new OrchestrationTestHelpers.DoubleEchoAgent("agent1"))
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
            .AddParticipants(new OrchestrationTestHelpers.DoubleEchoAgent("agent1"))
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
    public async Task BuildGroupChat_AgentsRunInOrderAsync(int maxIterations)
    {
        const int NumAgents = 3;
        var workflow = AgentWorkflowBuilder.CreateGroupChatBuilderWith(agents => new RoundRobinGroupChatManager(agents) { MaximumIterationCount = maxIterations })
            .AddParticipants(new OrchestrationTestHelpers.DoubleEchoAgent("agent1"), new OrchestrationTestHelpers.DoubleEchoAgent("agent2"))
            .AddParticipants(new OrchestrationTestHelpers.DoubleEchoAgent("agent3"))
            .Build();

        for (int iter = 0; iter < 3; iter++)
        {
            const string UserInput = "abc";
            (string updateText, List<ChatMessage>? result, _, _) = await OrchestrationTestHelpers.RunWorkflowAsync(workflow, [new ChatMessage(ChatRole.User, UserInput)]);

            Assert.NotNull(result);
            Assert.Equal(maxIterations + 1, result.Count);

            Assert.Equal(ChatRole.User, result[0].Role);
            Assert.Null(result[0].AuthorName);
            Assert.Equal(UserInput, result[0].Text);

            // The group-chat host broadcasts each new message (initial user input + each speaker's
            // response) to every participant except the speaker that produced it. The selected
            // speaker therefore sees only what's been broadcast to it since its previous turn.
            string[] agentIds = ["agent1", "agent2", "agent3"];
            List<string>[] buffers = new List<string>[NumAgents];
            for (int a = 0; a < NumAgents; a++)
            {
                buffers[a] = [UserInput];
            }

            string[] texts = new string[maxIterations + 1];
            texts[0] = UserInput;
            string expectedTotal = string.Empty;
            for (int i = 1; i < maxIterations + 1; i++)
            {
                int speakerIdx = (i - 1) % NumAgents;
                string id = agentIds[speakerIdx];
                string concatReceived = string.Concat(buffers[speakerIdx]);
                texts[i] = $"{id}{Double(concatReceived)}";
                buffers[speakerIdx].Clear();
                for (int a = 0; a < NumAgents; a++)
                {
                    if (a == speakerIdx)
                    {
                        continue;
                    }

                    buffers[a].Add(texts[i]);
                }

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

    [Fact]
    public void Test_GroupChatWorkflowBuilder_DefaultDesignationsMatchSpec()
    {
        OrchestrationTestHelpers.DoubleEchoAgent a1 = new("agent1");
        OrchestrationTestHelpers.DoubleEchoAgent a2 = new("agent2");
        OrchestrationTestHelpers.DoubleEchoAgent a3 = new("agent3");

        Workflow workflow = AgentWorkflowBuilder
            .CreateGroupChatBuilderWith(agents => new RoundRobinGroupChatManager(agents) { MaximumIterationCount = 1 })
            .AddParticipants(a1, a2, a3)
            .Build();

        Dictionary<string, HashSet<OutputTag>> designations = workflow.OutputExecutors;

        designations.Where(kvp => kvp.Value.Count == 0)
            .Should().ContainSingle("group-chat host is the sole terminal output executor by default");
        designations.Where(kvp => kvp.Value.Contains(OutputTag.Intermediate))
            .Should().HaveCount(3, "every participant is designated intermediate by default");
    }

    [Fact]
    public void Test_GroupChatWorkflowBuilder_ExplicitDesignationsReplaceDefaults()
    {
        OrchestrationTestHelpers.DoubleEchoAgent a1 = new("agent1");
        OrchestrationTestHelpers.DoubleEchoAgent a2 = new("agent2");
        OrchestrationTestHelpers.DoubleEchoAgent a3 = new("agent3");

        Workflow workflow = AgentWorkflowBuilder
            .CreateGroupChatBuilderWith(agents => new RoundRobinGroupChatManager(agents) { MaximumIterationCount = 1 })
            .AddParticipants(a1, a2, a3)
            .WithOutputFrom(a1)
            .WithIntermediateOutputFrom([a2])
            .Build();

        Dictionary<string, HashSet<OutputTag>> designations = workflow.OutputExecutors;

        designations.Should().HaveCount(2,
            "only the two explicitly-designated agents land on the inner builder; the host default is suppressed");
        designations.Values.Where(tags => tags.Count == 0)
            .Should().ContainSingle("agent1 is the only terminal designation");
        designations.Values.Where(tags => tags.Contains(OutputTag.Intermediate))
            .Should().ContainSingle("agent2 is the only intermediate designation");
    }

    [Fact]
    public void Test_GroupChatWorkflowBuilder_DesignationForNonParticipantThrows()
    {
        OrchestrationTestHelpers.DoubleEchoAgent participant = new("p1");
        OrchestrationTestHelpers.DoubleEchoAgent stranger = new("stranger");

        GroupChatWorkflowBuilder builder = AgentWorkflowBuilder
            .CreateGroupChatBuilderWith(agents => new RoundRobinGroupChatManager(agents) { MaximumIterationCount = 1 })
            .AddParticipants(participant)
            .WithOutputFrom(stranger);

        Action build = () => builder.Build();
        build.Should().Throw<InvalidOperationException>().WithMessage("*stranger*");
    }

    private sealed class RecordingAgent(string name) : AIAgent
    {
        public List<List<string>> Invocations { get; } = [];

        public override string Name => name;

        protected override ValueTask<AgentSession> CreateSessionCoreAsync(CancellationToken cancellationToken = default)
            => new(new RecordingAgentSession());

        protected override ValueTask<AgentSession> DeserializeSessionCoreAsync(JsonElement serializedState, JsonSerializerOptions? jsonSerializerOptions = null, CancellationToken cancellationToken = default)
            => new(new RecordingAgentSession());

        protected override ValueTask<JsonElement> SerializeSessionCoreAsync(AgentSession session, JsonSerializerOptions? jsonSerializerOptions = null, CancellationToken cancellationToken = default)
            => default;

        protected override Task<AgentResponse> RunCoreAsync(
            IEnumerable<ChatMessage> messages, AgentSession? session = null, AgentRunOptions? options = null, CancellationToken cancellationToken = default) =>
            throw new NotImplementedException();

        protected override async IAsyncEnumerable<AgentResponseUpdate> RunCoreStreamingAsync(
            IEnumerable<ChatMessage> messages, AgentSession? session = null, AgentRunOptions? options = null, [EnumeratorCancellation] CancellationToken cancellationToken = default)
        {
            await Task.Yield();

            this.Invocations.Add(messages.Select(m => m.Text).ToList());

            string id = Guid.NewGuid().ToString("N");
            yield return new AgentResponseUpdate(ChatRole.Assistant, name) { AuthorName = name, MessageId = id };
        }
    }

    private sealed class RecordingAgentSession() : AgentSession();

    [Fact]
    public async Task BuildGroupChat_BroadcastsDeltaAndTargetsTurnTokenToSpeakerOnlyAsync()
    {
        var agentA = new RecordingAgent("agentA");
        var agentB = new RecordingAgent("agentB");
        var agentC = new RecordingAgent("agentC");

        var workflow = AgentWorkflowBuilder
            .CreateGroupChatBuilderWith(agents => new RoundRobinGroupChatManager(agents) { MaximumIterationCount = 4 })
            .AddParticipants(agentA, agentB, agentC)
            .Build();

        const string UserInput = "hello";
        (_, List<ChatMessage>? result, _, _) = await OrchestrationTestHelpers.RunWorkflowAsync(workflow, [new ChatMessage(ChatRole.User, UserInput)]);

        Assert.NotNull(result);
        Assert.Equal(5, result.Count); // initial user input + 4 agent turns
        Assert.Collection(
            result,
            m => Assert.Equal(UserInput, m.Text),
            m => Assert.Equal("agentA", m.Text),
            m => Assert.Equal("agentB", m.Text),
            m => Assert.Equal("agentC", m.Text),
            m => Assert.Equal("agentA", m.Text));

        // Each agent's TurnToken fires exactly when it is the selected speaker — invocation counts
        // confirm only the chosen participant receives a TurnToken on each round.
        Assert.Equal(2, agentA.Invocations.Count);
        Assert.Single(agentB.Invocations);
        Assert.Single(agentC.Invocations);

        // Turn 1: agentA is the first speaker. Initial broadcast went to every participant, so
        // agentA's only buffered message is the user input.
        Assert.Equal([UserInput], agentA.Invocations[0]);

        // Turn 2: agentB. It received the initial broadcast (user input) plus turn-1 broadcast of
        // agentA's response (agentA itself is excluded as the last speaker).
        Assert.Equal([UserInput, "agentA"], agentB.Invocations[0]);

        // Turn 3: agentC. It also received every broadcast so far (it has never been excluded).
        Assert.Equal([UserInput, "agentA", "agentB"], agentC.Invocations[0]);

        // Turn 4: agentA again. It was excluded on turn 2's broadcast (its own response), but
        // received turn-3 (agentB's response) and turn-4 (agentC's response) deltas.
        Assert.Equal(["agentB", "agentC"], agentA.Invocations[1]);
    }

    [Fact]
    public async Task BuildGroupChat_UpdateHistoryAsync_FiltersBroadcastPayloadAsync()
    {
        var agentA = new RecordingAgent("agentA");
        var agentB = new RecordingAgent("agentB");

        var workflow = AgentWorkflowBuilder
            .CreateGroupChatBuilderWith(agents => new PrefixingGroupChatManager(agents, "[broadcast] ") { MaximumIterationCount = 2 })
            .AddParticipants(agentA, agentB)
            .Build();

        const string UserInput = "hello";
        await OrchestrationTestHelpers.RunWorkflowAsync(workflow, [new ChatMessage(ChatRole.User, UserInput)]);

        // Turn 1: agentA's buffer contains only the initial broadcast, which UpdateHistoryAsync
        // prefixed.
        Assert.Equal(["[broadcast] hello"], agentA.Invocations[0]);

        // Turn 2: agentB received both the initial broadcast and agentA's response — both passed
        // through UpdateHistoryAsync before being broadcast.
        Assert.Equal(["[broadcast] hello", "[broadcast] agentA"], agentB.Invocations[0]);
    }

    [Fact]
    public async Task BuildGroupChat_CheckpointResumeMidConversation_PreservesIterationCursorAndBroadcastExclusionAsync()
    {
        const string UserInput = "hello";
        const int MaxIterations = 6;

        // --- Baseline: run the full conversation under checkpointing and capture every checkpoint
        //     plus the final transcript. The same workflow + agents are reused for the resume,
        //     because the runner enforces workflow-shape compatibility on ResumeStreamingAsync. ---
        BaselineRunResult baseline = await RunGroupChatBaselineAsync(UserInput, MaxIterations);

        // We need at least one mid-conversation checkpoint to resume from. The baseline produces a
        // checkpoint per superstep, which for MaxIterations=6 yields many; we pick a checkpoint
        // captured roughly midway so the resumed run still has work to do.
        Assert.True(baseline.Checkpoints.Count >= 5,
            $"expected at least 5 checkpoints in the baseline, got {baseline.Checkpoints.Count}");

        int midIndex = baseline.Checkpoints.Count / 2;
        CheckpointInfo midCheckpoint = baseline.Checkpoints[midIndex];

        // Snapshot per-agent invocation counts before the resume so we can isolate the invocations
        // produced after the checkpoint is restored.
        int aPreCount = baseline.AgentA.Invocations.Count;
        int bPreCount = baseline.AgentB.Invocations.Count;
        int cPreCount = baseline.AgentC.Invocations.Count;

        // --- Resume the same workflow from the mid-conversation checkpoint. ---
        List<ChatMessage>? resumedResult = null;
        await using (StreamingRun resumed = await baseline.Environment
                                                          .ResumeStreamingAsync(baseline.Workflow, midCheckpoint))
        {
            await foreach (WorkflowEvent evt in resumed.WatchStreamAsync(blockOnPendingRequest: false))
            {
                if (evt is WorkflowOutputEvent o)
                {
                    resumedResult = o.As<List<ChatMessage>>();
                }
                else if (evt is WorkflowErrorEvent err)
                {
                    Assert.Fail($"Resumed workflow failed: {err.Exception}");
                }
            }
        }

        // (1) Iteration-count continuity: the resumed run terminates with exactly the same number
        //     of turns the baseline produced — proves IterationCount was rehydrated and the manager
        //     honored MaximumIterationCount across the boundary.
        Assert.NotNull(resumedResult);
        Assert.Equal(baseline.Result.Count, resumedResult!.Count);

        // (2) Next-speaker consistency: the full transcript (initial input + every speaker's turn,
        //     in order) matches the baseline — proves the round-robin cursor was restored.
        List<string?> baselineTranscript = [.. baseline.Result.Select(m => m.Text)];
        List<string?> resumedTranscript = [.. resumedResult.Select(m => m.Text)];
        Assert.Equal(baselineTranscript, resumedTranscript);

        // (3) Broadcast exclusion holds across resume: a RecordingAgent's response text is just its
        //     own Name. Examine only the invocations recorded after the resume. If the host failed
        //     to exclude the current speaker from its post-resume broadcasts, an agent's next
        //     invocation buffer would contain its own previously produced response. Asserting that
        //     no post-resume invocation input contains the invoking agent's own name proves the
        //     exclusion was preserved through checkpoint+restore.
        AssertPostResumeBroadcastExclusion(baseline.AgentA, aPreCount);
        AssertPostResumeBroadcastExclusion(baseline.AgentB, bPreCount);
        AssertPostResumeBroadcastExclusion(baseline.AgentC, cPreCount);

        // Sanity: at least one agent was actually invoked after the resume; otherwise the test
        // would trivially pass even if the host stopped scheduling turns after restore.
        int totalPost = baseline.AgentA.Invocations.Count - aPreCount
                      + (baseline.AgentB.Invocations.Count - bPreCount)
                      + (baseline.AgentC.Invocations.Count - cPreCount);
        Assert.True(totalPost > 0, "at least one agent should be invoked after resuming from the mid-conversation checkpoint");

        static void AssertPostResumeBroadcastExclusion(RecordingAgent agent, int preCount)
        {
            for (int i = preCount; i < agent.Invocations.Count; i++)
            {
                Assert.DoesNotContain(agent.Name, agent.Invocations[i]);
            }
        }
    }

    private sealed record BaselineRunResult(
        Workflow Workflow,
        InProcessExecutionEnvironment Environment,
        RecordingAgent AgentA,
        RecordingAgent AgentB,
        RecordingAgent AgentC,
        List<ChatMessage> Result,
        List<CheckpointInfo> Checkpoints,
        CheckpointManager CheckpointManager);

    private static async Task<BaselineRunResult> RunGroupChatBaselineAsync(string userInput, int maxIterations)
    {
        var agentA = new RecordingAgent("agentA");
        var agentB = new RecordingAgent("agentB");
        var agentC = new RecordingAgent("agentC");

        Workflow workflow = AgentWorkflowBuilder
            .CreateGroupChatBuilderWith(agents => new RoundRobinGroupChatManager(agents) { MaximumIterationCount = maxIterations })
            .AddParticipants(agentA, agentB, agentC)
            .Build();

        CheckpointManager checkpointMgr = CheckpointManager.CreateInMemory();
        InProcessExecutionEnvironment env = ExecutionEnvironment.InProcess_Lockstep
                                                                .ToWorkflowExecutionEnvironment()
                                                                .WithCheckpointing(checkpointMgr);

        List<CheckpointInfo> checkpoints = [];
        List<ChatMessage>? finalResult = null;

        await using (StreamingRun run = await env.OpenStreamingAsync(workflow))
        {
            await run.TrySendMessageAsync(new List<ChatMessage> { new(ChatRole.User, userInput) });
            await run.TrySendMessageAsync(new TurnToken(emitEvents: true));

            await foreach (WorkflowEvent evt in run.WatchStreamAsync(blockOnPendingRequest: false))
            {
                switch (evt)
                {
                    case SuperStepCompletedEvent step when step.CompletionInfo?.Checkpoint is { } cp:
                        checkpoints.Add(cp);
                        break;
                    case WorkflowOutputEvent o:
                        finalResult = o.As<List<ChatMessage>>();
                        break;
                    case WorkflowErrorEvent err:
                        Assert.Fail($"Baseline workflow failed: {err.Exception}");
                        break;
                }
            }
        }

        Assert.NotNull(finalResult);
        return new BaselineRunResult(workflow, env, agentA, agentB, agentC, finalResult!, checkpoints, checkpointMgr);
    }

    private sealed class PrefixingGroupChatManager(IReadOnlyList<AIAgent> agents, string prefix) : RoundRobinGroupChatManager(agents)
    {
        protected internal override ValueTask<IEnumerable<ChatMessage>> UpdateHistoryAsync(
            IReadOnlyList<ChatMessage> history,
            CancellationToken cancellationToken = default)
        {
            IEnumerable<ChatMessage> prefixed =
                history.Select(m => new ChatMessage(m.Role, $"{prefix}{m.Text}") { AuthorName = m.AuthorName });

            return new(prefixed);
        }
    }
}
