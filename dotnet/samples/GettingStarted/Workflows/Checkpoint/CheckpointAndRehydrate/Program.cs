// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.Workflows;

namespace WorkflowCheckpointAndRehydrateSample;

/// <summary>
/// This sample introduces the concepts of check points and shows how to save and restore
/// the state of a workflow using checkpoints.
/// This sample demonstrates checkpoints, which allow you to save and restore a workflow's state.
/// Key concepts:
/// - Super Steps: A workflow executes in stages called "super steps". Each super step runs
///   one or more executors and completes when all those executors finish their work.
/// - Checkpoints: The system automatically saves the workflow's state at the end of each
///   super step. You can use these checkpoints to resume the workflow from any saved point.
/// - Rehydration: You can rehydrate a new workflow instance from a saved checkpoint, allowing
///   you to continue execution from that point.
/// </summary>
/// <remarks>
/// Pre-requisites:
/// - Foundational samples should be completed first.
/// </remarks>
public static class Program
{
    private static async Task Main()
    {
        // Create the workflow
        var workflow = WorkflowHelper.GetWorkflow();

        // Create checkpoint manager
        var checkpointManager = CheckpointManager.Default;
        var checkpoints = new List<CheckpointInfo>();

        // Execute the workflow and save checkpoints
        Checkpointed<StreamingRun> checkpointedRun = await InProcessExecution
            .StreamAsync(workflow, NumberSignal.Init, checkpointManager)
            .ConfigureAwait(false);
        await foreach (WorkflowEvent evt in checkpointedRun.Run.WatchStreamAsync().ConfigureAwait(false))
        {
            if (evt is ExecutorCompletedEvent executorCompletedEvt)
            {
                Console.WriteLine($"* Executor {executorCompletedEvt.ExecutorId} completed.");
            }

            if (evt is SuperStepCompletedEvent superStepCompletedEvt)
            {
                // Checkpoints are automatically created at the end of each super step when a
                // checkpoint manager is provided. You can store the checkpoint info for later use.
                CheckpointInfo? checkpoint = superStepCompletedEvt.CompletionInfo!.Checkpoint;
                if (checkpoint is not null)
                {
                    checkpoints.Add(checkpoint);
                    Console.WriteLine($"** Checkpoint created at step {checkpoints.Count}.");
                }
            }

            if (evt is WorkflowCompletedEvent workflowCompletedEvt)
            {
                Console.WriteLine($"Workflow completed with result: {workflowCompletedEvt.Data}");
            }
        }

        if (checkpoints.Count == 0)
        {
            throw new InvalidOperationException("No checkpoints were created during the workflow execution.");
        }
        Console.WriteLine($"Number of checkpoints created: {checkpoints.Count}");

        // Rehydrate a new workflow instance from a saved checkpoint and continue execution
        var newWorkflow = WorkflowHelper.GetWorkflow();
        const int CheckpointIndex = 5;
        Console.WriteLine($"\n\nHydrating a new workflow instance from the {CheckpointIndex + 1}th checkpoint.");
        CheckpointInfo savedCheckpoint = checkpoints[CheckpointIndex];

        Checkpointed<StreamingRun> newCheckpointedRun = await InProcessExecution
            .StreamAsync(newWorkflow, NumberSignal.Init, checkpointManager)
            .ConfigureAwait(false);
        await newCheckpointedRun.RestoreCheckpointAsync(savedCheckpoint, CancellationToken.None).ConfigureAwait(false);
        await foreach (WorkflowEvent evt in newCheckpointedRun.Run.WatchStreamAsync().ConfigureAwait(false))
        {
            if (evt is ExecutorCompletedEvent executorCompletedEvt)
            {
                Console.WriteLine($"* Executor {executorCompletedEvt.ExecutorId} completed.");
            }

            if (evt is WorkflowCompletedEvent workflowCompletedEvt)
            {
                Console.WriteLine($"Workflow completed with result: {workflowCompletedEvt.Data}");
            }
        }
    }
}
