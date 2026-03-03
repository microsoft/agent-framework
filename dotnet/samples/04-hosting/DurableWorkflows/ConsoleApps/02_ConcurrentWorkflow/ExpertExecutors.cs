// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.Workflows;

namespace WorkflowConcurrency;

/// <summary>
/// Parses and validates the incoming question before sending to AI agents.
/// </summary>
internal sealed class ParseQuestionExecutor() : Executor<string, string>("ParseQuestion")
{
    public override ValueTask<string> HandleAsync(
        string message,
        IWorkflowContext context,
        CancellationToken cancellationToken = default)
    {
        Console.WriteLine();
        Console.ForegroundColor = ConsoleColor.Magenta;
        Console.WriteLine("┌─────────────────────────────────────────────────────────────────┐");
        Console.WriteLine("│ [ParseQuestion] Preparing question for AI agents...");

        string formattedQuestion = message.Trim();
        if (!formattedQuestion.EndsWith('?'))
        {
            formattedQuestion += "?";
        }

        Console.WriteLine($"│ [ParseQuestion] Question: \"{formattedQuestion}\"");
        Console.WriteLine("│ [ParseQuestion] → Sending to Physicist and Chemist in PARALLEL...");
        Console.WriteLine("└─────────────────────────────────────────────────────────────────┘");
        Console.ResetColor();

        return ValueTask.FromResult(formattedQuestion);
    }
}

/// <summary>
/// Aggregates responses from all AI agents into a comprehensive answer.
/// This is the Fan-in point where parallel results are collected.
/// </summary>
internal sealed class AggregatorExecutor() : Executor<string[], string>("Aggregator")
{
    public override ValueTask<string> HandleAsync(
        string[] message,
        IWorkflowContext context,
        CancellationToken cancellationToken = default)
    {
        Console.WriteLine();
        Console.ForegroundColor = ConsoleColor.Cyan;
        Console.WriteLine("┌─────────────────────────────────────────────────────────────────┐");
        Console.WriteLine($"│ [Aggregator] 📋 Received {message.Length} AI agent responses");
        Console.WriteLine("│ [Aggregator] Combining into comprehensive answer...");
        Console.WriteLine("│ [Aggregator] ✓ Aggregation complete!");
        Console.WriteLine("└─────────────────────────────────────────────────────────────────┘");
        Console.ResetColor();

        string aggregatedResult = "═══════════════════════════════════════════════════════════════\n" +
                                 "                    AI EXPERT PANEL RESPONSES\n" +
                                 "═══════════════════════════════════════════════════════════════\n\n";

        for (int i = 0; i < message.Length; i++)
        {
            string expertLabel = i == 0 ? "⚛️ PHYSICIST" : "🧪 CHEMIST";
            aggregatedResult += $"{expertLabel}:\n{message[i]}\n\n";
        }

        aggregatedResult += "═══════════════════════════════════════════════════════════════\n" +
                          $"Summary: Received perspectives from {message.Length} AI experts.\n" +
                          "═══════════════════════════════════════════════════════════════";

        return ValueTask.FromResult(aggregatedResult);
    }
}
