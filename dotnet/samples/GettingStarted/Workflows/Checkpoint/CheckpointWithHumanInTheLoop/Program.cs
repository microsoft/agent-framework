// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.Workflows;

namespace WorkflowCheckpointWithHumanInTheLoopSample;

/// <summary>
/// This sample demonstrates how to create a workflow with human-in-the-loop interaction and
/// checkpointing support. The workflow plays a number guessing game where the user provides
/// guesses based on feedback from the workflow. The workflow state is checkpointed at the end
/// of each super step, allowing it to be restored and resumed later.
/// Each InputPort request and response cycle takes two super steps:
/// 1. The InputPort sends a RequestInfoEvent to request input from the external world.
/// 2. The external world sends a response back to the InputPort.
/// Thus, two checkpoints are created for each human-in-the-loop interaction.
/// </summary>
/// <remarks>
/// Pre-requisites:
/// - Foundational samples should be completed first.
/// - This sample builds upon the HumanInTheLoopBasic sample. It's recommended to go through that
///   sample first to understand the basics of human-in-the-loop workflows.
/// - This sample also builds upon the CheckpointAndResume sample. It's recommended to
///   go through that sample first to understand the basics of checkpointing and resuming workflows.
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
            .StreamAsync(workflow, new SignalWithNumber(NumberSignal.Init), checkpointManager)
            .ConfigureAwait(false);
        await foreach (WorkflowEvent evt in checkpointedRun.Run.WatchStreamAsync().ConfigureAwait(false))
        {
            switch (evt)
            {
                case RequestInfoEvent requestInputEvt:
                    // Handle `RequestInfoEvent` from the workflow
                    ExternalResponse response = HandleExternalRequest(requestInputEvt.Request);
                    await checkpointedRun.Run.SendResponseAsync(response).ConfigureAwait(false);
                    break;
                case ExecutorCompletedEvent executorCompletedEvt:
                    Console.WriteLine($"* Executor {executorCompletedEvt.ExecutorId} completed.");
                    break;
                case SuperStepCompletedEvent superStepCompletedEvt:
                    // Checkpoints are automatically created at the end of each super step when a
                    // checkpoint manager is provided. You can store the checkpoint info for later use.
                    CheckpointInfo? checkpoint = superStepCompletedEvt.CompletionInfo!.Checkpoint;
                    if (checkpoint is not null)
                    {
                        checkpoints.Add(checkpoint);
                        Console.WriteLine($"** Checkpoint created at step {checkpoints.Count}.");
                    }
                    break;
                case WorkflowCompletedEvent workflowCompletedEvt:
                    Console.WriteLine($"Workflow completed with result: {workflowCompletedEvt.Data}");
                    break;
            }
        }

        if (checkpoints.Count == 0)
        {
            throw new InvalidOperationException("No checkpoints were created during the workflow execution.");
        }
        Console.WriteLine($"Number of checkpoints created: {checkpoints.Count}");

        // Restoring from a checkpoint and resuming execution
        const int CheckpointIndex = 1;
        Console.WriteLine($"\n\nRestoring from the {CheckpointIndex + 1}th checkpoint.");
        CheckpointInfo savedCheckpoint = checkpoints[CheckpointIndex];
        // Note that we are restoring the state directly to the same run instance.
        await checkpointedRun.RestoreCheckpointAsync(savedCheckpoint, CancellationToken.None).ConfigureAwait(false);
        await foreach (WorkflowEvent evt in checkpointedRun.Run.WatchStreamAsync().ConfigureAwait(false))
        {
            switch (evt)
            {
                case RequestInfoEvent requestInputEvt:
                    // Handle `RequestInfoEvent` from the workflow
                    ExternalResponse response = HandleExternalRequest(requestInputEvt.Request);
                    await checkpointedRun.Run.SendResponseAsync(response).ConfigureAwait(false);
                    break;
                case ExecutorCompletedEvent executorCompletedEvt:
                    Console.WriteLine($"* Executor {executorCompletedEvt.ExecutorId} completed.");
                    break;
                case WorkflowCompletedEvent workflowCompletedEvt:
                    Console.WriteLine($"Workflow completed with result: {workflowCompletedEvt.Data}");
                    break;
            }
        }
    }

    private static ExternalResponse HandleExternalRequest(ExternalRequest request)
    {
        var signal = request.DataAs<SignalWithNumber>();
        if (signal is not null)
        {
            switch (signal.Signal)
            {
                case NumberSignal.Init:
                    int initialGuess = ReadIntegerFromConsole("Please provide your initial guess: ");
                    return request.CreateResponse(initialGuess);
                case NumberSignal.Above:
                    int lowerGuess = ReadIntegerFromConsole($"You previously guessed {signal.Number} too large. Please provide a new guess: ");
                    return request.CreateResponse(lowerGuess);
                case NumberSignal.Below:
                    int higherGuess = ReadIntegerFromConsole($"You previously guessed {signal.Number} too small. Please provide a new guess: ");
                    return request.CreateResponse(higherGuess);
            }
        }

        throw new NotSupportedException($"Request {request.PortInfo.RequestType} is not supported");
    }

    private static int ReadIntegerFromConsole(string prompt)
    {
        while (true)
        {
            Console.Write(prompt);
            string? input = Console.ReadLine();
            if (int.TryParse(input, out int value))
            {
                return value;
            }
            Console.WriteLine("Invalid input. Please enter a valid integer.");
        }
    }
}
