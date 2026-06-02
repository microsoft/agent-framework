// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using System.Text.Json;
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
    public async Task Task_Completes_When_RequestSatisfiedAsync()
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
    public async Task PlanReview_Approved_ProceedsAsync()
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
    public async Task Initial_Plan_Emits_PlanCreatedEventAsync()
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
    public async Task NextSpeaker_Invalid_Triggers_FinalAnswerAsync()
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
    public async Task ProgressLedger_Updated_Event_EmittedAsync()
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
    public async Task PlanSignoff_Disabled_Proceeds_ImmediatelyAsync()
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
    public async Task NextSpeaker_Empty_Falls_Back_To_FirstAsync()
    {
        // Arrange: First progress ledger returns empty next_speaker, which should fall back to first participant.
        // Round 1: empty speaker → fallback to Worker (first participant) → Worker echoes
        // Round 2 (after Worker responds): RunCoordinationRoundAsync → satisfied ledger → final answer
        // Note: No replan on agent return — only progress ledger is created on subsequent turns.
        List<ChatMessage> factsResponse1 = CreatePlanResponse("Facts about the task");
        List<ChatMessage> planResponse1 = CreatePlanResponse("Step 1: Execute");
        List<ChatMessage> emptyNextSpeakerLedger = CreateProgressLedgerResponse(
            isRequestSatisfied: false,
            isInLoop: false,
            isProgressBeingMade: true,
            nextSpeaker: "",  // Empty - should fall back to first participant
            instructionOrQuestion: "Please help with this task");

        // Round 2: satisfied ledger + final answer (no replan on normal agent return)
        List<ChatMessage> satisfiedLedger = CreateProgressLedgerResponse(
            isRequestSatisfied: true,
            isInLoop: false,
            isProgressBeingMade: true,
            nextSpeaker: "Worker",
            instructionOrQuestion: "Done");
        List<ChatMessage> finalAnswerResponse = CreateFinalAnswerResponse("Task completed after fallback");

        TestReplayAgent manager = new(
            [factsResponse1, planResponse1, emptyNextSpeakerLedger,
             satisfiedLedger, finalAnswerResponse],
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
    public async Task Task_Completes_After_Multiple_RoundsAsync()
    {
        // Arrange: Round 1 delegates to Worker (not satisfied), round 2 completes
        // Manager turn sequence: facts1, plan1, ledger1(not satisfied), ledger2(satisfied), finalAnswer
        // Note: No replan on agent return — only progress ledger is created on subsequent turns.
        List<ChatMessage> factsResponse1 = CreatePlanResponse("Initial facts");
        List<ChatMessage> planResponse1 = CreatePlanResponse("Step 1: Delegate to worker");
        List<ChatMessage> round1Ledger = CreateProgressLedgerResponse(
            isRequestSatisfied: false,
            isInLoop: false,
            isProgressBeingMade: true,
            nextSpeaker: "Worker",
            instructionOrQuestion: "Please work on the task");

        List<ChatMessage> round2Ledger = CreateProgressLedgerResponse(
            isRequestSatisfied: true,
            isInLoop: false,
            isProgressBeingMade: true,
            nextSpeaker: "Worker",
            instructionOrQuestion: "Task is done");
        List<ChatMessage> finalAnswerResponse = CreateFinalAnswerResponse("Multi-round task completed!");

        TestReplayAgent manager = new(
            [factsResponse1, planResponse1, round1Ledger,
             round2Ledger, finalAnswerResponse],
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

        // Assert: One plan created, one progress ledger per round, final answer
        collectedEvents.OfType<MagenticProgressLedgerUpdatedEvent>().Should().HaveCount(2);
        collectedEvents.OfType<MagenticPlanCreatedEvent>().Should().ContainSingle("only one initial plan, no replan on agent return");
        collectedEvents.OfType<MagenticReplannedEvent>().Should().BeEmpty("no replan occurs on normal agent return");
        runResult.Result.Should().NotBeNull();
        runResult.Result![0].Text.Should().Contain("Multi-round task completed!");
    }

    [Fact]
    public async Task RunCoordinationRound_Forwards_Participant_Reply_To_ManagerAsync()
    {
        // Regression: MagenticOrchestrator.TakeTurnAsync used to drop the `messages`
        // parameter on subsequent turns, so participant replies never reached the
        // manager's ChatHistory. The manager then re-dispatched the same speaker
        // every round until MaxRounds. Assert that round-2's progress-ledger call
        // actually sees the worker's reply in its input.

        const string TaskPrompt = "Echo back this exact magentic-regression-marker";

        List<ChatMessage> factsResponse = CreatePlanResponse("Facts");
        List<ChatMessage> planResponse = CreatePlanResponse("Plan");
        List<ChatMessage> round1Ledger = CreateProgressLedgerResponse(
            isRequestSatisfied: false,
            isInLoop: false,
            isProgressBeingMade: true,
            nextSpeaker: "Worker",
            instructionOrQuestion: TaskPrompt);
        List<ChatMessage> round2Ledger = CreateProgressLedgerResponse(
            isRequestSatisfied: true,
            isInLoop: false,
            isProgressBeingMade: true,
            nextSpeaker: "Worker",
            instructionOrQuestion: "Done");
        List<ChatMessage> finalAnswer = CreateFinalAnswerResponse("All good");

        RecordingReplayAgent manager = new(
            [factsResponse, planResponse, round1Ledger, round2Ledger, finalAnswer],
            name: "Manager");
        TestEchoAgent worker = new(name: "Worker");

        Workflow workflow = new MagenticWorkflowBuilder(manager)
            .AddParticipants(worker)
            .RequirePlanSignoff(false)
            .Build();

        WorkflowRunResult runResult = await RunMagenticWorkflowAsync(
            workflow,
            [new ChatMessage(ChatRole.User, TaskPrompt)]);

        runResult.Result.Should().NotBeNull();
        runResult.Result![0].Text.Should().Contain("All good");

        // Calls in order: facts, plan, ledger1, ledger2, finalAnswer.
        manager.RecordedInputs.Should().HaveCount(5);

        manager.RecordedInputs[3].Should().Contain(
            m => m.Role == ChatRole.Assistant
              && m.AuthorName == "Worker"
              && m.Text.Contains(TaskPrompt),
            "round-2 progress ledger must see the worker's reply; without it the manager loops to MaxRounds");

        manager.RecordedInputs[4].Should().Contain(
            m => m.Role == ChatRole.Assistant && m.AuthorName == "Worker",
            "final-answer synthesis must see what participants actually said");
    }

    [Fact]
    public async Task PlanReview_Revised_Triggers_ReplanAsync()
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
    public async Task MaxRoundLimit_Terminates_WorkflowAsync()
    {
        // Arrange: MaxRounds=1, so round 1 delegates to Worker, round 2 hits limit and terminates.
        // Manager turns: facts1, plan1, ledger1(not satisfied→delegates), then limit hit before ledger.
        List<ChatMessage> factsResponse1 = CreatePlanResponse("Facts");
        List<ChatMessage> planResponse1 = CreatePlanResponse("Plan");
        List<ChatMessage> round1Ledger = CreateProgressLedgerResponse(
            isRequestSatisfied: false,
            isInLoop: false,
            isProgressBeingMade: true,
            nextSpeaker: "Worker",
            instructionOrQuestion: "Work on it");

        // No more turns needed: RunCoordinationRoundAsync hits round limit before calling UpdateProgressLedgerAsync

        TestReplayAgent manager = new(
            [factsResponse1, planResponse1, round1Ledger],
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
    public async Task MaxStallCount_Triggers_ResetAsync()
    {
        // Arrange: MaxStallCount=0, so one stall (isInLoop=true, StallCount=1 > 0) triggers ResetAndReplanAsync.
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
            .WithMaxStalls(0)  // One stall triggers reset (StallCount 1 > 0)
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

    [Fact]
    public async Task Instruction_Message_Sent_When_PresentAsync()
    {
        // Arrange: Progress ledger has a non-empty instruction_or_question.
        // The orchestrator should send the instruction as a ChatMessage before delegating to the next agent.
        // After Worker echoes, the second round completes.
        List<ChatMessage> factsResponse1 = CreatePlanResponse("Facts about the task");
        List<ChatMessage> planResponse1 = CreatePlanResponse("Step 1: Instruct the worker");
        List<ChatMessage> ledgerWithInstruction = CreateProgressLedgerResponse(
            isRequestSatisfied: false,
            isInLoop: false,
            isProgressBeingMade: true,
            nextSpeaker: "Worker",
            instructionOrQuestion: "Please analyze the data carefully");

        // Round 2 after Worker responds (no replan, just progress ledger)
        List<ChatMessage> satisfiedLedger = CreateProgressLedgerResponse(
            isRequestSatisfied: true,
            isInLoop: false,
            isProgressBeingMade: true,
            nextSpeaker: "Worker",
            instructionOrQuestion: "Done");
        List<ChatMessage> finalAnswerResponse = CreateFinalAnswerResponse("Task completed with instruction");

        TestReplayAgent manager = new(
            [factsResponse1, planResponse1, ledgerWithInstruction,
             satisfiedLedger, finalAnswerResponse],
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
            [new ChatMessage(ChatRole.User, "Analyze data")],
            eventCollector: collectedEvents);

        // Assert: The workflow completed successfully, proving the instruction path executed without error.
        // The update text should contain the instruction text since it is sent to participants as a ChatMessage.
        runResult.Result.Should().NotBeNull();
        runResult.Result![0].Text.Should().Contain("Task completed with instruction");
        // Verify the delegation happened (two progress ledger events for two rounds)
        collectedEvents.OfType<MagenticProgressLedgerUpdatedEvent>().Should().HaveCount(2);
    }

    [Fact]
    public async Task PlanReview_On_Stall_ReplanAsync()
    {
        // Arrange: Plan signoff enabled, stall triggers reset, replan requires new plan review.
        // Flow: facts1, plan1 → PlanCreatedEvent → plan review (pending)
        //       resume with approval → ledger1(stall: isInLoop=true) → StallCount=1 → IsStalled → Reset
        //       → facts2, plan2 → MagenticReplannedEvent → plan review again (pending)
        //       resume with approval → ledger2(satisfied) → finalAnswer
        List<ChatMessage> factsResponse1 = CreatePlanResponse("Initial facts");
        List<ChatMessage> planResponse1 = CreatePlanResponse("Initial plan");
        List<ChatMessage> stalledLedger = CreateProgressLedgerResponse(
            isRequestSatisfied: false,
            isInLoop: true,  // This triggers stall
            isProgressBeingMade: true,
            nextSpeaker: "Worker",
            instructionOrQuestion: "Keep trying");

        // After reset: new plan
        List<ChatMessage> factsResponse2 = CreatePlanResponse("Fresh facts after stall reset");
        List<ChatMessage> planResponse2 = CreatePlanResponse("Fresh plan after stall reset");
        // After second approval: satisfied ledger + final answer
        List<ChatMessage> satisfiedLedger = CreateProgressLedgerResponse(
            isRequestSatisfied: true,
            isInLoop: false,
            isProgressBeingMade: true,
            nextSpeaker: "Worker",
            instructionOrQuestion: "Done");
        List<ChatMessage> finalAnswerResponse = CreateFinalAnswerResponse("Recovered after stall with plan review");

        TestReplayAgent manager = new(
            [factsResponse1, planResponse1, stalledLedger,
             factsResponse2, planResponse2, satisfiedLedger, finalAnswerResponse],
            name: "Manager");
        TestEchoAgent worker = new(name: "Worker");

        Workflow workflow = new MagenticWorkflowBuilder(manager)
            .AddParticipants(worker)
            .RequirePlanSignoff(true)
            .WithMaxStalls(0)
            .Build();

        CheckpointManager checkpointManager = CheckpointManager.CreateInMemory();
        List<WorkflowEvent> allEvents = [];

        // Act 1: First run - should pause for initial plan review
        WorkflowRunResult firstResult = await RunMagenticWorkflowAsync(
            workflow,
            [new ChatMessage(ChatRole.User, "Do task")],
            checkpointManager: checkpointManager,
            eventCollector: allEvents);

        firstResult.PendingRequests.Should().ContainSingle();
        ExternalRequest request1 = firstResult.PendingRequests[0].Request;
        MagenticPlanReviewRequest? reviewRequest1 = request1.Data.As<MagenticPlanReviewRequest>();
        reviewRequest1.Should().NotBeNull();
        reviewRequest1!.Plan.Text.Should().Contain("Initial plan");
        reviewRequest1.IsStalled.Should().BeFalse("the initial plan review is not stall-triggered");

        // Act 2: Approve initial plan → stall occurs → reset → replan → new plan review
        MagenticPlanReviewResponse approval1 = reviewRequest1.Approve();
        ExternalResponse approvalResponse1 = request1.CreateResponse(approval1);
        WorkflowRunResult secondResult = await ResumeMagenticWorkflowAsync(
            workflow,
            approvalResponse1,
            checkpointManager,
            firstResult.LastCheckpoint,
            eventCollector: allEvents);

        // Should pause for review of the replanned plan
        secondResult.PendingRequests.Should().NotBeEmpty();
        ExternalRequest request2 = secondResult.PendingRequests[^1].Request;
        MagenticPlanReviewRequest? reviewRequest2 = request2.Data.As<MagenticPlanReviewRequest>();
        reviewRequest2.Should().NotBeNull();
        reviewRequest2!.Plan.Text.Should().Contain("Fresh plan after stall reset");
        reviewRequest2.IsStalled.Should().BeTrue("the replan was triggered by a stall");

        // Act 3: Approve the revised plan → satisfied → final answer
        MagenticPlanReviewResponse approval2 = reviewRequest2.Approve();
        ExternalResponse approvalResponse2 = request2.CreateResponse(approval2);
        WorkflowRunResult thirdResult = await ResumeMagenticWorkflowAsync(
            workflow,
            approvalResponse2,
            checkpointManager,
            secondResult.LastCheckpoint,
            eventCollector: allEvents);

        // Assert
        allEvents.OfType<MagenticPlanCreatedEvent>().Should().NotBeEmpty("initial plan emits PlanCreatedEvent");
        allEvents.OfType<MagenticReplannedEvent>().Should().NotBeEmpty("stall reset triggers ReplannedEvent");
        thirdResult.Result.Should().NotBeNull();
        thirdResult.Result![0].Text.Should().Contain("Recovered after stall with plan review");
    }

    [Fact]
    public async Task MaxResetLimit_Terminates_WorkflowAsync()
    {
        // Arrange: MaxStallCount=0, MaxResets=1.
        // Flow: facts1, plan1 → ledger1(stall: isInLoop=true) → StallCount=1 > 0 → IsStalled → ResetAndReplanAsync
        //       → ResetCount becomes 1 → facts2, plan2 → DelegateToTeamAsync
        //       → RunCoordinationRoundAsync: CheckLimits() detects ResetCount(1) >= MaxResetCount(1) → terminates
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
        // No more turns needed: RunCoordinationRoundAsync hits reset limit before calling UpdateProgressLedgerAsync

        TestReplayAgent manager = new(
            [factsResponse1, planResponse1, stalledLedger,
             factsResponse2, planResponse2],
            name: "Manager");
        TestEchoAgent worker = new(name: "Worker");

        Workflow workflow = new MagenticWorkflowBuilder(manager)
            .AddParticipants(worker)
            .RequirePlanSignoff(false)
            .WithMaxStalls(0)   // One stall triggers reset (StallCount 1 > 0)
            .WithMaxResets(1)   // One reset triggers termination
            .Build();

        // Act
        WorkflowRunResult runResult = await RunMagenticWorkflowAsync(
            workflow,
            [new ChatMessage(ChatRole.User, "Do task")]);

        // Assert: Workflow terminates with reset limit message
        runResult.Result.Should().NotBeNull();
        runResult.Result![0].Text.Should().Contain("maximum reset count limit");
    }

    [Fact]
    public async Task ProgressLedger_Retry_On_Parse_FailureAsync()
    {
        // Arrange: First progress ledger attempt returns invalid JSON (triggers parse failure + warning),
        // second attempt returns valid JSON (satisfied=true).
        // Manager turn sequence: facts, plan, INVALID_JSON, VALID_LEDGER(satisfied), finalAnswer
        // MagenticManager.UpdateProgressLedgerAsync retries internally: attempt 0 fails, attempt 1 succeeds.
        List<ChatMessage> factsResponse = CreatePlanResponse("Facts about the task");
        List<ChatMessage> planResponse = CreatePlanResponse("Step 1: Execute");
        List<ChatMessage> invalidLedgerResponse = CreatePlanResponse("This is not valid JSON for a progress ledger");
        List<ChatMessage> validLedgerResponse = CreateProgressLedgerResponse(
            isRequestSatisfied: true,
            isInLoop: false,
            isProgressBeingMade: true,
            nextSpeaker: "Worker",
            instructionOrQuestion: "Done after retry");
        List<ChatMessage> finalAnswerResponse = CreateFinalAnswerResponse("Completed after ledger retry");

        TestReplayAgent manager = new(
            [factsResponse, planResponse, invalidLedgerResponse, validLedgerResponse, finalAnswerResponse],
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

        // Assert: Warning emitted for parse failure, but workflow completes successfully
        collectedEvents.OfType<WorkflowWarningEvent>()
            .Should().Contain(e => e.Data != null && e.Data.ToString()!.Contains("Progress ledger JSON parse failed"));
        runResult.Result.Should().NotBeNull();
        runResult.Result![0].Text.Should().Contain("Completed after ledger retry");
    }

    [Fact]
    public async Task ProgressLedger_Max_Retries_Triggers_ResetAsync()
    {
        // Arrange: All 3 progress ledger retry attempts return invalid JSON → exception → ResetAndReplanAsync.
        // After reset: new plan, valid ledger (satisfied), final answer.
        // Turn sequence: facts1, plan1, invalidJSON×3, facts2, plan2, validLedger(satisfied), finalAnswer
        List<ChatMessage> factsResponse1 = CreatePlanResponse("Initial facts");
        List<ChatMessage> planResponse1 = CreatePlanResponse("Initial plan");
        List<ChatMessage> invalidLedger1 = CreatePlanResponse("not json at all");
        List<ChatMessage> invalidLedger2 = CreatePlanResponse("still not json");
        List<ChatMessage> invalidLedger3 = CreatePlanResponse("definitely not json");

        // After reset: ResetAndReplanAsync → UpdatePlanAndDelegateAsync → new plan
        List<ChatMessage> factsResponse2 = CreatePlanResponse("Fresh facts after reset");
        List<ChatMessage> planResponse2 = CreatePlanResponse("Fresh plan after reset");
        List<ChatMessage> validLedger = CreateProgressLedgerResponse(
            isRequestSatisfied: true,
            isInLoop: false,
            isProgressBeingMade: true,
            nextSpeaker: "Worker",
            instructionOrQuestion: "Done after reset");
        List<ChatMessage> finalAnswerResponse = CreateFinalAnswerResponse("Recovered after max retries reset");

        TestReplayAgent manager = new(
            [factsResponse1, planResponse1, invalidLedger1, invalidLedger2, invalidLedger3,
             factsResponse2, planResponse2, validLedger, finalAnswerResponse],
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

        // Assert: Parse failure warnings emitted, reset triggered (ReplannedEvent), workflow completes
        collectedEvents.OfType<WorkflowWarningEvent>()
            .Where(e => e.Data?.ToString()?.Contains("Progress ledger JSON parse failed") == true)
            .Should().HaveCountGreaterThanOrEqualTo(3, "all 3 retry attempts should emit warnings");
        collectedEvents.OfType<WorkflowWarningEvent>()
            .Should().Contain(e => e.Data != null && e.Data.ToString()!.Contains("triggering reset"));
        collectedEvents.OfType<MagenticReplannedEvent>().Should().NotBeEmpty("reset triggers replan");
        runResult.Result.Should().NotBeNull();
        runResult.Result![0].Text.Should().Contain("Recovered after max retries reset");
    }

    [Fact]
    public async Task Stall_NoProgress_Increments_StallCountAsync()
    {
        // Arrange: MaxStallCount=0, progress ledger reports IsProgressBeingMade=false (not IsInLoop).
        // This exercises the alternative stall trigger: !IsProgressBeingMade.
        // Flow: facts1, plan1 → ledger1(IsProgressBeingMade=false) → StallCount=1 > 0 → IsStalled → Reset
        //       → facts2, plan2 (replan) → ledger2(satisfied) → finalAnswer
        List<ChatMessage> factsResponse1 = CreatePlanResponse("Initial facts");
        List<ChatMessage> planResponse1 = CreatePlanResponse("Initial plan");
        List<ChatMessage> noProgressLedger = CreateProgressLedgerResponse(
            isRequestSatisfied: false,
            isInLoop: false,           // Not in loop
            isProgressBeingMade: false, // But no progress → stall
            nextSpeaker: "Worker",
            instructionOrQuestion: "Keep trying");

        // After reset: ResetAndReplanAsync → UpdatePlanAndDelegateAsync → new plan
        List<ChatMessage> factsResponse2 = CreatePlanResponse("Fresh facts after no-progress reset");
        List<ChatMessage> planResponse2 = CreatePlanResponse("Fresh plan after no-progress reset");
        List<ChatMessage> satisfiedLedger = CreateProgressLedgerResponse(
            isRequestSatisfied: true,
            isInLoop: false,
            isProgressBeingMade: true,
            nextSpeaker: "Worker",
            instructionOrQuestion: "Done");
        List<ChatMessage> finalAnswerResponse = CreateFinalAnswerResponse("Recovered after no-progress stall");

        TestReplayAgent manager = new(
            [factsResponse1, planResponse1, noProgressLedger,
             factsResponse2, planResponse2, satisfiedLedger, finalAnswerResponse],
            name: "Manager");
        TestEchoAgent worker = new(name: "Worker");

        List<WorkflowEvent> collectedEvents = [];

        Workflow workflow = new MagenticWorkflowBuilder(manager)
            .AddParticipants(worker)
            .RequirePlanSignoff(false)
            .WithMaxStalls(0)
            .Build();

        // Act
        WorkflowRunResult runResult = await RunMagenticWorkflowAsync(
            workflow,
            [new ChatMessage(ChatRole.User, "Do task")],
            eventCollector: collectedEvents);

        // Assert: Stall detected via no-progress, reset triggered, replan emitted, workflow completes
        collectedEvents.OfType<MagenticReplannedEvent>().Should().NotBeEmpty("no-progress stall triggers reset and replan");
        runResult.Result.Should().NotBeNull();
        runResult.Result![0].Text.Should().Contain("Recovered after no-progress stall");
    }

    [Fact]
    public async Task Task_Delegates_To_Correct_AgentAsync()
    {
        // Arrange: Two participants (WorkerA, WorkerB). Manager selects "WorkerA" as next speaker.
        // We verify that WorkerA produces a response update event and WorkerB does not.
        // Flow: facts1, plan1 → ledger1(nextSpeaker=WorkerA, not satisfied) → WorkerA runs
        //       → RunCoordinationRoundAsync (no replan) → ledger2(satisfied) → finalAnswer
        List<ChatMessage> factsResponse1 = CreatePlanResponse("Task delegation facts");
        List<ChatMessage> planResponse1 = CreatePlanResponse("Delegate to WorkerA");
        List<ChatMessage> ledger1 = CreateProgressLedgerResponse(
            isRequestSatisfied: false,
            isInLoop: false,
            isProgressBeingMade: true,
            nextSpeaker: "WorkerA",
            instructionOrQuestion: "WorkerA please handle this");

        // After WorkerA responds, orchestrator goes directly to RunCoordinationRoundAsync (no replan)
        List<ChatMessage> ledger2 = CreateProgressLedgerResponse(
            isRequestSatisfied: true,
            isInLoop: false,
            isProgressBeingMade: true,
            nextSpeaker: "WorkerA",
            instructionOrQuestion: "Done");
        List<ChatMessage> finalAnswerResponse = CreateFinalAnswerResponse("Delegated correctly!");

        TestReplayAgent manager = new(
            [factsResponse1, planResponse1, ledger1,
             ledger2, finalAnswerResponse],
            name: "Manager");
        TestEchoAgent workerA = new(name: "WorkerA", prefix: "[A] ");
        TestEchoAgent workerB = new(name: "WorkerB", prefix: "[B] ");

        List<WorkflowEvent> collectedEvents = [];

        Workflow workflow = new MagenticWorkflowBuilder(manager)
            .AddParticipants(workerA, workerB)
            .RequirePlanSignoff(false)
            .Build();

        // Act
        WorkflowRunResult runResult = await RunMagenticWorkflowAsync(
            workflow,
            [new ChatMessage(ChatRole.User, "Test delegation routing")],
            eventCollector: collectedEvents);

        // Assert: WorkerA should have produced response updates, WorkerB should not
        List<AgentResponseUpdateEvent> agentUpdates = collectedEvents.OfType<AgentResponseUpdateEvent>().ToList();

        // WorkerA's executor should appear in the events
        agentUpdates.Should().Contain(e => e.Update.AuthorName == "WorkerA",
            "WorkerA was selected as next speaker and should have responded");

        // WorkerB should NOT have responded
        agentUpdates.Should().NotContain(e => e.Update.AuthorName == "WorkerB",
            "WorkerB was not selected and should not have responded");

        runResult.Result.Should().NotBeNull();
        runResult.Result![0].Text.Should().Contain("Delegated correctly!");
    }

    [Fact]
    public async Task Progress_Made_Decrements_StallCountAsync()
    {
        // Arrange: MaxStallCount=3, so a single stall won't trigger reset.
        // Round 1: isInLoop=true (stall count → 1), delegates to Worker
        // Round 2: progress being made (stall count → 0), delegates to Worker
        // Round 3: satisfied → final answer
        // No reset should occur because the stall count was decremented before reaching threshold.
        List<ChatMessage> facts1 = CreatePlanResponse("Initial facts");
        List<ChatMessage> plan1 = CreatePlanResponse("Initial plan");
        List<ChatMessage> ledger1 = CreateProgressLedgerResponse(
            isRequestSatisfied: false,
            isInLoop: true,  // triggers stall increment → StallCount=1
            isProgressBeingMade: true,
            nextSpeaker: "Worker",
            instructionOrQuestion: "Keep trying");

        // After Worker responds → RunCoordinationRoundAsync (no replan)
        List<ChatMessage> ledger2 = CreateProgressLedgerResponse(
            isRequestSatisfied: false,
            isInLoop: false,
            isProgressBeingMade: true,  // progress → stall count decrements → StallCount=0
            nextSpeaker: "Worker",
            instructionOrQuestion: "Good progress");

        // After Worker responds → RunCoordinationRoundAsync (no replan)
        List<ChatMessage> ledger3 = CreateProgressLedgerResponse(
            isRequestSatisfied: true,
            isInLoop: false,
            isProgressBeingMade: true,
            nextSpeaker: "Worker",
            instructionOrQuestion: "All done");
        List<ChatMessage> finalAnswerResponse = CreateFinalAnswerResponse("Completed without reset!");

        TestReplayAgent manager = new(
            [facts1, plan1, ledger1,
             ledger2,
             ledger3, finalAnswerResponse],
            name: "Manager");
        TestEchoAgent worker = new(name: "Worker");

        List<WorkflowEvent> collectedEvents = [];

        Workflow workflow = new MagenticWorkflowBuilder(manager)
            .AddParticipants(worker)
            .RequirePlanSignoff(false)
            .WithMaxStalls(3)  // high threshold so single stall doesn't trigger reset
            .Build();

        // Act
        WorkflowRunResult runResult = await RunMagenticWorkflowAsync(
            workflow,
            [new ChatMessage(ChatRole.User, "Test stall decrement")],
            eventCollector: collectedEvents);

        // Assert: Three progress ledger updates, no stall-triggered reset
        collectedEvents.OfType<MagenticProgressLedgerUpdatedEvent>().Should().HaveCount(3,
            "three coordination rounds should produce three progress ledger events");

        // One initial plan, no replans (agent returns go directly to coordination, no replan)
        collectedEvents.OfType<MagenticPlanCreatedEvent>().Should().ContainSingle(
            "only one initial plan should be created");
        collectedEvents.OfType<MagenticReplannedEvent>().Should().BeEmpty(
            "no replan occurs on normal agent return; stall count never exceeded threshold");

        runResult.Result.Should().NotBeNull();
        runResult.Result![0].Text.Should().Contain("Completed without reset!");
    }

    [Fact]
    public async Task Consecutive_Stalls_Trigger_ResetAsync()
    {
        // Arrange: MaxStallCount=1 — two consecutive stalls trigger reset (StallCount 2 > 1).
        // Round 1: isInLoop=true (stall count → 1), delegates to Worker
        // Round 2: isProgressBeingMade=false (stall count → 2 > 1 → IsStalled) → reset & replan
        // After reset: new plan → ledger(satisfied) → final answer
        List<ChatMessage> facts1 = CreatePlanResponse("Initial facts");
        List<ChatMessage> plan1 = CreatePlanResponse("Initial plan");
        List<ChatMessage> ledger1 = CreateProgressLedgerResponse(
            isRequestSatisfied: false,
            isInLoop: true,  // stall #1 → StallCount=1
            isProgressBeingMade: true,
            nextSpeaker: "Worker",
            instructionOrQuestion: "Keep trying");

        // After Worker responds → RunCoordinationRoundAsync (no replan)
        List<ChatMessage> ledger2 = CreateProgressLedgerResponse(
            isRequestSatisfied: false,
            isInLoop: false,
            isProgressBeingMade: false,  // stall #2 → StallCount=2 > 1 → IsStalled → reset
            nextSpeaker: "Worker",
            instructionOrQuestion: "No progress");

        // Reset & replan: new facts + plan, then coordination round
        List<ChatMessage> resetFacts = CreatePlanResponse("Fresh facts after stall reset");
        List<ChatMessage> resetPlan = CreatePlanResponse("Fresh plan after stall reset");
        List<ChatMessage> postResetLedger = CreateProgressLedgerResponse(
            isRequestSatisfied: true,
            isInLoop: false,
            isProgressBeingMade: true,
            nextSpeaker: "Worker",
            instructionOrQuestion: "Done");
        List<ChatMessage> finalAnswerResponse = CreateFinalAnswerResponse("Recovered after consecutive stalls!");

        TestReplayAgent manager = new(
            [facts1, plan1, ledger1,
             ledger2,
             resetFacts, resetPlan, postResetLedger, finalAnswerResponse],
            name: "Manager");
        TestEchoAgent worker = new(name: "Worker");

        List<WorkflowEvent> collectedEvents = [];

        Workflow workflow = new MagenticWorkflowBuilder(manager)
            .AddParticipants(worker)
            .RequirePlanSignoff(false)
            .WithMaxStalls(1)  // requires 2 consecutive stalls (StallCount > 1)
            .Build();

        // Act
        WorkflowRunResult runResult = await RunMagenticWorkflowAsync(
            workflow,
            [new ChatMessage(ChatRole.User, "Test consecutive stalls")],
            eventCollector: collectedEvents);

        // Assert: Two pre-reset coordination rounds + one post-reset round = 3 ledger events
        collectedEvents.OfType<MagenticProgressLedgerUpdatedEvent>().Should().HaveCount(3,
            "two pre-reset rounds and one post-reset round");

        // One initial plan + one stall-triggered reset replan (no normal re-entry replans anymore)
        collectedEvents.OfType<MagenticPlanCreatedEvent>().Should().ContainSingle();
        collectedEvents.OfType<MagenticReplannedEvent>().Should().ContainSingle(
            "only one replan from stall-triggered reset; no replan on normal agent return");

        runResult.Result.Should().NotBeNull();
        runResult.Result![0].Text.Should().Contain("Recovered after consecutive stalls!");
    }

    [Fact]
    public async Task PlanReview_Multiple_RevisionsAsync()
    {
        // Arrange: Human rejects the plan twice before approving on the third review.
        // Flow: facts1, plan1 → PlanCreatedEvent → plan review (pending)
        //       resume with revision1 → facts2, plan2 → ReplannedEvent → plan review (pending)
        //       resume with revision2 → facts3, plan3 → ReplannedEvent → plan review (pending)
        //       resume with approval → ledger(satisfied) → finalAnswer
        List<ChatMessage> factsResponse1 = CreatePlanResponse("Initial facts");
        List<ChatMessage> planResponse1 = CreatePlanResponse("Initial plan - too vague");
        List<ChatMessage> factsResponse2 = CreatePlanResponse("Revised facts v2");
        List<ChatMessage> planResponse2 = CreatePlanResponse("Revised plan v2 - still needs work");
        List<ChatMessage> factsResponse3 = CreatePlanResponse("Revised facts v3");
        List<ChatMessage> planResponse3 = CreatePlanResponse("Revised plan v3 - final version");
        List<ChatMessage> progressLedgerResponse = CreateProgressLedgerResponse(
            isRequestSatisfied: true,
            isInLoop: false,
            isProgressBeingMade: true,
            nextSpeaker: "Worker",
            instructionOrQuestion: "Execute final plan");
        List<ChatMessage> finalAnswerResponse = CreateFinalAnswerResponse("Completed after multiple revisions");

        TestReplayAgent manager = new(
            [factsResponse1, planResponse1,
             factsResponse2, planResponse2,
             factsResponse3, planResponse3,
             progressLedgerResponse, finalAnswerResponse],
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

        // Act 2: Resume with first revision
        MagenticPlanReviewResponse revision1 = reviewRequest1.Revise("Too vague, add more detail");
        ExternalResponse revisionResponse1 = request1.CreateResponse(revision1);
        WorkflowRunResult secondResult = await ResumeMagenticWorkflowAsync(
            workflow,
            revisionResponse1,
            checkpointManager,
            firstResult.LastCheckpoint,
            eventCollector: allEvents);

        secondResult.PendingRequests.Should().NotBeEmpty();
        ExternalRequest request2 = secondResult.PendingRequests[^1].Request;
        MagenticPlanReviewRequest? reviewRequest2 = request2.Data.As<MagenticPlanReviewRequest>();
        reviewRequest2.Should().NotBeNull();
        reviewRequest2!.Plan.Text.Should().Contain("Revised plan v2");

        // Act 3: Resume with second revision
        MagenticPlanReviewResponse revision2 = reviewRequest2.Revise("Still needs more work on step 3");
        ExternalResponse revisionResponse2 = request2.CreateResponse(revision2);
        WorkflowRunResult thirdResult = await ResumeMagenticWorkflowAsync(
            workflow,
            revisionResponse2,
            checkpointManager,
            secondResult.LastCheckpoint,
            eventCollector: allEvents);

        thirdResult.PendingRequests.Should().NotBeEmpty();
        ExternalRequest request3 = thirdResult.PendingRequests[^1].Request;
        MagenticPlanReviewRequest? reviewRequest3 = request3.Data.As<MagenticPlanReviewRequest>();
        reviewRequest3.Should().NotBeNull();
        reviewRequest3!.Plan.Text.Should().Contain("Revised plan v3");

        // Act 4: Resume with approval
        MagenticPlanReviewResponse approval = reviewRequest3.Approve();
        ExternalResponse approvalResponse = request3.CreateResponse(approval);
        WorkflowRunResult fourthResult = await ResumeMagenticWorkflowAsync(
            workflow,
            approvalResponse,
            checkpointManager,
            thirdResult.LastCheckpoint,
            eventCollector: allEvents);

        // Assert: Multiple replan events emitted, final answer produced
        allEvents.OfType<MagenticPlanCreatedEvent>().Should().NotBeEmpty("initial plan emits PlanCreatedEvent");
        allEvents.OfType<MagenticReplannedEvent>().Should().HaveCountGreaterThanOrEqualTo(2,
            "two revisions should emit at least two ReplannedEvents");
        fourthResult.Result.Should().NotBeNull();
        fourthResult.Result![0].Text.Should().Contain("Completed after multiple revisions");
    }

    [Fact]
    public void Empty_Team_Build_Throws()
    {
        // Arrange: No participants added to the builder.
        TestReplayAgent manager = new(
            [CreatePlanResponse("Facts"), CreatePlanResponse("Plan")],
            name: "Manager");

        MagenticWorkflowBuilder builder = new MagenticWorkflowBuilder(manager)
            // No .AddParticipants() — empty team
            .RequirePlanSignoff(false);

        // Act & Assert: Build() should throw because the team is empty.
        Action buildAction = () => builder.Build();
        buildAction.Should().Throw<InvalidOperationException>()
            .WithMessage("*participant*");
    }

    [Fact]
    public async Task Terminated_Context_Rejects_New_MessagesAsync()
    {
        // Arrange: Run a workflow to completion so IsTerminated=true, then send another message.
        // The framework accepts the message (TrySendMessageAsync returns true), but Magentic
        // should error out internally, surfacing as a WorkflowErrorEvent.
        List<ChatMessage> factsResponse = CreatePlanResponse("Facts");
        List<ChatMessage> planResponse = CreatePlanResponse("The plan");
        List<ChatMessage> satisfiedLedger = CreateProgressLedgerResponse(
            isRequestSatisfied: true,
            isInLoop: false,
            isProgressBeingMade: true,
            nextSpeaker: "Worker",
            instructionOrQuestion: "Done");
        List<ChatMessage> finalAnswerResponse = CreateFinalAnswerResponse("Task done");

        TestReplayAgent manager = new(
            [factsResponse, planResponse, satisfiedLedger, finalAnswerResponse],
            name: "Manager");
        TestEchoAgent worker = new(name: "Worker");

        Workflow workflow = new MagenticWorkflowBuilder(manager)
            .AddParticipants(worker)
            .RequirePlanSignoff(false)
            .Build();

        InProcessExecutionEnvironment environment = ExecutionEnvironment.InProcess_Lockstep
            .ToWorkflowExecutionEnvironment()
            .WithCheckpointing(CheckpointManager.CreateInMemory());

        await using StreamingRun run = await environment.OpenStreamingAsync(workflow);

        // Send the initial messages and run to completion
        await run.TrySendMessageAsync(new List<ChatMessage> { new(ChatRole.User, "Do the task") });
        await run.TrySendMessageAsync(new TurnToken(emitEvents: true));

        // Drain the stream to completion — workflow yields output and sets IsTerminated=true
        WorkflowOutputEvent? output = null;
        await foreach (WorkflowEvent evt in run.WatchStreamAsync(blockOnPendingRequest: false).ConfigureAwait(false))
        {
            if (evt is WorkflowOutputEvent o)
            {
                output = o;
            }
        }

        output.Should().NotBeNull("workflow should have completed with output");

        // Act: Send a new message after termination — framework accepts it, but Magentic errors out
        bool accepted = await run.TrySendMessageAsync(new List<ChatMessage> { new(ChatRole.User, "Another message") });
        accepted.Should().BeTrue("framework does not have a terminal state — it always queues messages");

        await run.TrySendMessageAsync(new TurnToken(emitEvents: true));

        // Watch for the error
        WorkflowErrorEvent? errorEvent = null;
        await foreach (WorkflowEvent evt in run.WatchStreamAsync(blockOnPendingRequest: false).ConfigureAwait(false))
        {
            if (evt is WorkflowErrorEvent e)
            {
                errorEvent = e;
            }
        }

        // Assert: Magentic should have rejected the message with an InvalidOperationException
        // (may be wrapped in TargetInvocationException by the framework's reflection-based dispatch)
        errorEvent.Should().NotBeNull("sending a message after termination should produce a WorkflowErrorEvent");
        Exception actual = errorEvent!.Exception is System.Reflection.TargetInvocationException tie && tie.InnerException != null
            ? tie.InnerException
            : errorEvent.Exception!;
        actual.Should().BeOfType<InvalidOperationException>();
        actual.Message.Should().Contain("terminated");
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
