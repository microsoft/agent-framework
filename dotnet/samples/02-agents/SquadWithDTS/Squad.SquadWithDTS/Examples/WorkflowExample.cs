// Copyright (c) Microsoft. All rights reserved.
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Workflows;
using Squad.SquadWithDTS.Infrastructure;
using Squad.SquadWithDTS.Models;

namespace Squad.SquadWithDTS.Examples;

/// <summary>
/// Sequential MAF workflow example: Writer (LLM) → Squad (governance).
///
/// Shows a two-executor <see cref="Workflow"/> without DTS — runs in-process
/// using the built-in in-memory workflow engine.
/// </summary>
internal static class WorkflowExample
{
    public static async Task RunAsync(
        ProviderAgentFactory provider,
        AIAgent squad,
        CancellationToken cancellationToken = default)
    {
        Console.WriteLine();
        Console.WriteLine("── Sequential Workflow example ─────────────────────────────");
        Console.WriteLine("  Flow: Writer → Squad (in-process, no DTS)");
        Console.WriteLine();

        // ── Writer executor ─────────────────────────────────────────────
        var writerExecutor = new LambdaExecutor<string, string>(
            "Writer",
            async (input, _, ct) =>
            {
                if (!provider.Summary.IsProviderBacked)
                {
                    await Task.Yield();
                    return "Proposed change: Add a new `OnPermissionRequest` hook to " +
                           "MAF `AIAgent` that fires before any tool call, allowing " +
                           "governance policies to approve or deny at the framework level.";
                }

                var (agent, scope) = provider.CreateAgent("writer", "Technical writer agent");
                await using (scope)
                {
                    return await DemoRuntime.RunAgentAsync(agent,
                        $"Write a one-paragraph technical proposal for: {input}", ct);
                }
            });

        // ── Squad executor ───────────────────────────────────────────────
        var squadExecutor = new LambdaExecutor<string, string>(
            "Squad",
            async (input, _, ct) =>
            {
                var sb = new System.Text.StringBuilder();
                await foreach (var chunk in squad.RunAsync(
                    $"Review this technical proposal from a governance perspective:\n\n{input}",
                    cancellationToken: ct))
                {
                    sb.Append(chunk);
                }
                return sb.ToString().Trim();
            });

        var writerBinding = writerExecutor.BindExecutor();
        var squadBinding  = squadExecutor.BindExecutor();

        var workflow = new WorkflowBuilder(writerBinding)
            .WithName("writer-squad-review")
            .AddEdge(writerBinding, squadBinding)
            .WithOutputFrom(squadBinding)
            .Build();

        var client = workflow.CreateInProcessClient();
        var run = (IAwaitableWorkflowRun)await client.RunAsync(
            workflow,
            "Add governance hooks to Microsoft Agent Framework",
            cancellationToken: cancellationToken);

        var result = await run.WaitForCompletionAsync<string>(cancellationToken);

        Console.WriteLine("[Squad review]");
        Console.WriteLine(result);
        Console.WriteLine();
        Console.WriteLine("── Sequential Workflow example complete ────────────────────");
    }

    // ── helpers ─────────────────────────────────────────────────────────

    private sealed class LambdaExecutor<TIn, TOut>(
        string name,
        Func<TIn, IWorkflowContext, CancellationToken, Task<TOut>> handler)
        : Executor<TIn, TOut>(name)
    {
        public override async ValueTask<TOut> HandleAsync(
            TIn input,
            IWorkflowContext context,
            CancellationToken cancellationToken = default)
            => await handler(input, context, cancellationToken);
    }
}
