// Copyright (c) Microsoft. All rights reserved.

// This sample demonstrates multi-turn conversation evaluation with different split strategies.

using Azure.AI.Projects;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.AI.Evaluation;
using FoundryEvals = Microsoft.Agents.AI.Foundry.FoundryEvals;

string endpoint = Environment.GetEnvironmentVariable("AZURE_AI_PROJECT_ENDPOINT") ?? throw new InvalidOperationException("AZURE_AI_PROJECT_ENDPOINT is not set.");
string deploymentName = Environment.GetEnvironmentVariable("AZURE_AI_MODEL_DEPLOYMENT_NAME") ?? "gpt-4o-mini";

// WARNING: DefaultAzureCredential is convenient for development but requires careful consideration in production.
// In production, consider using a specific credential (e.g., ManagedIdentityCredential) to avoid
// latency issues, unintended credential probing, and potential security risks from fallback mechanisms.
AIProjectClient projectClient = new(new Uri(endpoint), new DefaultAzureCredential());

// A multi-turn conversation with tool calls to evaluate three ways.
List<ChatMessage> conversation =
[
    // Turn 1: user asks about weather -> agent calls tool -> responds
    new(ChatRole.User, "What's the weather in Seattle?"),
    new(ChatRole.Assistant,
    [
        new FunctionCallContent("c1", "get_weather", new Dictionary<string, object?> { ["location"] = "seattle" }),
    ]),
    new(ChatRole.Tool,
    [
        new FunctionResultContent("c1", "62\u00b0F, cloudy with a chance of rain"),
    ]),
    new(ChatRole.Assistant, "Seattle is 62\u00b0F, cloudy with a chance of rain."),

    // Turn 2: user asks about Paris -> agent calls tool -> responds
    new(ChatRole.User, "And Paris?"),
    new(ChatRole.Assistant,
    [
        new FunctionCallContent("c2", "get_weather", new Dictionary<string, object?> { ["location"] = "paris" }),
    ]),
    new(ChatRole.Tool,
    [
        new FunctionResultContent("c2", "Paris is 68\u00b0F, partly sunny"),
    ]),
    new(ChatRole.Assistant, "Paris is 68\u00b0F, partly sunny."),

    // Turn 3: user asks for comparison -> agent synthesizes without tool
    new(ChatRole.User, "Can you compare them?"),
    new(ChatRole.Assistant,
        "Seattle is cooler at 62\u00b0F with rain likely, while Paris is warmer " +
        "at 68\u00b0F and partly sunny. Paris is the better choice for outdoor activities."),
];

// =========================================================================
// Strategy 1: LastTurn (default)
// "Given all context, was the last response good?"
// =========================================================================
Console.WriteLine(new string('=', 70));
Console.WriteLine("Strategy 1: LastTurn \u2014 evaluate the final response");
Console.WriteLine(new string('=', 70));

EvalItem lastTurnItem = new(
    query: "Can you compare them?",
    response: "Seattle is cooler at 62\u00b0F with rain likely, while Paris is warmer at 68\u00b0F and partly sunny.",
    conversation: conversation);

FoundryEvals lastTurnEvals = new(projectClient, deploymentName, FoundryEvals.Relevance, FoundryEvals.Coherence);
AgentEvaluationResults lastTurnResults = await lastTurnEvals.EvaluateAsync(
    [lastTurnItem],
    "Split Strategy: LastTurn");

PrintResults("LastTurn", lastTurnResults);

// =========================================================================
// Strategy 2: Full
// "Given the original request, did the whole conversation serve the user?"
// =========================================================================
Console.WriteLine(new string('=', 70));
Console.WriteLine("Strategy 2: Full \u2014 evaluate the entire conversation trajectory");
Console.WriteLine(new string('=', 70));

EvalItem fullItem = new(
    query: "What's the weather in Seattle?",
    response: "Seattle is cooler at 62\u00b0F with rain likely, while Paris is warmer at 68\u00b0F and partly sunny.",
    conversation: conversation)
{
    Splitter = ConversationSplitters.Full,
};

FoundryEvals fullEvals = new(projectClient, deploymentName, ConversationSplitters.Full, FoundryEvals.Relevance, FoundryEvals.Coherence);
AgentEvaluationResults fullResults = await fullEvals.EvaluateAsync(
    [fullItem],
    "Split Strategy: Full");

PrintResults("Full", fullResults);

// =========================================================================
// Strategy 3: PerTurnItems
// "Was each individual response appropriate at that point?"
// =========================================================================
Console.WriteLine(new string('=', 70));
Console.WriteLine("Strategy 3: PerTurnItems \u2014 evaluate each turn independently");
Console.WriteLine(new string('=', 70));

IReadOnlyList<EvalItem> perTurnItems = EvalItem.PerTurnItems(conversation);
Console.WriteLine($"Split into {perTurnItems.Count} items from {conversation.Count} messages:");
for (int i = 0; i < perTurnItems.Count; i++)
{
    string response = perTurnItems[i].Response;
    string truncated = response.Length > 60 ? response[..60] + "..." : response;
    Console.WriteLine($"  Turn {i + 1}: query=\"{perTurnItems[i].Query}\", response=\"{truncated}\"");
}

Console.WriteLine();

FoundryEvals perTurnEvals = new(projectClient, deploymentName, FoundryEvals.Relevance, FoundryEvals.Coherence);
AgentEvaluationResults perTurnResults = await perTurnEvals.EvaluateAsync(
    perTurnItems,
    "Split Strategy: Per-Turn");

PrintResults("Per-Turn", perTurnResults);

Console.WriteLine(new string('=', 70));
Console.WriteLine("All strategies complete. Compare results above.");
Console.WriteLine(new string('=', 70));

static void PrintResults(string strategy, AgentEvaluationResults results)
{
    Console.WriteLine($"\n  Result: {results.Passed}/{results.Total} passed");
    if (results.ReportUrl is not null)
    {
        Console.WriteLine($"  Report: {results.ReportUrl}");
    }

    for (int i = 0; i < results.Items.Count; i++)
    {
        foreach (var metric in results.Items[i].Metrics)
        {
            string status = metric.Value.Interpretation?.Failed == true ? "FAIL" : "PASS";
            string score = metric.Value is NumericMetric nm && nm.Value.HasValue
                ? nm.Value.Value.ToString("F1")
                : "N/A";
            Console.WriteLine($"    [{status}] {metric.Key}: {score}");
        }
    }

    Console.WriteLine();
}
