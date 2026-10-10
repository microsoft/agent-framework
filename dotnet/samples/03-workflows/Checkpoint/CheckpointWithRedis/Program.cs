// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.Workflows;
using Microsoft.Agents.AI.Workflows.Checkpointing;
using Microsoft.Agents.AI.Workflows.InProc;
using StackExchange.Redis;

namespace WorkflowCheckpointWithRedisSample;

/// <summary>
/// This sample shows how to store workflow checkpoints in Redis with <see cref="RedisCheckpointStore"/>,
/// so that a workflow can be resumed by another process, container or machine.
/// Key concepts:
/// - The store keeps the checkpoints of each session in Redis, in the order they were committed.
/// - Any process that connects to the same Redis server can find the latest checkpoint of a session
///   and resume the workflow from it.
/// - An optional time to live removes the checkpoints of a session some time after its last checkpoint.
/// - The first run uses lockstep execution, so it can be stopped exactly after a given super step.
/// </summary>
/// <remarks>
/// Pre-requisites:
/// - Foundational samples should be completed first.
/// - A Redis server, for example: docker run -d -p 6379:6379 redis:7-alpine
/// - Optionally set REDIS_CONNECTION_STRING (defaults to localhost:6379).
/// </remarks>
public static class Program
{
    private static async Task Main()
    {
        string connectionString = Environment.GetEnvironmentVariable("REDIS_CONNECTION_STRING") ?? "localhost:6379";
        string sessionId = $"guess-number-{Guid.NewGuid():N}";

        // <run_with_redis_checkpoints>
        // The application owns the connection; share one ConnectionMultiplexer per application.
        await using ConnectionMultiplexer redis = await ConnectionMultiplexer.ConnectAsync(connectionString);

        RedisCheckpointStoreOptions options = new()
        {
            KeyPrefix = "samples:checkpoints",
            TimeToLive = TimeSpan.FromHours(1),
        };
        CheckpointManager checkpointManager = CheckpointManager.CreateJson(new RedisCheckpointStore(redis, options));

        // In lockstep mode the next super step only runs when the event stream is read further, so stopping
        // the stream after the fourth checkpoint stops the workflow exactly there, as if the process had crashed.
        const int StopAfterCheckpoints = 4;
        List<CheckpointInfo> checkpoints = [];
        InProcessExecutionEnvironment lockstep = InProcessExecution.Lockstep.WithCheckpointing(checkpointManager);
        Workflow workflow = WorkflowFactory.BuildWorkflow();
        await using (StreamingRun run = await lockstep.RunStreamingAsync(workflow, NumberSignal.Init, sessionId))
        {
            await foreach (WorkflowEvent evt in run.WatchStreamAsync())
            {
                if (evt is SuperStepCompletedEvent { CompletionInfo.Checkpoint: CheckpointInfo checkpoint })
                {
                    checkpoints.Add(checkpoint);
                    if (checkpoints.Count == StopAfterCheckpoints)
                    {
                        Console.WriteLine($"Stopping the first run after {checkpoints.Count} checkpoints.");
                        break;
                    }
                }
            }
        }
        // </run_with_redis_checkpoints>

        // <resume_from_redis>
        // Later, possibly in another process: create a new store and workflow, find the latest
        // checkpoint of the session in Redis and resume the workflow from it.
        CheckpointManager resumeManager = CheckpointManager.CreateJson(new RedisCheckpointStore(redis, options));
        CheckpointInfo latest = await resumeManager.GetLatestCheckpointAsync(sessionId)
            ?? throw new InvalidOperationException($"No checkpoint found for session '{sessionId}'.");
        if (!latest.Equals(checkpoints[^1]))
        {
            throw new InvalidOperationException("The latest checkpoint in Redis is not the last checkpoint of the first run.");
        }

        Console.WriteLine($"Resuming from checkpoint {checkpoints.Count}, the latest checkpoint of the session in Redis.");

        Workflow resumedWorkflow = WorkflowFactory.BuildWorkflow();
        await using StreamingRun resumedRun = await InProcessExecution.ResumeStreamingAsync(resumedWorkflow, latest, resumeManager);
        // </resume_from_redis>

        await foreach (WorkflowEvent evt in resumedRun.WatchStreamAsync())
        {
            switch (evt)
            {
                case ExecutorCompletedEvent executorCompleted:
                    Console.WriteLine($"* Executor {executorCompleted.ExecutorId} completed.");
                    break;

                case WorkflowOutputEvent output:
                    Console.WriteLine($"Workflow completed with result: {output.Data}");
                    break;

                case WorkflowErrorEvent workflowError:
                    Console.ForegroundColor = ConsoleColor.Red;
                    Console.Error.WriteLine(workflowError.Exception?.ToString() ?? "Unknown workflow error occurred.");
                    Console.ResetColor();
                    break;
            }
        }
    }
}
