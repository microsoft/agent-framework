// Copyright (c) Microsoft. All rights reserved.

// This sample demonstrates evaluating a multi-agent workflow against a
// golden answer using Foundry's reference-based Similarity evaluator.

using Azure.AI.Projects;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Workflows;
using Microsoft.Extensions.AI;
using FoundryEvals = Microsoft.Agents.AI.Foundry.FoundryEvals;

string endpoint = Environment.GetEnvironmentVariable("AZURE_AI_PROJECT_ENDPOINT")
    ?? throw new InvalidOperationException("AZURE_AI_PROJECT_ENDPOINT is not set.");
string deploymentName = Environment.GetEnvironmentVariable("AZURE_AI_MODEL_DEPLOYMENT_NAME") ?? "gpt-4o-mini";

// WARNING: DefaultAzureCredential is convenient for development but requires careful consideration in production.
// In production, consider using a specific credential (e.g., ManagedIdentityCredential) to avoid
// latency issues, unintended credential probing, and potential security risks from fallback mechanisms.
AIProjectClient projectClient = new(new Uri(endpoint), new DefaultAzureCredential());

// Build a two-agent workflow: a researcher writes a draft answer, then an
// editor polishes it into the final response that we compare to ground truth.
// EmitAgentResponseEvents is enabled so the workflow surfaces an AgentResponseEvent
// for each agent — this is what EvaluateAsync uses to find the overall final answer.
var hostOptions = new AIAgentHostOptions { EmitAgentResponseEvents = true };

AIAgent researcher = projectClient.AsAIAgent(
    model: deploymentName,
    instructions: "You research questions and produce a short factual draft answer.",
    name: "researcher");

AIAgent editor = projectClient.AsAIAgent(
    model: deploymentName,
    instructions: "You take a draft answer and produce the final concise response.",
    name: "editor");

ExecutorBinding researcherExecutor = researcher.BindAsExecutor(hostOptions);
ExecutorBinding editorExecutor = editor.BindAsExecutor(hostOptions);

Workflow workflow = new WorkflowBuilder(researcherExecutor)
    .AddEdge(researcherExecutor, editorExecutor)
    .Build();

// Run the workflow against the user question.
const string Query = "What is the capital of France?";
const string GroundTruth = "Paris";

await using Run run = await InProcessExecution.RunAsync(
    workflow,
    new ChatMessage(ChatRole.User, Query));

// Evaluate the overall workflow output against a golden answer using the
// reference-based Similarity evaluator. The 'expectedOutput' value is stamped
// onto the overall EvalItem.ExpectedOutput and is surfaced to Foundry as
// `ground_truth` in the underlying JSONL payload.
//
// Per-agent breakdown is disabled here: ground truth applies to the workflow's
// final answer, not to each sub-agent's intermediate output. Without
// includePerAgent: false, the evaluator would be invoked for per-agent items
// (which have no ExpectedOutput) and Similarity would fail validation.
FoundryEvals similarity = new(projectClient, deploymentName, FoundryEvals.Similarity);

AgentEvaluationResults results = await run.EvaluateAsync(
    similarity,
    includePerAgent: false,
    expectedOutput: GroundTruth);

Console.WriteLine($"Query: {Query}");
Console.WriteLine($"Expected: {GroundTruth}");
Console.WriteLine($"Provider: {results.ProviderName}");
Console.WriteLine($"Passed: {results.Passed}/{results.Total}");
if (results.ReportUrl is not null)
{
    Console.WriteLine($"Report: {results.ReportUrl}");
}
