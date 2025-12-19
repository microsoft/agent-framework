// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json;
using Microsoft.Agents.AI.Workflows;

namespace CheckpointWithRedis;

/// <summary>
/// This sample demonstrates how to use Redis-backed checkpoint storage for workflows.
/// Key concepts:
/// - RedisCheckpointStore: A distributed, durable checkpoint store using Redis
/// - TTL (Time-To-Live): Automatic expiration of checkpoints
/// - Parent-child relationships: Linking checkpoints to track workflow history
/// </summary>
/// <remarks>
/// Pre-requisites:
/// - Redis must be running. Start it with: docker run --name redis -p 6379:6379 -d redis:7-alpine
/// - Or set REDIS_CONNECTION_STRING environment variable to your Redis instance.
/// </remarks>
public static class Program
{
    public static async Task<int> Main()
    {
        // Configuration
        var redisConnectionString = Environment.GetEnvironmentVariable("REDIS_CONNECTION_STRING") ?? "localhost:6379";
        var ttl = TimeSpan.FromHours(24);

        Console.WriteLine("=== Redis Checkpoint Storage Demo ===\n");
        Console.WriteLine($"Connecting to Redis: {redisConnectionString}");

        try
        {
            // Create checkpoint store with TTL
            using var checkpointStore = RedisWorkflowExtensions.CreateRedisCheckpointStoreWithTtl(
                redisConnectionString,
                ttl,
                keyPrefix: "workflow_checkpoints");

            Console.WriteLine($"Key prefix: {checkpointStore.KeyPrefix}");
            Console.WriteLine($"TTL: {checkpointStore.TimeToLive}\n");

            // Sample workflow data
            var runId = $"run_{Guid.NewGuid():N}";
            var workflowState = new WorkflowState
            {
                CurrentStep = "initialize",
                Variables = new Dictionary<string, object>
                {
                    ["user_input"] = "Hello, Agent!",
                    ["timestamp"] = DateTimeOffset.UtcNow.ToString("o")
                }
            };

            // Create initial checkpoint
            Console.WriteLine("--- Creating Initial Checkpoint ---");
            var initialCheckpoint = await checkpointStore.CreateCheckpointAsync(
                runId,
                JsonSerializer.SerializeToElement(workflowState));

            Console.WriteLine($"Run ID: {runId}");
            Console.WriteLine($"Checkpoint ID: {initialCheckpoint.CheckpointId}");
            Console.WriteLine($"State: {workflowState.CurrentStep}\n");

            // Simulate workflow progress
            workflowState.CurrentStep = "processing";
            workflowState.Variables["processed"] = true;
            workflowState.Variables["processing_time"] = DateTimeOffset.UtcNow.ToString("o");

            // Create child checkpoint (linked to parent)
            Console.WriteLine("--- Creating Child Checkpoint ---");
            var processingCheckpoint = await checkpointStore.CreateCheckpointAsync(
                runId,
                JsonSerializer.SerializeToElement(workflowState),
                parent: initialCheckpoint);

            Console.WriteLine($"Checkpoint ID: {processingCheckpoint.CheckpointId}");
            Console.WriteLine($"Parent ID: {initialCheckpoint.CheckpointId}");
            Console.WriteLine($"State: {workflowState.CurrentStep}\n");

            // Simulate more progress
            workflowState.CurrentStep = "completed";
            workflowState.Variables["result"] = "Success!";
            workflowState.Variables["completion_time"] = DateTimeOffset.UtcNow.ToString("o");

            // Create final checkpoint
            Console.WriteLine("--- Creating Final Checkpoint ---");
            var finalCheckpoint = await checkpointStore.CreateCheckpointAsync(
                runId,
                JsonSerializer.SerializeToElement(workflowState),
                parent: processingCheckpoint);

            Console.WriteLine($"Checkpoint ID: {finalCheckpoint.CheckpointId}");
            Console.WriteLine($"State: {workflowState.CurrentStep}\n");

            // List all checkpoints for the run
            Console.WriteLine("--- All Checkpoints for Run ---");
            var allCheckpoints = await checkpointStore.RetrieveIndexAsync(runId);
            var checkpointList = allCheckpoints.ToList();
            Console.WriteLine($"Total checkpoints: {checkpointList.Count}");
            foreach (var cp in checkpointList)
            {
                Console.WriteLine($"  - {cp.CheckpointId}");
            }

            Console.WriteLine();

            // List children of the initial checkpoint
            Console.WriteLine("--- Children of Initial Checkpoint ---");
            var children = await checkpointStore.RetrieveIndexAsync(runId, initialCheckpoint);
            var childList = children.ToList();
            Console.WriteLine($"Child checkpoints: {childList.Count}");
            foreach (var child in childList)
            {
                Console.WriteLine($"  - {child.CheckpointId}");
            }

            Console.WriteLine();

            // Retrieve and display checkpoint data
            Console.WriteLine("--- Retrieving Final Checkpoint Data ---");
            var retrievedData = await checkpointStore.RetrieveCheckpointAsync(runId, finalCheckpoint);
            Console.WriteLine($"Current step: {retrievedData.GetProperty("CurrentStep").GetString()}");

            var variables = retrievedData.GetProperty("Variables");
            Console.WriteLine($"User input: {variables.GetProperty("user_input").GetString()}");
            Console.WriteLine($"Result: {variables.GetProperty("result").GetString()}");
            Console.WriteLine($"Processed: {variables.GetProperty("processed").GetBoolean()}");

            Console.WriteLine("\n=== Demo Complete ===");
        }
        catch (Exception ex)
        {
            Console.WriteLine($"\nError: {ex.Message}");
            Console.WriteLine("\nMake sure Redis is running. You can start it with:");
            Console.WriteLine("  docker run --name redis -p 6379:6379 -d redis:7-alpine");
            return 1;
        }

        return 0;
    }
}

/// <summary>
/// Sample workflow state class.
/// </summary>
public class WorkflowState
{
    public string CurrentStep { get; set; } = string.Empty;
    public Dictionary<string, object> Variables { get; set; } = new();
}
