// Copyright (c) Microsoft. All rights reserved.

// This sample demonstrates evaluating a multi-agent workflow with per-agent breakdown.

using Azure.AI.Projects;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Workflows;
using Microsoft.Extensions.AI;

string endpoint = Environment.GetEnvironmentVariable("AZURE_AI_PROJECT_ENDPOINT")
    ?? throw new InvalidOperationException("AZURE_AI_PROJECT_ENDPOINT is not set.");
string deploymentName = Environment.GetEnvironmentVariable("AZURE_AI_MODEL_DEPLOYMENT_NAME") ?? "gpt-4o-mini";

AIProjectClient aiProjectClient = new(new Uri(endpoint), new DefaultAzureCredential());

// Create two agents: a planner and an executor.
AIAgent planner = aiProjectClient.AsAIAgent(
    model: deploymentName,
    instructions: "You plan trips. Output a concise bullet-point plan.",
    name: "planner");

AIAgent executor = aiProjectClient.AsAIAgent(
    model: deploymentName,
    instructions: "You execute travel plans. Confirm the bookings listed in the plan.",
    name: "executor");

// Build a simple planner -> executor workflow.
Workflow workflow = new WorkflowBuilder(planner)
    .AddEdge(planner, executor)
    .Build();

// Run the workflow to completion (RunAsync returns Run which supports EvaluateAsync).
await using Run run = await InProcessExecution.RunAsync(
    workflow,
    new ChatMessage(ChatRole.User, "Plan a weekend trip to Paris"));

// Print the events from the run.
foreach (WorkflowEvent evt in run.OutgoingEvents)
{
    if (evt is AgentResponseEvent response)
    {
        Console.WriteLine($"  {response.ExecutorId}: {response.Response.Text[..Math.Min(80, response.Response.Text.Length)]}...");
    }
}

// Evaluate with per-agent breakdown.
EvalCheck isNonempty = FunctionEvaluator.Create("is_nonempty", (string response) => response.Trim().Length > 5);
EvalCheck hasKeywords = EvalChecks.KeywordCheck("plan", "trip");
LocalEvaluator local = new(isNonempty, hasKeywords);

AgentEvaluationResults results = await run.EvaluateAsync(local);

Console.WriteLine();
Console.WriteLine($"Overall: {results.Passed}/{results.Total} passed");

if (results.SubResults is not null)
{
    foreach (var (agentName, sub) in results.SubResults)
    {
        Console.WriteLine($"  {agentName}: {sub.Passed}/{sub.Total} passed");
        for (int i = 0; i < sub.Items.Count; i++)
        {
            foreach (var metric in sub.Items[i].Metrics)
            {
                string status = metric.Value.Interpretation?.Failed == true ? "FAIL" : "PASS";
                Console.WriteLine($"    [{status}] {metric.Key}");
            }
        }
    }
}
