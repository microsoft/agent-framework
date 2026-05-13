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
