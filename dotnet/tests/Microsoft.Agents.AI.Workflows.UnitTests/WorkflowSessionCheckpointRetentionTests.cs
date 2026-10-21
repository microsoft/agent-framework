// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Runtime.CompilerServices;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.Checkpointing;
using Microsoft.Agents.AI.Workflows.InProc;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Workflows.UnitTests;

/// <summary>
/// Verifies which checkpoints a workflow agent session keeps across turns, for a handoff workflow hosted as a
/// sub-workflow.
/// </summary>
public class WorkflowSessionCheckpointRetentionTests
{
    private const string SpecialistReply = "SPECIALIST_REPLY";
    private const int TurnCount = 5;

    [Theory]
    [InlineData(ExecutionEnvironment.InProcess_OffThread)]
    [InlineData(ExecutionEnvironment.InProcess_Lockstep)]
    internal async Task SessionOwnedCheckpoints_StayBoundedAcrossTurnsAsync(ExecutionEnvironment environment)
    {
        // Arrange
        AIAgent agent = BuildNestedHandoffAgent(environment.ToWorkflowExecutionEnvironment());
        AgentSession session = await agent.CreateSessionAsync();
        List<CheckpointCounts> counts = [];
        List<int> sizes = [];

        // Act
        for (int turn = 1; turn <= TurnCount; turn++)
        {
            AgentResponse response = await agent.RunAsync($"Question {turn}", session);
            Assert.Equal($"{SpecialistReply}:turn:{turn}", response.Text);

            JsonElement serialized = await agent.SerializeSessionAsync(session);
            sizes.Add(serialized.GetRawText().Length);
            counts.Add(CountCheckpoints(serialized));
        }

        // Assert: the session keeps the resume point and the latest turn, and every copy of the sub-workflow's
        // checkpoint manager keeps only its latest checkpoint, so each turn adds about the same amount.
        Assert.Equal(counts[^2].Session, counts[^1].Session);
        Assert.All(counts, turnCounts => Assert.All(turnCounts.SubWorkflow, subWorkflowCount => Assert.Equal(1, subWorkflowCount)));
        Assert.InRange(sizes[^1] - sizes[^2], 0, (sizes[^2] - sizes[^3]) * 1.1);
    }

    [Theory]
    [InlineData(ExecutionEnvironment.InProcess_OffThread)]
    [InlineData(ExecutionEnvironment.InProcess_Lockstep)]
    internal async Task SessionOwnedCheckpoints_ResumeEachTurnFromSerializedSessionAsync(ExecutionEnvironment environment)
    {
        // Arrange
        AIAgent agent = BuildNestedHandoffAgent(environment.ToWorkflowExecutionEnvironment());
        AgentSession session = await agent.CreateSessionAsync();
        List<CheckpointCounts> counts = [];

        for (int turn = 1; turn <= TurnCount; turn++)
        {
            // Act: run the turn, then continue from the serialized session on a freshly built agent.
            AgentResponse response = await agent.RunAsync($"Question {turn}", session);
            JsonElement serialized = await agent.SerializeSessionAsync(session);
            counts.Add(CountCheckpoints(serialized));

            agent = BuildNestedHandoffAgent(environment.ToWorkflowExecutionEnvironment());
            session = await agent.DeserializeSessionAsync(serialized);

            // Assert: the specialist sees every earlier user turn, so the pruned session restored the sub-workflow.
            Assert.Equal($"{SpecialistReply}:turn:{turn}", response.Text);
        }

        Assert.Equal(counts[^2].Session, counts[^1].Session);
        Assert.All(counts, turnCounts => Assert.All(turnCounts.SubWorkflow, subWorkflowCount => Assert.Equal(1, subWorkflowCount)));
    }

    [Theory]
    [InlineData(ExecutionEnvironment.InProcess_OffThread)]
    [InlineData(ExecutionEnvironment.InProcess_Lockstep)]
    internal async Task SessionOwnedCheckpoints_RecoverFromCheckpointOfLatestTurnAsync(ExecutionEnvironment environment)
    {
        // Arrange
        AIAgent agent = BuildHandoffWorkflow().AsAIAgent(executionEnvironment: environment.ToWorkflowExecutionEnvironment());
        AgentSession session = await agent.CreateSessionAsync();

        await RunTurnAsync(agent, session, "Question 1");
        (_, List<CheckpointInfo> secondTurnCheckpoints) = await RunTurnAsync(agent, session, "Question 2");
        JsonElement serialized = await agent.SerializeSessionAsync(session);

        AIAgent recoveringAgent = BuildHandoffWorkflow().AsAIAgent(executionEnvironment: environment.ToWorkflowExecutionEnvironment());
        AgentSession recoveringSession = await recoveringAgent.DeserializeSessionAsync(serialized);
        WorkflowSessionCheckpointRecovery recovery = recoveringSession.GetService<WorkflowSessionCheckpointRecovery>()
            ?? throw new InvalidOperationException("Workflow checkpoint recovery was not available.");

        // Act: continue the second turn from one of its intermediate checkpoints, then run another turn.
        Assert.True(recovery.TryPrepare(secondTurnCheckpoints[1].CheckpointId));
        (string recoveredReply, _) = await RunTurnAsync(recoveringAgent, recoveringSession, message: null);
        (string nextReply, _) = await RunTurnAsync(recoveringAgent, recoveringSession, "Question 3");

        // Assert
        Assert.Equal($"{SpecialistReply}:turn:2", recoveredReply);
        Assert.Equal($"{SpecialistReply}:turn:3", nextReply);
    }

    [Theory]
    [InlineData(ExecutionEnvironment.InProcess_OffThread)]
    [InlineData(ExecutionEnvironment.InProcess_Lockstep)]
    internal async Task CallerCheckpointManager_KeepsEveryCheckpointAsync(ExecutionEnvironment environment)
    {
        // Arrange
        CheckpointManager checkpointManager = CheckpointManager.CreateInMemory();
        AIAgent agent = BuildNestedHandoffAgent(environment.ToWorkflowExecutionEnvironment().WithCheckpointing(checkpointManager));
        AgentSession session = await agent.CreateSessionAsync();
        List<CheckpointInfo> committed = [];

        // Act
        for (int turn = 1; turn <= 3; turn++)
        {
            (string reply, List<CheckpointInfo> checkpoints) = await RunTurnAsync(agent, session, $"Question {turn}");
            Assert.Equal($"{SpecialistReply}:turn:{turn}", reply);
            committed.AddRange(checkpoints);
        }

        // Assert
        ICheckpointManager manager = checkpointManager;
        string sessionId = committed[0].SessionId;
        Assert.Equal(committed, await manager.RetrieveIndexAsync(sessionId));
        foreach (CheckpointInfo checkpoint in committed)
        {
            await manager.LookupCheckpointAsync(sessionId, checkpoint);
        }
    }

    [Theory]
    [InlineData(ExecutionEnvironment.InProcess_OffThread)]
    [InlineData(ExecutionEnvironment.InProcess_Lockstep)]
    internal async Task CallerJsonCheckpointStore_RestoresSubWorkflowFromEarlierTurnAsync(ExecutionEnvironment environment)
    {
        // Arrange
        InProcessExecutionEnvironment env = environment.ToWorkflowExecutionEnvironment()
                                                       .WithCheckpointing(CheckpointManager.CreateJson(new InMemoryJsonStore()));
        Workflow workflow = BuildNestedHandoffWorkflow();

        CheckpointInfo endOfFirstTurn;
        await using (StreamingRun run = await env.OpenStreamingAsync(workflow))
        {
            (string firstReply, endOfFirstTurn) = await RunWorkflowTurnAsync(run, "Question 1");
            (string secondReply, _) = await RunWorkflowTurnAsync(run, "Question 2");

            Assert.Equal($"{SpecialistReply}:turn:1", firstReply);
            Assert.Equal($"{SpecialistReply}:turn:2", secondReply);
        }

        // Act: go back to the end of the first turn and take a different second turn.
        await using StreamingRun restored = await env.ResumeStreamingAsync(workflow, endOfFirstTurn);
        (string replacementReply, _) = await RunWorkflowTurnAsync(restored, "Another question 2");

        // Assert: the sub-workflow resumed from the first turn, not from the latest one.
        Assert.Equal($"{SpecialistReply}:turn:2", replacementReply);
    }

    private sealed record CheckpointCounts(int Session, List<int> SubWorkflow);

    private static CheckpointCounts CountCheckpoints(JsonElement serializedSession)
    {
        WorkflowSession.SessionState state = new JsonMarshaller().Marshal<WorkflowSession.SessionState>(serializedSession);
        SessionCheckpointCache<Checkpoint> sessionStore = Assert.Single(Assert.IsType<InMemoryCheckpointManager>(state.CheckpointManager).Store.Values);

        List<int> subWorkflow = sessionStore.Cache.Values
            .SelectMany(checkpoint => checkpoint.StateData.Values)
            .Where(value => value.TypeId.IsMatch<InMemoryCheckpointManager>())
            .Select(value => Assert.IsType<InMemoryCheckpointManager>(value.As<InMemoryCheckpointManager>()))
            .Select(manager => manager.Store.Values.Sum(store => store.CheckpointIndex.Count))
            .ToList();

        Assert.NotEmpty(subWorkflow);
        return new(sessionStore.CheckpointIndex.Count, subWorkflow);
    }

    private static async Task<(string Reply, List<CheckpointInfo> Checkpoints)> RunTurnAsync(AIAgent agent, AgentSession session, string? message)
    {
        List<AgentResponseUpdate> updates = [];
        List<CheckpointInfo> checkpoints = [];

        IAsyncEnumerable<AgentResponseUpdate> stream = message is null
            ? agent.RunStreamingAsync(session)
            : agent.RunStreamingAsync(message, session);

        await foreach (AgentResponseUpdate update in stream)
        {
            updates.Add(update);
            if (update.RawRepresentation is SuperStepCompletedEvent { CompletionInfo.Checkpoint: { } checkpoint })
            {
                checkpoints.Add(checkpoint);
            }
        }

        return (updates.ToAgentResponse().Text, checkpoints);
    }

    private static async Task<(string Reply, CheckpointInfo LastCheckpoint)> RunWorkflowTurnAsync(StreamingRun run, string message)
    {
        await run.TrySendMessageAsync(new List<ChatMessage> { new(ChatRole.User, message) });
        await run.TrySendMessageAsync(new TurnToken(emitEvents: false));

        string? reply = null;
        CheckpointInfo? lastCheckpoint = null;
        await foreach (WorkflowEvent evt in run.WatchStreamAsync(blockOnPendingRequest: false))
        {
            switch (evt)
            {
                case WorkflowOutputEvent { Data: List<ChatMessage> conversation }:
                    reply = conversation[^1].Text;
                    break;
                case SuperStepCompletedEvent { CompletionInfo.Checkpoint: { } checkpoint }:
                    lastCheckpoint = checkpoint;
                    break;
            }
        }

        return (Assert.IsType<string>(reply), Assert.IsType<CheckpointInfo>(lastCheckpoint));
    }

    private static AIAgent BuildNestedHandoffAgent(IWorkflowExecutionEnvironment environment)
        => BuildNestedHandoffWorkflow().AsAIAgent(id: "outer-agent", name: "outer-agent", executionEnvironment: environment);

    private static Workflow BuildNestedHandoffWorkflow()
    {
        ExecutorBinding handoff = BuildHandoffWorkflow().BindAsExecutor("handoff");
        return new WorkflowBuilder(handoff).WithOutputFrom(handoff).Build();
    }

    private static Workflow BuildHandoffWorkflow()
    {
        AIAgent triage = new StatelessMockChatClient((_, options) =>
        {
            string handoffTool = options?.Tools?
                .FirstOrDefault(t => t.Name.StartsWith("handoff_to_", StringComparison.Ordinal))?.Name
                ?? throw new InvalidOperationException("Expected a handoff tool to be available to the triage agent.");

            return new ChatResponse(new ChatMessage(ChatRole.Assistant, [new FunctionCallContent(Guid.NewGuid().ToString("N"), handoffTool)]));
        }).AsAIAgent(new ChatClientAgentOptions
        {
            Id = "triage-agent",
            Name = "triage_agent",
            Description = "Routes the request to a specialist.",
            ChatOptions = new() { Instructions = "Always hand off to the specialist." },
        });

        // The reply counts the user turns the specialist sees, which only advances if a resume restored them.
        AIAgent specialist = new StatelessMockChatClient((messages, _) =>
        {
            int observedUserTurns = messages.Count(m => m.Role == ChatRole.User);
            return new ChatResponse(new ChatMessage(ChatRole.Assistant, $"{SpecialistReply}:turn:{observedUserTurns}"));
        }).AsAIAgent(new ChatClientAgentOptions
        {
            Id = "specialist-agent",
            Name = "specialist_agent",
            Description = "Handles the request once triage hands off.",
            ChatOptions = new() { Instructions = "Answer the request." },
        });

        return AgentWorkflowBuilder.CreateHandoffBuilderWith(triage)
            .WithHandoff(triage, specialist)
            .Build();
    }

    private sealed class StatelessMockChatClient(Func<IEnumerable<ChatMessage>, ChatOptions?, ChatResponse> responseFactory) : IChatClient
    {
        public Task<ChatResponse> GetResponseAsync(IEnumerable<ChatMessage> messages, ChatOptions? options = null, CancellationToken cancellationToken = default) =>
            Task.FromResult(responseFactory(messages, options));

        public async IAsyncEnumerable<ChatResponseUpdate> GetStreamingResponseAsync(
            IEnumerable<ChatMessage> messages, ChatOptions? options = null, [EnumeratorCancellation] CancellationToken cancellationToken = default)
        {
            foreach (ChatResponseUpdate update in (await this.GetResponseAsync(messages, options, cancellationToken).ConfigureAwait(false)).ToChatResponseUpdates())
            {
                yield return update;
            }
        }

        public object? GetService(Type serviceType, object? serviceKey = null) => null;

        public void Dispose() { }
    }
}
