// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using System.Threading.Tasks;
using FluentAssertions;
using Microsoft.Agents.AI.Workflows.InProc;
using Microsoft.Agents.AI.Workflows.Specialized.Magentic;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Workflows.UnitTests;

/// <summary>
/// End-to-end tests for the Magentic orchestrator workflow.
/// </summary>
public class MagenticOrchestrationTests
{
    [Fact]
    public async Task Task_Completes_When_RequestSatisfied()
    {
        // Arrange: Manager reports task satisfied on first coordination round
        // Each response must have unique message IDs, so create separate instances
        List<ChatMessage> factsResponse = CreatePlanResponse("Facts about the task");
        List<ChatMessage> planResponse = CreatePlanResponse("Step 1: Do the task");
        List<ChatMessage> progressLedgerResponse = CreateProgressLedgerResponse(
            isRequestSatisfied: true,
            isInLoop: false,
            isProgressBeingMade: true,
            nextSpeaker: "Worker",
            instructionOrQuestion: "Complete the task");
        List<ChatMessage> finalAnswerResponse = CreateFinalAnswerResponse("Task completed successfully!");

        TestReplayAgent manager = new(
            [factsResponse, planResponse, progressLedgerResponse, finalAnswerResponse],
            name: "Manager");
        TestEchoAgent worker = new(name: "Worker");

        Workflow workflow = new MagenticWorkflowBuilder(manager)
            .AddParticipants(worker)
            .RequirePlanSignoff(false)
            .Build();

        // Act
        WorkflowRunResult runResult = await RunMagenticWorkflowAsync(workflow, [new ChatMessage(ChatRole.User, "Do the task")]);

        // Assert: Check the result contains the final answer
        runResult.Result.Should().NotBeNull();
        runResult.Result.Should().ContainSingle();
        runResult.Result![0].Text.Should().Contain("Task completed successfully!");
        runResult.PendingRequests.Should().BeEmpty();
    }

    [Fact]
    public async Task PlanReview_Approved_Proceeds()
    {
        // Arrange: Human approves initial plan
        List<ChatMessage> factsResponse = CreatePlanResponse("Facts about executing the plan");
        List<ChatMessage> planResponse = CreatePlanResponse("Step 1: Execute the plan");
        List<ChatMessage> progressLedgerResponse = CreateProgressLedgerResponse(
            isRequestSatisfied: true,
            isInLoop: false,
            isProgressBeingMade: true,
            nextSpeaker: "Worker",
            instructionOrQuestion: "Execute");
        List<ChatMessage> finalAnswerResponse = CreateFinalAnswerResponse("Plan executed successfully");

        TestReplayAgent manager = new(
            [factsResponse, planResponse, progressLedgerResponse, finalAnswerResponse],
            name: "Manager");
        TestEchoAgent worker = new(name: "Worker");

        Workflow workflow = new MagenticWorkflowBuilder(manager)
            .AddParticipants(worker)
            .RequirePlanSignoff(true)
            .Build();

        CheckpointManager checkpointManager = CheckpointManager.CreateInMemory();

        // Act: First run - should pause for plan review
        WorkflowRunResult firstResult = await RunMagenticWorkflowAsync(
            workflow,
            [new ChatMessage(ChatRole.User, "Execute plan")],
            checkpointManager: checkpointManager);

        firstResult.PendingRequests.Should().ContainSingle();
        ExternalRequest request = firstResult.PendingRequests[0].Request;
        MagenticPlanReviewRequest? reviewRequest = request.Data.As<MagenticPlanReviewRequest>();
        reviewRequest.Should().NotBeNull();
        reviewRequest!.Plan.Text.Should().Contain("Execute the plan");

        // Act: Resume with approval
        MagenticPlanReviewResponse approval = reviewRequest.Approve();
        ExternalResponse response = request.CreateResponse(approval);
        WorkflowRunResult secondResult = await ResumeMagenticWorkflowAsync(
            workflow,
            response,
            checkpointManager,
            firstResult.LastCheckpoint);

        // Assert
        secondResult.Result.Should().NotBeNull();
        secondResult.Result![0].Text.Should().Contain("Plan executed successfully");
    }

    [Fact]
    public async Task Initial_Plan_Emits_PlanCreatedEvent()
    {
        // Arrange
        List<ChatMessage> factsResponse = CreatePlanResponse("Facts about the task");
        List<ChatMessage> planResponse = CreatePlanResponse("Step 1: Initial plan");
        List<ChatMessage> progressLedgerResponse = CreateProgressLedgerResponse(
            isRequestSatisfied: true,
            isInLoop: false,
            isProgressBeingMade: true,
            nextSpeaker: "Worker",
            instructionOrQuestion: "Execute");
        List<ChatMessage> finalAnswerResponse = CreateFinalAnswerResponse("Done");

        TestReplayAgent manager = new(
            [factsResponse, planResponse, progressLedgerResponse, finalAnswerResponse],
            name: "Manager");
        TestEchoAgent worker = new(name: "Worker");

        List<WorkflowEvent> collectedEvents = [];

        Workflow workflow = new MagenticWorkflowBuilder(manager)
            .AddParticipants(worker)
            .RequirePlanSignoff(false)
            .Build();

        // Act
        await RunMagenticWorkflowAsync(
            workflow,
            [new ChatMessage(ChatRole.User, "Do task")],
            eventCollector: collectedEvents);

        // Assert
        collectedEvents.OfType<MagenticPlanCreatedEvent>().Should().NotBeEmpty();
        MagenticPlanCreatedEvent planEvent = collectedEvents.OfType<MagenticPlanCreatedEvent>().First();
        planEvent.FullTaskLedger.Should().NotBeNull();
    }

    [Fact]
    public async Task NextSpeaker_Invalid_Triggers_FinalAnswer()
    {
        // Arrange: ProgressLedger returns invalid next_speaker
        List<ChatMessage> factsResponse = CreatePlanResponse("Facts about the task");
        List<ChatMessage> planResponse = CreatePlanResponse("Step 1: Execute");
        List<ChatMessage> invalidNextSpeakerLedger = CreateProgressLedgerResponse(
            isRequestSatisfied: false,
            isInLoop: false,
            isProgressBeingMade: true,
            nextSpeaker: "NonExistentAgent",  // Invalid - doesn't match any team member
            instructionOrQuestion: "Continue");
        List<ChatMessage> finalAnswer = CreateFinalAnswerResponse("Forced to conclude due to invalid speaker");

        TestReplayAgent manager = new(
            [factsResponse, planResponse, invalidNextSpeakerLedger, finalAnswer],
            name: "Manager");
        TestEchoAgent worker = new(name: "Worker");

        List<WorkflowEvent> collectedEvents = [];

        Workflow workflow = new MagenticWorkflowBuilder(manager)
            .AddParticipants(worker)
            .RequirePlanSignoff(false)
            .Build();

        // Act
        WorkflowRunResult runResult = await RunMagenticWorkflowAsync(
            workflow,
            [new ChatMessage(ChatRole.User, "Do task")],
            eventCollector: collectedEvents);

        // Assert: Warning should be emitted and final answer prepared
        collectedEvents.OfType<WorkflowWarningEvent>()
            .Should().Contain(e => e.Data != null && e.Data.ToString()!.Contains("Invalid next speaker"));
        runResult.Result.Should().NotBeNull();
        runResult.Result![0].Text.Should().Contain("Forced to conclude");
    }

    [Fact]
    public async Task ProgressLedger_Updated_Event_Emitted()
    {
        // Arrange
        List<ChatMessage> factsResponse = CreatePlanResponse("Facts about the task");
        List<ChatMessage> planResponse = CreatePlanResponse("Step 1: Execute");
        List<ChatMessage> progressLedgerResponse = CreateProgressLedgerResponse(
            isRequestSatisfied: true,
            isInLoop: false,
            isProgressBeingMade: true,
            nextSpeaker: "Worker",
            instructionOrQuestion: "Execute");
        List<ChatMessage> finalAnswerResponse = CreateFinalAnswerResponse("Done");

        TestReplayAgent manager = new(
            [factsResponse, planResponse, progressLedgerResponse, finalAnswerResponse],
            name: "Manager");
        TestEchoAgent worker = new(name: "Worker");

        List<WorkflowEvent> collectedEvents = [];

        Workflow workflow = new MagenticWorkflowBuilder(manager)
            .AddParticipants(worker)
            .RequirePlanSignoff(false)
            .Build();

        // Act
        await RunMagenticWorkflowAsync(
            workflow,
            [new ChatMessage(ChatRole.User, "Do task")],
            eventCollector: collectedEvents);

        // Assert
        collectedEvents.OfType<MagenticProgressLedgerUpdatedEvent>().Should().NotBeEmpty();
        MagenticProgressLedgerUpdatedEvent ledgerEvent = collectedEvents.OfType<MagenticProgressLedgerUpdatedEvent>().First();
        ledgerEvent.ProgressLedger.Should().NotBeNull();
        ledgerEvent.ProgressLedger.IsRequestSatisfied.Should().BeTrue();
    }

    [Fact]
    public async Task PlanSignoff_Disabled_Proceeds_Immediately()
    {
        // Arrange: requirePlanSignoff=false should mean no plan review request
        List<ChatMessage> factsResponse = CreatePlanResponse("Task facts");
        List<ChatMessage> planResponse = CreatePlanResponse("Step 1: Execute immediately");
        List<ChatMessage> progressLedgerResponse = CreateProgressLedgerResponse(
            isRequestSatisfied: true,
            isInLoop: false,
            isProgressBeingMade: true,
            nextSpeaker: "Worker",
            instructionOrQuestion: "Go");
        List<ChatMessage> finalAnswerResponse = CreateFinalAnswerResponse("Immediate completion");

        TestReplayAgent manager = new(
            [factsResponse, planResponse, progressLedgerResponse, finalAnswerResponse],
            name: "Manager");
        TestEchoAgent worker = new(name: "Worker");

        List<WorkflowEvent> collectedEvents = [];

        Workflow workflow = new MagenticWorkflowBuilder(manager)
            .AddParticipants(worker)
            .RequirePlanSignoff(false)
            .Build();

        // Act
        WorkflowRunResult runResult = await RunMagenticWorkflowAsync(
            workflow,
            [new ChatMessage(ChatRole.User, "Do it now")],
            eventCollector: collectedEvents);

        // Assert: No plan review request, workflow completes immediately
        runResult.PendingRequests.Should().BeEmpty("plan signoff is disabled, so no review should be requested");
        collectedEvents.OfType<RequestInfoEvent>().Should().BeEmpty();
        runResult.Result.Should().NotBeNull();
        runResult.Result![0].Text.Should().Contain("Immediate completion");
    }

    [Fact]
    public async Task NextSpeaker_Empty_Falls_Back_To_First()
    {
        // Arrange: First progress ledger returns empty next_speaker, which should fall back to first participant.
        // Round 1: empty speaker → fallback to Worker (first participant) → Worker echoes
        // Round 2 (after Worker responds, TakeTurnAsync re-enters): new plan + satisfied ledger → final answer
        List<ChatMessage> factsResponse1 = CreatePlanResponse("Facts about the task");
        List<ChatMessage> planResponse1 = CreatePlanResponse("Step 1: Execute");
        List<ChatMessage> emptyNextSpeakerLedger = CreateProgressLedgerResponse(
            isRequestSatisfied: false,
            isInLoop: false,
            isProgressBeingMade: true,
            nextSpeaker: "",  // Empty - should fall back to first participant
            instructionOrQuestion: "Please help with this task");

        // Round 2 responses (after Worker echoes back, orchestrator re-enters TakeTurnAsync → UpdatePlanAndDelegateAsync)
        List<ChatMessage> factsResponse2 = CreatePlanResponse("Updated facts");
        List<ChatMessage> planResponse2 = CreatePlanResponse("Updated plan");
        List<ChatMessage> satisfiedLedger = CreateProgressLedgerResponse(
            isRequestSatisfied: true,
            isInLoop: false,
            isProgressBeingMade: true,
            nextSpeaker: "Worker",
            instructionOrQuestion: "Done");
        List<ChatMessage> finalAnswerResponse = CreateFinalAnswerResponse("Task completed after fallback");

        TestReplayAgent manager = new(
            [factsResponse1, planResponse1, emptyNextSpeakerLedger,
             factsResponse2, planResponse2, satisfiedLedger, finalAnswerResponse],
            name: "Manager");
        TestEchoAgent worker = new(name: "Worker");

        List<WorkflowEvent> collectedEvents = [];

        Workflow workflow = new MagenticWorkflowBuilder(manager)
            .AddParticipants(worker)
            .RequirePlanSignoff(false)
            .Build();

        // Act
        WorkflowRunResult runResult = await RunMagenticWorkflowAsync(
            workflow,
            [new ChatMessage(ChatRole.User, "Do the task")],
            eventCollector: collectedEvents);

        // Assert: Warning about empty next speaker should be emitted
        collectedEvents.OfType<WorkflowWarningEvent>()
            .Should().Contain(e => e.Data != null && e.Data.ToString()!.Contains("empty"));
        runResult.Result.Should().NotBeNull();
        runResult.Result![0].Text.Should().Contain("Task completed after fallback");
    }

    [Fact]
    public async Task Task_Completes_After_Multiple_Rounds()
    {
        // Arrange: Round 1 delegates to Worker (not satisfied), round 2 completes
        // Manager turn sequence: facts1, plan1, ledger1(not satisfied), facts2, plan2, ledger2(satisfied), finalAnswer
        List<ChatMessage> factsResponse1 = CreatePlanResponse("Initial facts");
        List<ChatMessage> planResponse1 = CreatePlanResponse("Step 1: Delegate to worker");
        List<ChatMessage> round1Ledger = CreateProgressLedgerResponse(
            isRequestSatisfied: false,
            isInLoop: false,
            isProgressBeingMade: true,
            nextSpeaker: "Worker",
            instructionOrQuestion: "Please work on the task");

        List<ChatMessage> factsResponse2 = CreatePlanResponse("Updated facts after worker input");
        List<ChatMessage> planResponse2 = CreatePlanResponse("Updated plan after worker input");
        List<ChatMessage> round2Ledger = CreateProgressLedgerResponse(
            isRequestSatisfied: true,
            isInLoop: false,
            isProgressBeingMade: true,
            nextSpeaker: "Worker",
            instructionOrQuestion: "Task is done");
        List<ChatMessage> finalAnswerResponse = CreateFinalAnswerResponse("Multi-round task completed!");

        TestReplayAgent manager = new(
            [factsResponse1, planResponse1, round1Ledger,
             factsResponse2, planResponse2, round2Ledger, finalAnswerResponse],
            name: "Manager");
        TestEchoAgent worker = new(name: "Worker");

        List<WorkflowEvent> collectedEvents = [];

        Workflow workflow = new MagenticWorkflowBuilder(manager)
            .AddParticipants(worker)
            .RequirePlanSignoff(false)
            .Build();

        // Act
        WorkflowRunResult runResult = await RunMagenticWorkflowAsync(
            workflow,
            [new ChatMessage(ChatRole.User, "Complex multi-round task")],
            eventCollector: collectedEvents);

        // Assert: Two plan created/replanned events (one per TakeTurn), two progress ledger events, final answer
        collectedEvents.OfType<MagenticProgressLedgerUpdatedEvent>().Should().HaveCount(2);
        runResult.Result.Should().NotBeNull();
        runResult.Result![0].Text.Should().Contain("Multi-round task completed!");
    }

    [Fact]
    public async Task PlanReview_Revised_Triggers_Replan()
    {
        // Arrange: Human rejects initial plan with revision, triggering a replan.
        // Flow: facts1, plan1 → PlanCreatedEvent → plan review (pending)
        //       resume with revision → facts2, plan2 → MagenticReplannedEvent → plan review again (pending)
        //       resume with approval → progressLedger(satisfied) → finalAnswer
        List<ChatMessage> factsResponse1 = CreatePlanResponse("Initial facts");
        List<ChatMessage> planResponse1 = CreatePlanResponse("Initial plan - needs revision");
        List<ChatMessage> factsResponse2 = CreatePlanResponse("Revised facts");
        List<ChatMessage> planResponse2 = CreatePlanResponse("Revised plan - much better");
        List<ChatMessage> progressLedgerResponse = CreateProgressLedgerResponse(
            isRequestSatisfied: true,
            isInLoop: false,
            isProgressBeingMade: true,
            nextSpeaker: "Worker",
            instructionOrQuestion: "Execute revised plan");
        List<ChatMessage> finalAnswerResponse = CreateFinalAnswerResponse("Revised plan executed successfully");

        TestReplayAgent manager = new(
            [factsResponse1, planResponse1, factsResponse2, planResponse2, progressLedgerResponse, finalAnswerResponse],
            name: "Manager");
        TestEchoAgent worker = new(name: "Worker");

        Workflow workflow = new MagenticWorkflowBuilder(manager)
            .AddParticipants(worker)
            .RequirePlanSignoff(true)
            .Build();

        CheckpointManager checkpointManager = CheckpointManager.CreateInMemory();
        List<WorkflowEvent> allEvents = [];

        // Act 1: First run - should pause for plan review with initial plan
        WorkflowRunResult firstResult = await RunMagenticWorkflowAsync(
            workflow,
            [new ChatMessage(ChatRole.User, "Execute task")],
            checkpointManager: checkpointManager,
            eventCollector: allEvents);

        firstResult.PendingRequests.Should().ContainSingle();
        ExternalRequest request1 = firstResult.PendingRequests[0].Request;
        MagenticPlanReviewRequest? reviewRequest1 = request1.Data.As<MagenticPlanReviewRequest>();
        reviewRequest1.Should().NotBeNull();
        reviewRequest1!.Plan.Text.Should().Contain("Initial plan");

        // Act 2: Resume with revision (reject the plan)
        MagenticPlanReviewResponse revision = reviewRequest1.Revise("Please include more detail");
        ExternalResponse revisionResponse = request1.CreateResponse(revision);
        WorkflowRunResult secondResult = await ResumeMagenticWorkflowAsync(
            workflow,
            revisionResponse,
            checkpointManager,
            firstResult.LastCheckpoint,
            eventCollector: allEvents);

        // Should pause again for review of the revised plan (stream may include prior request too)
        secondResult.PendingRequests.Should().NotBeEmpty();
        ExternalRequest request2 = secondResult.PendingRequests[^1].Request;
        MagenticPlanReviewRequest? reviewRequest2 = request2.Data.As<MagenticPlanReviewRequest>();
        reviewRequest2.Should().NotBeNull();
        reviewRequest2!.Plan.Text.Should().Contain("Revised plan");

        // Act 3: Resume with approval
        MagenticPlanReviewResponse approval = reviewRequest2.Approve();
        ExternalResponse approvalResponse = request2.CreateResponse(approval);
        WorkflowRunResult thirdResult = await ResumeMagenticWorkflowAsync(
            workflow,
            approvalResponse,
            checkpointManager,
            secondResult.LastCheckpoint,
            eventCollector: allEvents);

        // Assert: MagenticReplannedEvent should have been emitted, and final answer produced
        allEvents.OfType<MagenticPlanCreatedEvent>().Should().NotBeEmpty("initial plan emits PlanCreatedEvent");
        allEvents.OfType<MagenticReplannedEvent>().Should().NotBeEmpty("revision triggers ReplannedEvent");
        thirdResult.Result.Should().NotBeNull();
        thirdResult.Result![0].Text.Should().Contain("Revised plan executed successfully");
    }

    [Fact]
    public async Task MaxRoundLimit_Terminates_Workflow()
    {
        // Arrange: MaxRounds=1, so round 1 delegates to Worker, round 2 hits limit and terminates.
        // Manager turns: facts1, plan1, ledger1(not satisfied→delegates), facts2, plan2 (re-entry), then limit hit before ledger.
        List<ChatMessage> factsResponse1 = CreatePlanResponse("Facts");
        List<ChatMessage> planResponse1 = CreatePlanResponse("Plan");
        List<ChatMessage> round1Ledger = CreateProgressLedgerResponse(
            isRequestSatisfied: false,
            isInLoop: false,
            isProgressBeingMade: true,
            nextSpeaker: "Worker",
            instructionOrQuestion: "Work on it");

        // Round 2 re-entry: TakeTurnAsync calls UpdatePlanAndDelegateAsync → needs facts + plan
        List<ChatMessage> factsResponse2 = CreatePlanResponse("Updated facts");
        List<ChatMessage> planResponse2 = CreatePlanResponse("Updated plan");
        // No more turns needed: RunCoordinationRoundAsync hits round limit before calling UpdateProgressLedgerAsync

        TestReplayAgent manager = new(
            [factsResponse1, planResponse1, round1Ledger, factsResponse2, planResponse2],
            name: "Manager");
        TestEchoAgent worker = new(name: "Worker");

        Workflow workflow = new MagenticWorkflowBuilder(manager)
            .AddParticipants(worker)
            .RequirePlanSignoff(false)
            .WithMaxRounds(1)
            .Build();

        // Act
        WorkflowRunResult runResult = await RunMagenticWorkflowAsync(
            workflow,
            [new ChatMessage(ChatRole.User, "Do task")]);

        // Assert: Workflow terminates with round limit message
        runResult.Result.Should().NotBeNull();
        runResult.Result![0].Text.Should().Contain("maximum round count limit");
    }

    [Fact]
    public async Task MaxStallCount_Triggers_Reset()
    {
        // Arrange: MaxStallCount=1, so one stall (isInLoop=true) triggers ResetAndReplanAsync.
        // Flow: facts1, plan1 → round1 ledger(stall: isInLoop=true) → StallCount=1 → IsStalled → Reset
        //       → facts2, plan2 (replan) → round2 ledger(satisfied) → finalAnswer
        List<ChatMessage> factsResponse1 = CreatePlanResponse("Initial facts");
        List<ChatMessage> planResponse1 = CreatePlanResponse("Initial plan");
        List<ChatMessage> stalledLedger = CreateProgressLedgerResponse(
            isRequestSatisfied: false,
            isInLoop: true,  // This triggers stall
            isProgressBeingMade: true,
            nextSpeaker: "Worker",
            instructionOrQuestion: "Keep trying");

        // After reset: ResetAndReplanAsync → UpdatePlanAndDelegateAsync → new plan
        List<ChatMessage> factsResponse2 = CreatePlanResponse("Fresh facts after reset");
        List<ChatMessage> planResponse2 = CreatePlanResponse("Fresh plan after reset");
        List<ChatMessage> satisfiedLedger = CreateProgressLedgerResponse(
            isRequestSatisfied: true,
            isInLoop: false,
            isProgressBeingMade: true,
            nextSpeaker: "Worker",
            instructionOrQuestion: "Done");
        List<ChatMessage> finalAnswerResponse = CreateFinalAnswerResponse("Recovered after stall reset");

        TestReplayAgent manager = new(
            [factsResponse1, planResponse1, stalledLedger,
             factsResponse2, planResponse2, satisfiedLedger, finalAnswerResponse],
            name: "Manager");
        TestEchoAgent worker = new(name: "Worker");

        List<WorkflowEvent> collectedEvents = [];

        Workflow workflow = new MagenticWorkflowBuilder(manager)
            .AddParticipants(worker)
            .RequirePlanSignoff(false)
            .WithMaxStalls(1)  // One stall triggers reset
            .Build();

        // Act
        WorkflowRunResult runResult = await RunMagenticWorkflowAsync(
            workflow,
            [new ChatMessage(ChatRole.User, "Do task")],
            eventCollector: collectedEvents);

        // Assert: MagenticReplannedEvent should be emitted (reset triggers replan), final answer produced
        collectedEvents.OfType<MagenticPlanCreatedEvent>().Should().NotBeEmpty("initial plan created");
        collectedEvents.OfType<MagenticReplannedEvent>().Should().NotBeEmpty("stall triggers reset and replan");
        runResult.Result.Should().NotBeNull();
        runResult.Result![0].Text.Should().Contain("Recovered after stall reset");
    }

    #region Helper Methods

    private sealed record WorkflowRunResult(
        string UpdateText,
        List<ChatMessage>? Result,
        CheckpointInfo? LastCheckpoint,
        List<RequestInfoEvent> PendingRequests);

    private static List<ChatMessage> CreatePlanResponse(string plan)
    {
        return
        [
            new ChatMessage(ChatRole.Assistant, plan)
            {
                MessageId = Guid.NewGuid().ToString("N"),
                CreatedAt = DateTimeOffset.UtcNow
            }
        ];
    }

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

        string ledgerJson = $$"""
        {
            "is_request_satisfied": { "answer": {{isRequestSatisfiedStr}}, "reason": "test reason" },
            "is_in_loop": { "answer": {{isInLoopStr}}, "reason": "test reason" },
            "is_progress_being_made": { "answer": {{isProgressBeingMadeStr}}, "reason": "test reason" },
            "next_speaker": { "answer": "{{nextSpeaker}}", "reason": "test reason" },
            "instruction_or_question": { "answer": "{{instructionOrQuestion}}", "reason": "test reason" }
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

    private static List<ChatMessage> CreateFinalAnswerResponse(string answer)
    {
        return
        [
            new ChatMessage(ChatRole.Assistant, answer)
            {
                MessageId = Guid.NewGuid().ToString("N"),
                CreatedAt = DateTimeOffset.UtcNow
            }
        ];
    }

    private static async Task<WorkflowRunResult> ResumeMagenticWorkflowAsync(
        Workflow workflow,
        ExternalResponse response,
        CheckpointManager checkpointManager,
        CheckpointInfo? fromCheckpoint,
        List<WorkflowEvent>? eventCollector = null)
    {
        InProcessExecutionEnvironment environment = ExecutionEnvironment.InProcess_Lockstep
            .ToWorkflowExecutionEnvironment()
            .WithCheckpointing(checkpointManager);

        await using StreamingRun run = fromCheckpoint != null
            ? await environment.ResumeStreamingAsync(workflow, fromCheckpoint)
            : await environment.OpenStreamingAsync(workflow);

        await run.SendResponseAsync(response);

        return await ProcessWorkflowRunAsync(run, eventCollector);
    }

    private static async Task<WorkflowRunResult> RunMagenticWorkflowAsync(
        Workflow workflow,
        List<ChatMessage> input,
        CheckpointManager? checkpointManager = null,
        List<WorkflowEvent>? eventCollector = null)
    {
        checkpointManager ??= CheckpointManager.CreateInMemory();

        InProcessExecutionEnvironment environment = ExecutionEnvironment.InProcess_Lockstep
            .ToWorkflowExecutionEnvironment()
            .WithCheckpointing(checkpointManager);

        await using StreamingRun run = await environment.OpenStreamingAsync(workflow);

        await run.TrySendMessageAsync(input);
        await run.TrySendMessageAsync(new TurnToken(emitEvents: true));

        return await ProcessWorkflowRunAsync(run, eventCollector);
    }

    private static async Task<WorkflowRunResult> ProcessWorkflowRunAsync(
        StreamingRun run,
        List<WorkflowEvent>? eventCollector = null)
    {
        StringBuilder sb = new();
        WorkflowOutputEvent? output = null;
        CheckpointInfo? lastCheckpoint = null;
        List<RequestInfoEvent> pendingRequests = [];

        await foreach (WorkflowEvent evt in run.WatchStreamAsync(blockOnPendingRequest: false).ConfigureAwait(false))
        {
            eventCollector?.Add(evt);

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

    #endregion
}
