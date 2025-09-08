// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Threading.Tasks;
using Microsoft.Agents.Workflows;

namespace WorkflowCheckpointAndResumeSample;

/// <summary>
/// This sample introduces the concepts of check points and shows how to save and restore
/// the state of a workflow using checkpoints.
/// To better understanding how checkpoints work, it's recommended to first understand the
/// concept of super steps. A super step is a logical grouping of steps within a workflow that
/// ...
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
        var checkpointManager = new CheckpointManager();
        var checkpoints = new List<CheckpointInfo>();

        // Execute the workflow
        Checkpointed<StreamingRun> checkpointed = await InProcessExecution
            .StreamAsync(workflow, NumberSignal.Init, checkpointManager)
            .ConfigureAwait(false);
        await foreach (WorkflowEvent evt in checkpointed.Run.WatchStreamAsync().ConfigureAwait(false))
        {
            if (evt is SuperStepCompletedEvent superStepCompletedEvt)
            {
                // Checkpoints are automatically created at the end of each super step.
                // You can store the checkpoint info for later use.
                CheckpointInfo? checkpoint = superStepCompletedEvt.CompletionInfo!.Checkpoint;
                if (checkpoint != null)
                {
                    checkpoints.Add(checkpoint);
                    Console.WriteLine($"Checkpoint created at step {checkpoints.Count}.");
                }
            }
        }

        Console.WriteLine("Number of checkpoints created: " + checkpoints.Count);
    }
}