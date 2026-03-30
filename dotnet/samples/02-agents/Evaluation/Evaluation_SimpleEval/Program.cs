// Copyright (c) Microsoft. All rights reserved.

// Simplest possible agent evaluation: create a Foundry agent, run it against
// test questions, and use Foundry quality evaluators to score the responses.
// For custom domain-specific checks, see the Evaluation_CustomEvals sample.

using Azure.AI.Projects;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.AI.Evaluation;
using FoundryEvals = Microsoft.Agents.AI.AzureAI.FoundryEvals;

string endpoint = Environment.GetEnvironmentVariable("AZURE_AI_PROJECT_ENDPOINT")
    ?? throw new InvalidOperationException("AZURE_AI_PROJECT_ENDPOINT is not set.");
string deploymentName = Environment.GetEnvironmentVariable("AZURE_AI_MODEL_DEPLOYMENT_NAME") ?? "gpt-4o-mini";

AIProjectClient projectClient = new(new Uri(endpoint), new DefaultAzureCredential());

// Create an agent.
AIAgent agent = projectClient.AsAIAgent(
    model: deploymentName,
    instructions: "You are a helpful assistant. Provide clear, accurate answers.",
    name: "SimpleAgent");

// Configure Foundry quality evaluators — these use an LLM to score relevance and coherence.
IChatClient chatClient = projectClient
    .GetProjectOpenAIClient()
    .GetChatClient(deploymentName)
    .AsIChatClient();

FoundryEvals evaluator = new(new ChatConfiguration(chatClient), FoundryEvals.Relevance, FoundryEvals.Coherence);

// Run the agent against test queries and evaluate in one call.
string[] queries = ["What is photosynthesis?", "How do vaccines work?"];
AgentEvaluationResults results = await agent.EvaluateAsync(queries, evaluator);

// Print results.
Console.WriteLine($"Passed: {results.Passed}/{results.Total}");
Console.WriteLine();

for (int i = 0; i < results.Items.Count; i++)
{
    Console.WriteLine($"Query: {queries[i]}");
    foreach (var metric in results.Items[i].Metrics)
    {
        string score = metric.Value is NumericMetric nm && nm.Value.HasValue
            ? nm.Value.Value.ToString("F1")
            : "N/A";
        Console.WriteLine($"  {metric.Key}: {score}");
    }

    Console.WriteLine();
}
