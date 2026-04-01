// Copyright (c) Microsoft. All rights reserved.

// This sample demonstrates writing custom evaluation functions for domain-specific
// checks. Custom evaluators run locally — no cloud evaluator service needed.
// For LLM-based quality scoring (relevance, coherence), see Evaluation_SimpleEval.

using Azure.AI.Projects;
using Azure.Identity;
using Microsoft.Agents.AI;

string endpoint = Environment.GetEnvironmentVariable("AZURE_AI_PROJECT_ENDPOINT") ?? throw new InvalidOperationException("AZURE_AI_PROJECT_ENDPOINT is not set.");
string deploymentName = Environment.GetEnvironmentVariable("AZURE_AI_MODEL_DEPLOYMENT_NAME") ?? "gpt-4o-mini";

// WARNING: DefaultAzureCredential is convenient for development but requires careful consideration in production.
// In production, consider using a specific credential (e.g., ManagedIdentityCredential) to avoid
// latency issues, unintended credential probing, and potential security risks from fallback mechanisms.
AIProjectClient projectClient = new(new Uri(endpoint), new DefaultAzureCredential());

AIAgent agent = projectClient.AsAIAgent(
    model: deploymentName,
    instructions: "You are a customer support agent. Help users resolve their issues "
                + "politely and provide clear, actionable steps.",
    name: "SupportAgent");

// Custom check: the agent should not refuse to help.
EvalCheck noRefusal = FunctionEvaluator.Create("no_refusal", (string response) =>
    !response.Contains("I can't help", StringComparison.OrdinalIgnoreCase)
    && !response.Contains("I'm unable to", StringComparison.OrdinalIgnoreCase)
    && !response.Contains("outside my scope", StringComparison.OrdinalIgnoreCase));

// Custom check: response should include actionable guidance (numbered steps or bullet points).
EvalCheck hasActionableSteps = FunctionEvaluator.Create("has_actionable_steps", (string response) =>
    response.Contains("1.", StringComparison.Ordinal)
    || response.Contains("- ", StringComparison.Ordinal)
    || response.Contains("• ", StringComparison.Ordinal));

// Custom check: response should be substantial but not excessively long.
EvalCheck reasonableLength = FunctionEvaluator.Create("reasonable_length", (string response) =>
    response.Length >= 50 && response.Length <= 2000);

// Combine all custom checks into a local evaluator.
LocalEvaluator evaluator = new(noRefusal, hasActionableSteps, reasonableLength);

string[] queries =
[
    "My order hasn't arrived after two weeks. What should I do?",
    "I was charged twice for the same item. Can you help?",
    "How do I return a damaged product?",
];

AgentEvaluationResults results = await agent.EvaluateAsync(queries, evaluator);

Console.WriteLine($"Passed: {results.Passed}/{results.Total}");
Console.WriteLine();

for (int i = 0; i < results.Items.Count; i++)
{
    Console.WriteLine($"Query: {queries[i]}");
    Console.WriteLine($"Response: {(results.InputItems?[i].Response is { } resp ? resp.Substring(0, Math.Min(50, resp.Length)) : "N/A")}...");
    foreach (var metric in results.Items[i].Metrics)
    {
        string status = metric.Value.Interpretation?.Failed == true ? "FAIL" : "PASS";
        Console.WriteLine($"  [{status}] {metric.Key}");
    }

    Console.WriteLine();
}
