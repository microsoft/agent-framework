// Copyright (c) Microsoft. All rights reserved.

// This sample demonstrates combining local evaluators and Foundry evaluators.

using Azure.AI.Projects;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI.Evaluation;
using FoundryEvals = Microsoft.Agents.AI.Foundry.FoundryEvals;

string endpoint = Environment.GetEnvironmentVariable("AZURE_AI_PROJECT_ENDPOINT") ?? throw new InvalidOperationException("AZURE_AI_PROJECT_ENDPOINT is not set.");
string deploymentName = Environment.GetEnvironmentVariable("AZURE_AI_MODEL_DEPLOYMENT_NAME") ?? "gpt-4o-mini";

// WARNING: DefaultAzureCredential is convenient for development but requires careful consideration in production.
// In production, consider using a specific credential (e.g., ManagedIdentityCredential) to avoid
// latency issues, unintended credential probing, and potential security risks from fallback mechanisms.
AIProjectClient projectClient = new(new Uri(endpoint), new DefaultAzureCredential());

AIAgent agent = projectClient.AsAIAgent(
    model: deploymentName,
    instructions: "You are a travel advisor. Provide helpful travel recommendations.",
    name: "TravelAdvisor");

string[] queries = ["What are the best places to visit in Japan?", "Suggest a 3-day itinerary for Paris."];

// --- Pattern 1: Local-only evaluation ---
EvalCheck isHelpful = FunctionEvaluator.Create("is_helpful", (string response) => response.Length > 20);
EvalCheck keywordCheck = EvalChecks.KeywordCheck("visit");
LocalEvaluator localEvaluator = new(isHelpful, keywordCheck);

AgentEvaluationResults localResults = await agent.EvaluateAsync(queries, localEvaluator);

Console.WriteLine("=== Pattern 1: Local-only ===");
Console.WriteLine($"  {localResults.ProviderName}: {localResults.Passed}/{localResults.Total} passed");
Console.WriteLine();

// --- Pattern 2: Foundry-only ---
FoundryEvals foundryEvaluator = new(projectClient, deploymentName, FoundryEvals.Relevance);

AgentEvaluationResults foundryResults = await agent.EvaluateAsync(queries, foundryEvaluator);

Console.WriteLine("=== Pattern 2: Foundry-only ===");
Console.WriteLine($"  {foundryResults.ProviderName}: {foundryResults.Passed}/{foundryResults.Total} passed");
Console.WriteLine();

// --- Pattern 3: Mixed -- combine local + foundry in one call ---
IReadOnlyList<AgentEvaluationResults> mixedResults = await agent.EvaluateAsync(
    queries,
    new IAgentEvaluator[] { localEvaluator, foundryEvaluator });

Console.WriteLine("=== Pattern 3: Mixed (local + Foundry) ===");
foreach (AgentEvaluationResults result in mixedResults)
{
    Console.WriteLine($"  {result.ProviderName}: {result.Passed}/{result.Total} passed");

    for (int i = 0; i < result.Items.Count; i++)
    {
        Console.WriteLine($"    Query {i + 1}: {queries[i]}");
        foreach (var metric in result.Items[i].Metrics)
        {
            string detail = metric.Value is NumericMetric nm && nm.Value.HasValue
                ? $"score={nm.Value.Value:F1}"
                : $"passed={metric.Value.Interpretation?.Failed != true}";
            Console.WriteLine($"      {metric.Key}: {detail}");
        }
    }

    Console.WriteLine();
}
