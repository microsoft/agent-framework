// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.Postgres;
using Microsoft.Agents.AI.Workflows;
using Npgsql;

namespace PostgresCheckpointing;

/// <summary>
/// Persists an approval workflow and resumes it from a later process.
/// </summary>
internal static class Program
{
    private static async Task Main(string[] args)
    {
        if (args.Length is < 2 or > 3 || args[0] is not ("start" or "resume") ||
            (args[0] == "resume" && (args.Length != 3 || args[2] is not ("approve" or "reject"))))
        {
            throw new ArgumentException("Usage: start <run-id> | resume <run-id> <approve|reject>");
        }

        var connectionString = Environment.GetEnvironmentVariable("POSTGRES_CONNECTION_STRING")
            ?? throw new InvalidOperationException("Set POSTGRES_CONNECTION_STRING to a PostgreSQL connection string.");
        var tenantId = Environment.GetEnvironmentVariable("POSTGRES_TENANT_ID")
            ?? throw new InvalidOperationException("Set POSTGRES_TENANT_ID to the authorized tenant identifier.");
        var applicationId = Environment.GetEnvironmentVariable("POSTGRES_APPLICATION_ID") ?? "checkpoint-sample";
        var schema = Environment.GetEnvironmentVariable("POSTGRES_SCHEMA") ?? "public";

        await using var dataSource = NpgsqlDataSource.Create(connectionString);
        var store = new PostgresCheckpointStore(dataSource, applicationId, tenantId, schema);
        await store.EnsureTableAsync();
        var manager = store.CreateCheckpointManager();
        var latest = await manager.GetLatestCheckpointAsync(args[1]);
        var resume = args[0] == "resume";
        if (!resume && latest is not null)
        {
            throw new InvalidOperationException("This run already has checkpoints. Resume it or choose a new run ID.");
        }

        if (resume && latest is null)
        {
            throw new InvalidOperationException("No checkpoint exists for this application, tenant, and run.");
        }

        var workflow = CreateWorkflow();
        await using StreamingRun run = resume
            ? await InProcessExecution.ResumeStreamingAsync(workflow, latest!, manager)
            : await InProcessExecution.RunStreamingAsync(workflow, "PO-1042", manager, sessionId: args[1]);

        var requested = false;
        await foreach (WorkflowEvent workflowEvent in run.WatchStreamAsync())
        {
            switch (workflowEvent)
            {
                case RequestInfoEvent requestEvent:
                    requested = true;
                    Console.WriteLine("Waiting for order approval.");
                    if (resume)
                    {
                        await run.SendResponseAsync(requestEvent.Request.CreateResponse(args[2] == "approve"));
                    }

                    break;
                case SuperStepCompletedEvent step when !resume && requested && step.CompletionInfo?.Checkpoint is not null:
                    Console.WriteLine($"Checkpoint saved: {step.CompletionInfo.Checkpoint.CheckpointId}");
                    return;
                case WorkflowOutputEvent output:
                    Console.WriteLine(output.Data);
                    break;
                case WorkflowErrorEvent error:
                    throw new InvalidOperationException("Workflow execution failed.", error.Exception);
            }
        }

        if (!requested)
        {
            throw new InvalidOperationException("This checkpoint has no pending approval.");
        }
    }

    private static Workflow CreateWorkflow()
    {
        var prepare = new PrepareOrder();
        var approval = RequestPort.Create<string, bool>("approval");
        var decision = new RecordDecision();
        return new WorkflowBuilder(prepare)
            .AddEdge(prepare, approval)
            .AddEdge(approval, decision)
            .WithOutputFrom(decision)
            .Build();
    }

    private sealed class PrepareOrder() : Executor<string, string>("prepare")
    {
        public override ValueTask<string> HandleAsync(string message, IWorkflowContext context, CancellationToken cancellationToken = default)
        {
            Console.WriteLine($"Prepared order: {message}");
            return ValueTask.FromResult(message);
        }
    }

    private sealed class RecordDecision() : Executor<bool, string>("decision")
    {
        public override ValueTask<string> HandleAsync(bool message, IWorkflowContext context, CancellationToken cancellationToken = default)
        {
            return ValueTask.FromResult(message ? "Approved order." : "Rejected order.");
        }
    }
}
