// Copyright (c) Microsoft. All rights reserved.

// This sample demonstrates evaluating agent responses against expected outputs.

using Azure.AI.Projects;
using Azure.Identity;
using Microsoft.Agents.AI;

string endpoint = Environment.GetEnvironmentVariable("AZURE_AI_PROJECT_ENDPOINT") ?? throw new InvalidOperationException("AZURE_AI_PROJECT_ENDPOINT is not set.");
string deploymentName = Environment.GetEnvironmentVariable("AZURE_AI_MODEL_DEPLOYMENT_NAME") ?? "gpt-4o-mini";

// WARNING: DefaultAzureCredential is convenient for development but requires careful consideration in production.
// In production, consider using a specific credential (e.g., ManagedIdentityCredential) to avoid
// latency issues, unintended credential probing, and potential security risks from fallback mechanisms.
AIProjectClient projectClient = new(new Uri(endpoint), new DefaultAzureCredential());

// Combine built-in checks.
LocalEvaluator localEvaluator = new(
    EvalChecks.ContainsExpected(),   // response must contain the expected answer
    EvalChecks.NonEmpty());          // response must not be empty

AIAgent agent = projectClient.AsAIAgent(
    model: deploymentName,
    instructions: "You are a math tutor. Answer concisely with the numeric result.",
    name: "MathTutor");

// Queries and expected outputs.
string[] queries = ["What is 2 + 2?", "What is the square root of 144?"];
string[] expectedOutputs = ["4", "12"];

// Run the agent and evaluate with expected outputs.
AgentEvaluationResults results = await agent.EvaluateAsync(
    queries,
    localEvaluator,
    expectedOutput: expectedOutputs);

// Print results.
Console.WriteLine($"Evaluation: {results.ProviderName}");
Console.WriteLine($"  Passed: {results.Passed}/{results.Total}");
Console.WriteLine($"  All passed: {results.AllPassed}");
Console.WriteLine();

for (int i = 0; i < results.Items.Count; i++)
{
    Console.WriteLine($"Query: {queries[i]}  |  Expected: {expectedOutputs[i]}");
    foreach (var metric in results.Items[i].Metrics)
    {
        string status = metric.Value.Interpretation?.Failed == true ? "FAIL" : "PASS";
        Console.WriteLine($"  [{status}] {metric.Key}: {metric.Value.Interpretation?.Reason}");
    }

    Console.WriteLine();
}
