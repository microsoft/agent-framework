// Copyright (c) Microsoft. All rights reserved.

using System.Text.RegularExpressions;
using Azure.AI.Projects;
using Azure.Identity;
using ClawAgent;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI.Evaluation;
using FoundryEvals = Microsoft.Agents.AI.Foundry.FoundryEvals;

string[] queries =
[
    "What's the capital of France?",
    "Value MSFT for me.",
    "How risky is my portfolio?",
];

await using ClawAgentBuild build = await ClawAgentFactory.CreateAsync(new ClawAgentFactoryOptions
{
    // Evals run only the trusted skill scripts bundled with this sample. Auto-approve those scripts
    // so evaluation receives the completed answer instead of an approval request.
    AdditionalToolAutoApprovalRules = [AgentSkillsProvider.AllToolsAutoApprovalRule],
    Log = Console.WriteLine,
});

Regex digitRegex = new(@"\d");
LocalEvaluator localEvaluator = new(
    FunctionEvaluator.Create("off_topic_refusal_or_finance_steer", item =>
    {
        if (!item.Query.Contains("capital of France", StringComparison.OrdinalIgnoreCase))
        {
            return true;
        }

        return item.Response.Contains("finance", StringComparison.OrdinalIgnoreCase)
            || item.Response.Contains("invest", StringComparison.OrdinalIgnoreCase)
            || item.Response.Contains("portfolio", StringComparison.OrdinalIgnoreCase)
            || item.Response.Contains("outside", StringComparison.OrdinalIgnoreCase)
            || item.Response.Contains("can't", StringComparison.OrdinalIgnoreCase)
            || item.Response.Contains("cannot", StringComparison.OrdinalIgnoreCase);
    }),
    FunctionEvaluator.Create("numeric_valuation", item =>
        !item.Query.Contains("Value MSFT", StringComparison.OrdinalIgnoreCase)
        || digitRegex.IsMatch(item.Response)),
    FunctionEvaluator.Create("portfolio_risk_runs", item =>
        !item.Query.Contains("portfolio", StringComparison.OrdinalIgnoreCase)
        || !string.IsNullOrWhiteSpace(item.Response)));

AgentEvaluationResults localResults = await build.Agent.EvaluateAsync(queries, localEvaluator, evalName: "ClawLocalFinanceEvals");
PrintResults("Local finance evals", localResults, queries);

string? endpoint = Environment.GetEnvironmentVariable("FOUNDRY_PROJECT_ENDPOINT");
if (!string.IsNullOrWhiteSpace(endpoint))
{
    string deploymentName = Environment.GetEnvironmentVariable("AZURE_AI_MODEL_DEPLOYMENT_NAME") ?? "gpt-5.4";
    AIProjectClient projectClient = new(new Uri(endpoint), new DefaultAzureCredential());
    FoundryEvals foundryEvals = new(projectClient, deploymentName, FoundryEvals.Relevance, FoundryEvals.Coherence);
    AgentEvaluationResults foundryResults = await build.Agent.EvaluateAsync(queries, foundryEvals, evalName: "ClawFoundryQualityEvals");
    PrintResults("Foundry quality evals", foundryResults, queries);
}
else
{
    Console.WriteLine("Skipping Foundry quality evals. Set FOUNDRY_PROJECT_ENDPOINT to enable them.");
}

static void PrintResults(string title, AgentEvaluationResults results, string[] queries)
{
    Console.WriteLine($"=== {title} ===");
    Console.WriteLine($"Provider: {results.ProviderName}");
    Console.WriteLine($"Passed: {results.Passed}/{results.Total}");
    if (results.ReportUrl is not null)
    {
        Console.WriteLine($"Report: {results.ReportUrl}");
    }

    Console.WriteLine();

    for (int i = 0; i < results.Items.Count; i++)
    {
        Console.WriteLine($"Query: {(i < queries.Length ? queries[i] : "N/A")}");
        Console.WriteLine($"Response: {(results.InputItems?[i].Response is { } response ? response[..Math.Min(80, response.Length)] : "N/A")}...");
        foreach (var metric in results.Items[i].Metrics)
        {
            string value = metric.Value is NumericMetric numericMetric && numericMetric.Value.HasValue
                ? numericMetric.Value.Value.ToString("F1")
                : metric.Value.Interpretation?.Failed == true ? "FAIL" : "PASS";
            Console.WriteLine($"  {metric.Key}: {value}");
        }

        Console.WriteLine();
    }
}
