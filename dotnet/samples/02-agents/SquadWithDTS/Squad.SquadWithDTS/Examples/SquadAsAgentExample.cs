// Copyright (c) Microsoft. All rights reserved.
using Microsoft.Agents.AI;
using Squad.SquadWithDTS.Infrastructure;

namespace Squad.SquadWithDTS.Examples;

/// <summary>
/// Simplest possible example: <see cref="Agents.SquadAgent"/> as a plain MAF
/// participant in a three-agent flow.
///
/// Planner (LLM) → Squad (governance) → Reviewer (LLM)
///
/// Shows that <c>SquadAgent</c> is a drop-in MAF <see cref="AIAgent"/> — it
/// can participate in any chain or graph without DTS.
/// </summary>
internal static class SquadAsAgentExample
{
    public static async Task RunAsync(
        ProviderAgentFactory provider,
        AIAgent squad,
        CancellationToken cancellationToken = default)
    {
        Console.WriteLine();
        Console.WriteLine("── Squad-as-Agent example ──────────────────────────────────");
        Console.WriteLine("  Flow: Planner → Squad → Reviewer");
        Console.WriteLine();

        // Step 1: Planner produces a task specification
        const string plannerPrompt =
            """
            You are a task-planning agent. Create a concise technical task specification
            (3–5 bullet points) for: "Add OpenTelemetry tracing to an existing .NET 9
            MAF agent that wraps GitHub Copilot Squad."
            """;

        string plannerOutput;
        if (provider.Summary.IsProviderBacked)
        {
            var (planner, plannerScope) = provider.CreateAgent("planner", "Task planning agent");
            await using (plannerScope)
            {
                plannerOutput = await DemoRuntime.RunAgentAsync(planner, plannerPrompt, cancellationToken);
            }
        }
        else
        {
            plannerOutput =
                "• Add ActivitySource 'Squad.AgentFramework.SquadAgent'\n" +
                "• Wrap RunAsync in a StartActivity span\n" +
                "• Record run_duration_ms histogram\n" +
                "• Register ActivitySource with OTel SDK in Program.cs\n" +
                "• Export via OTLP to Aspire dashboard";
        }

        Console.WriteLine("[Planner output]");
        Console.WriteLine(plannerOutput);
        Console.WriteLine();

        // Step 2: Squad reviews and applies governance
        var squadPrompt = $"""
            Review the following technical task specification and confirm it follows
            good observability practice. Flag any missing items.

            Specification:
            {plannerOutput}
            """;

        Console.WriteLine("[Squad output]");
        await foreach (var chunk in squad.RunAsync(squadPrompt, cancellationToken: cancellationToken))
        {
            Console.Write(chunk);
        }
        Console.WriteLine();
        Console.WriteLine();

        // Step 3: Reviewer summarises
        Console.WriteLine("[Reviewer output]");
        if (provider.Summary.IsProviderBacked)
        {
            var (reviewer, reviewerScope) = provider.CreateAgent("reviewer", "Code review agent");
            await using (reviewerScope)
            {
                var reviewPrompt = $"Summarise the Squad-reviewed task in one sentence suitable for a commit message.";
                var summary = await DemoRuntime.RunAgentAsync(reviewer, reviewPrompt, cancellationToken);
                Console.WriteLine(summary);
            }
        }
        else
        {
            Console.WriteLine("feat(otel): wrap SquadAgent with ActivitySource, Meter, and OTLP exporter");
        }

        Console.WriteLine();
        Console.WriteLine("── Squad-as-Agent example complete ─────────────────────────");
    }
}
