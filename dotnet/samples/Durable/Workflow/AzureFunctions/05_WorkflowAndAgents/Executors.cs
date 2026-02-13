// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.Workflows;

namespace WorkflowAndAgentsFunctionApp;

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
        Console.WriteLine($"[ParseQuestion] Preparing question: \"{message}\"");

        string formattedQuestion = message.Trim();
        if (!formattedQuestion.EndsWith('?'))
        {
            formattedQuestion += "?";
        }

        return ValueTask.FromResult(formattedQuestion);
    }
}

/// <summary>
/// Aggregates responses from multiple AI agents into a unified response.
/// </summary>
internal sealed class ResponseAggregatorExecutor() : Executor<string[], string>("ResponseAggregator")
{
    public override ValueTask<string> HandleAsync(
        string[] message,
        IWorkflowContext context,
        CancellationToken cancellationToken = default)
    {
        Console.WriteLine($"[Aggregator] Received {message.Length} AI agent responses, combining...");

        string aggregatedResult = "AI EXPERT PANEL RESPONSES\n" +
                                  "═════════════════════════\n\n";

        for (int i = 0; i < message.Length; i++)
        {
            string expertLabel = i == 0 ? "PHYSICIST" : "CHEMIST";
            aggregatedResult += $"{expertLabel}:\n{message[i]}\n\n";
        }

        aggregatedResult += $"Summary: Received perspectives from {message.Length} AI experts.";

        return ValueTask.FromResult(aggregatedResult);
    }
}
