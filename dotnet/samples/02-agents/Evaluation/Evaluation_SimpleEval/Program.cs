// Copyright (c) Microsoft. All rights reserved.

// Simplest possible agent evaluation: create a Foundry agent, run it against
// test questions, and use Foundry quality evaluators to score the responses.
// For custom domain-specific checks, see the Evaluation_CustomEvals sample.

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
    instructions: "You are a helpful assistant. Provide clear, accurate answers.",
    name: "SimpleAgent");

// Configure Foundry quality evaluators — runs evaluations server-side via the Foundry Evals API.
FoundryEvals evaluator = new(projectClient, deploymentName, FoundryEvals.Relevance, FoundryEvals.Coherence);

// Run the agent against test queries and evaluate in one call.
string[] queries = ["What is photosynthesis?", "How do vaccines work?"];
AgentEvaluationResults results = await agent.EvaluateAsync(queries, evaluator);

// Print results.
Console.WriteLine($"Passed: {results.Passed}/{results.Total}");
if (results.ReportUrl is not null)
{
    Console.WriteLine($"Report: {results.ReportUrl}");
}

Console.WriteLine();

for (int i = 0; i < results.Items.Count; i++)
{
    Console.WriteLine($"Query: {queries[i]}");
    Console.WriteLine($"Response: {(results.InputItems?[i].Response is { } resp ? resp.Substring(0, Math.Min(50, resp.Length)) : "N/A")}...");
    foreach (var metric in results.Items[i].Metrics)
    {
        string score = metric.Value is NumericMetric nm && nm.Value.HasValue
            ? nm.Value.Value.ToString("F1")
            : "N/A";
        Console.WriteLine($"  {metric.Key}: {score}");
    }

    Console.WriteLine();
}
