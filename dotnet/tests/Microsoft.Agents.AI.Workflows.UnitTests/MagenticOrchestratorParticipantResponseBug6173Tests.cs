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
using Microsoft.Agents.AI.Workflows.Specialized.Magentic;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Workflows.UnitTests;

/// <summary>
/// Regression test for https://github.com/microsoft/agent-framework/issues/6173.
///
/// On subsequent turns of <see cref="MagenticOrchestrator.TakeTurnAsync"/> (i.e., when an
/// agent participant returns control to the orchestrator), the inbound <c>messages</c>
/// parameter — which carries the participant's response — must be appended to the
/// task context's chat history before the next coordination round is computed.
/// Otherwise, the manager's progress ledger never sees the participant's output and the
/// workflow loops until it exhausts <c>MaxRoundCount</c>.
/// </summary>
public class MagenticOrchestratorParticipantResponseBug6173Tests
{
    [Fact]
    public async Task ParticipantResponse_IsAppendedTo_ChatHistory_BetweenRoundsAsync()
    {
        // A marker that only appears in the worker's echo response, NOT in any orchestrator
        // instruction or manager prompt. Used to prove the participant response made it
        // back into the chat history between rounds.
        const string WorkerEchoMarker = "WORKER_ECHO_MARKER::";

        List<ChatMessage> factsResponse = CreatePlanResponse("Initial facts");
        List<ChatMessage> planResponse = CreatePlanResponse("Step 1: Delegate to worker");

        // Round 1 ledger: not satisfied, delegate to Worker.
        List<ChatMessage> round1Ledger = CreateProgressLedgerResponse(
            isRequestSatisfied: false,
            isInLoop: false,
            isProgressBeingMade: true,
            nextSpeaker: "Worker",
            instructionOrQuestion: "Please work on the task");

        // Round 2 ledger: satisfied — drives the workflow to the final answer.
        List<ChatMessage> round2Ledger = CreateProgressLedgerResponse(
            isRequestSatisfied: true,
            isInLoop: false,
            isProgressBeingMade: true,
            nextSpeaker: "Worker",
            instructionOrQuestion: "Done");

        List<ChatMessage> finalAnswerResponse = CreateFinalAnswerResponse("All done");

        RecordingReplayAgent manager = new(
            [factsResponse, planResponse, round1Ledger, round2Ledger, finalAnswerResponse],
            name: "Manager");

        TestEchoAgent worker = new(name: "Worker", prefix: WorkerEchoMarker);

        Workflow workflow = new MagenticWorkflowBuilder(manager)
            .AddParticipants(worker)
            .RequirePlanSignoff(false)
            .WithMaxRounds(2)
            .Build();

        InProcessExecutionEnvironment environment = ExecutionEnvironment.InProcess_Lockstep
            .ToWorkflowExecutionEnvironment()
            .WithCheckpointing(CheckpointManager.CreateInMemory());

        await using StreamingRun run = await environment.OpenStreamingAsync(workflow);

        await run.TrySendMessageAsync(new List<ChatMessage> { new(ChatRole.User, "Do the task") });
        await run.TrySendMessageAsync(new TurnToken(emitEvents: true));

        await foreach (WorkflowEvent _ in run.WatchStreamAsync(blockOnPendingRequest: false).ConfigureAwait(false))
        {
            // Drain to completion.
        }

        // The manager is invoked five times: facts, plan, round-1 ledger, round-2 ledger, final answer.
        // The round-2 progress-ledger call (index 3) is the one that proves the worker's response
        // made it into chat history between rounds.
        manager.Invocations.Should().HaveCountGreaterThanOrEqualTo(4,
            "the manager should have been invoked at least four times (facts, plan, ledger1, ledger2)");

        IReadOnlyList<ChatMessage> round2LedgerInputs = manager.Invocations[3];

        round2LedgerInputs.Should().Contain(
            m => m.Text != null && m.Text.Contains(WorkerEchoMarker, StringComparison.Ordinal),
            "the worker's response from round 1 must be included in the messages provided to the manager "
            + "when computing the round-2 progress ledger — otherwise the orchestrator cannot detect task completion "
            + "and the workflow will exhaust MaxRoundCount (see issue #6173).");
    }

    private static List<ChatMessage> CreatePlanResponse(string plan) =>
    [
        new ChatMessage(ChatRole.Assistant, plan)
        {
            MessageId = Guid.NewGuid().ToString("N"),
            CreatedAt = DateTimeOffset.UtcNow
        }
    ];

    private static List<ChatMessage> CreateProgressLedgerResponse(
        bool isRequestSatisfied,
        bool isInLoop,
        bool isProgressBeingMade,
        string nextSpeaker,
        string instructionOrQuestion)
    {
        string isRequestSatisfiedStr = isRequestSatisfied ? "true" : "false";
        string isInLoopStr = isInLoop ? "true" : "false";
        string isProgressBeingMadeStr = isProgressBeingMade ? "true" : "false";
        string nextSpeakerJson = JsonSerializer.Serialize(nextSpeaker);
        string instructionJson = JsonSerializer.Serialize(instructionOrQuestion);

        string ledgerJson = $$"""
        {
            "is_request_satisfied": { "answer": {{isRequestSatisfiedStr}}, "reason": "test reason" },
            "is_in_loop": { "answer": {{isInLoopStr}}, "reason": "test reason" },
            "is_progress_being_made": { "answer": {{isProgressBeingMadeStr}}, "reason": "test reason" },
            "next_speaker": { "answer": {{nextSpeakerJson}}, "reason": "test reason" },
            "instruction_or_question": { "answer": {{instructionJson}}, "reason": "test reason" }
        }
        """;

        return
        [
            new ChatMessage(ChatRole.Assistant, ledgerJson)
            {
                MessageId = Guid.NewGuid().ToString("N"),
                CreatedAt = DateTimeOffset.UtcNow
            }
        ];
    }

    private static List<ChatMessage> CreateFinalAnswerResponse(string answer) =>
    [
        new ChatMessage(ChatRole.Assistant, answer)
        {
            MessageId = Guid.NewGuid().ToString("N"),
            CreatedAt = DateTimeOffset.UtcNow
        }
    ];

    /// <summary>
    /// A scripted manager agent that records the messages it receives on each invocation,
    /// so tests can inspect what context was passed to the manager at each step.
    /// </summary>
    private sealed class RecordingReplayAgent(List<List<ChatMessage>> scriptedResponses, string? name = null) : AIAgent
    {
        public override string? Name => name;

        public List<IReadOnlyList<ChatMessage>> Invocations { get; } = [];

        private int _turn;

        protected override ValueTask<AgentSession> CreateSessionCoreAsync(CancellationToken cancellationToken = default)
            => new(new RecordingAgentSession());

        protected override ValueTask<AgentSession> DeserializeSessionCoreAsync(JsonElement serializedState, JsonSerializerOptions? jsonSerializerOptions = null, CancellationToken cancellationToken = default)
            => new(new RecordingAgentSession());

        protected override ValueTask<JsonElement> SerializeSessionCoreAsync(AgentSession session, JsonSerializerOptions? jsonSerializerOptions = null, CancellationToken cancellationToken = default)
            => default;

        protected override Task<AgentResponse> RunCoreAsync(IEnumerable<ChatMessage> messages, AgentSession? session = null, AgentRunOptions? options = null, CancellationToken cancellationToken = default)
            => this.RunStreamingAsync(messages, session, options, cancellationToken).ToAgentResponseAsync(cancellationToken);

        protected override async IAsyncEnumerable<AgentResponseUpdate> RunCoreStreamingAsync(IEnumerable<ChatMessage> messages, AgentSession? session = null, AgentRunOptions? options = null, [EnumeratorCancellation] CancellationToken cancellationToken = default)
        {
            this.Invocations.Add(messages.ToList());

            string responseId = Guid.NewGuid().ToString("N");

            if (this._turn < scriptedResponses.Count)
            {
                foreach (ChatMessage message in scriptedResponses[this._turn++])
                {
                    foreach (AIContent content in message.Contents)
                    {
                        yield return new AgentResponseUpdate
                        {
                            AgentId = this.Id,
                            AuthorName = this.Name,
                            MessageId = message.MessageId,
                            ResponseId = responseId,
                            Contents = [content],
                            Role = message.Role,
                        };
                    }
                }
            }

            await Task.CompletedTask.ConfigureAwait(false);
        }

        private sealed class RecordingAgentSession() : AgentSession();
    }
}
