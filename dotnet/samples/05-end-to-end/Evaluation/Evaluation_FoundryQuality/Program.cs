// Copyright (c) Microsoft. All rights reserved.

// This sample demonstrates agent evaluation using Foundry quality evaluators
// (Relevance, Coherence) via the Foundry Evals API.

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
    instructions: "You are a helpful assistant that provides clear, accurate answers.",
    name: "QualityTestAgent");

// Configure Foundry evaluators.
FoundryEvals foundryEvals = new(projectClient, deploymentName, FoundryEvals.Relevance, FoundryEvals.Coherence);

// --- Pattern 1: Run agent, then evaluate pre-existing responses ---
string[] queries = ["What is photosynthesis?", "Explain gravity in simple terms."];

AgentResponse[] responses = new AgentResponse[queries.Length];
for (int i = 0; i < queries.Length; i++)
{
    responses[i] = await agent.RunAsync(queries[i]);
}

AgentEvaluationResults results1 = await agent.EvaluateAsync(responses, queries, foundryEvals);

Console.WriteLine("=== Pattern 1: Evaluate pre-existing responses ===");
PrintResults(results1, queries);

// --- Pattern 2: Run + evaluate in one call ---
string[] queries2 = ["What causes rain?", "Why is the sky blue?"];
AgentEvaluationResults results2 = await agent.EvaluateAsync(queries2, foundryEvals);

Console.WriteLine("=== Pattern 2: Run + evaluate in one call ===");
PrintResults(results2, queries2);

static void PrintResults(AgentEvaluationResults results, string[] queries)
{
    Console.WriteLine($"Provider: {results.ProviderName}");
    Console.WriteLine($"Passed: {results.Passed}/{results.Total}");
    if (results.ReportUrl is not null)
    {
        Console.WriteLine($"Report: {results.ReportUrl}");
    }

    Console.WriteLine();

    for (int i = 0; i < results.Items.Count; i++)
    {
        Console.WriteLine($"  Query {i + 1}: {(i < queries.Length ? queries[i] : "N/A")}");
        foreach (var metric in results.Items[i].Metrics)
        {
            string score = metric.Value is NumericMetric nm && nm.Value.HasValue
                ? nm.Value.Value.ToString("F1")
                : "N/A";
            Console.WriteLine($"    {metric.Key}: {score}");
        }

        Console.WriteLine();
    }
}
