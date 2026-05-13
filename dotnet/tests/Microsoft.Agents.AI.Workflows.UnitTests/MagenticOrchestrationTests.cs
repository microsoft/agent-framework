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
