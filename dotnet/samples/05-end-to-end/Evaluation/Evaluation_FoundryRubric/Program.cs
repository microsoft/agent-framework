// Copyright (c) Microsoft. All rights reserved.

// This sample evaluates a pre-existing Azure AI Foundry agent against a rubric evaluator
// that was authored in the Foundry portal.
//
// Rubric evaluators are LLM-as-judge evaluators with custom scoring dimensions you define
// for your domain. agent-framework consumes pre-existing rubric evaluators — they are
// authored in the Foundry portal (or via the dedicated SDK / REST surface) and referenced
// here by name and version.
//
// Prerequisites:
//   - An Azure AI Foundry project with a deployed model.
//   - A registered Foundry agent in that project (the rubric was created against this agent).
//   - A rubric evaluator already created in the Foundry portal.
//   - .env (or environment) populated with the FOUNDRY_* variables below.
//
// IMPORTANT: FOUNDRY_PROJECT_ENDPOINT must be the project-scoped URL
//   https://<resource>.services.ai.azure.com/api/projects/<project>
// A bare Azure OpenAI endpoint silently fails eval submission with HTTP 500.

using Azure.AI.Projects;
using Azure.AI.Projects.Agents;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Foundry;
using FoundryEvals = Microsoft.Agents.AI.Foundry.FoundryEvals;

string projectEndpoint = Environment.GetEnvironmentVariable("FOUNDRY_PROJECT_ENDPOINT")
    ?? throw new InvalidOperationException("FOUNDRY_PROJECT_ENDPOINT is not set.");
string model = Environment.GetEnvironmentVariable("FOUNDRY_MODEL")
    ?? throw new InvalidOperationException("FOUNDRY_MODEL is not set.");
string agentName = Environment.GetEnvironmentVariable("FOUNDRY_AGENT_NAME")
    ?? throw new InvalidOperationException("FOUNDRY_AGENT_NAME is not set.");
string? agentVersion = Environment.GetEnvironmentVariable("FOUNDRY_AGENT_VERSION");
string rubricName = Environment.GetEnvironmentVariable("FOUNDRY_RUBRIC_NAME")
    ?? throw new InvalidOperationException("FOUNDRY_RUBRIC_NAME is not set.");
string? rubricVersion = Environment.GetEnvironmentVariable("FOUNDRY_RUBRIC_VERSION");

// WARNING: DefaultAzureCredential is convenient for development but requires careful
// consideration in production. Prefer ManagedIdentityCredential (or a specific credential)
// to avoid latency, unintended credential probing, and fallback security risks.
AIProjectClient projectClient = new(new Uri(projectEndpoint), new DefaultAzureCredential());

// 1. Connect to the pre-existing Foundry agent the rubric was created against.
FoundryAgent agent;
if (agentVersion is null)
{
    ProjectsAgentRecord agentRecord = await projectClient.AgentAdministrationClient.GetAgentAsync(agentName);
    agent = projectClient.AsAIAgent(agentRecord);
}
else
{
    ProjectsAgentVersion versionRecord = await projectClient.AgentAdministrationClient.GetAgentVersionAsync(agentName, agentVersion);
    agent = projectClient.AsAIAgent(versionRecord);
}

// 2. Reference the pre-existing rubric evaluator by name + version.
//    Always pin a version for reproducible CI runs; a versionless ref resolves to the
//    current version at run time and emits a Trace.TraceWarning on each criterion build.
GeneratedEvaluatorRef rubric = rubricVersion is null
    ? GeneratedEvaluatorRef.Latest(rubricName)
    : new GeneratedEvaluatorRef(rubricName, rubricVersion);

// 3. Mix the rubric with built-in evaluators in a single FoundryEvals config.
//    The implicit conversion lets you pass strings and refs interchangeably.
FoundryEvals evals = new(
    projectClient,
    model,
    rubric,
    FoundryEvals.Relevance,
    FoundryEvals.Coherence);

// 4. Run two example queries against the agent and evaluate the outputs in one call.
string[] queries =
[
    "What's the weather like in Seattle?",
    "Should I bring an umbrella to London tomorrow?",
];

Console.WriteLine(new string('=', 60));
Console.WriteLine($"Evaluating '{agent.Name}' with rubric '{rubricName}' (version {rubricVersion ?? "latest"})");
Console.WriteLine(new string('=', 60));

AgentEvaluationResults results = await agent.EvaluateAsync(queries, evals);

Console.WriteLine($"Status: {results.Status}");
Console.WriteLine($"Results: {results.Passed}/{results.Total} passed");
if (results.ReportUrl is not null)
{
    Console.WriteLine($"Portal: {results.ReportUrl}");
}

Console.WriteLine(results.Passed == results.Total ? "[PASS] All passed" : $"[FAIL] {results.Failed} failed");

// 5. Print per-dimension breakdown for each evaluated item — this is the unique value
//    of a rubric evaluator over the built-in numeric ones.
Console.WriteLine();
Console.WriteLine(new string('=', 60));
Console.WriteLine("Per-dimension scores");
Console.WriteLine(new string('=', 60));

if (results.DetailedItems is { Count: > 0 })
{
    for (int i = 0; i < results.DetailedItems.Count; i++)
    {
        EvalItemResult item = results.DetailedItems[i];
        Console.WriteLine($"Item {i + 1}{(i < queries.Length ? $" — \"{queries[i]}\"" : string.Empty)}");

        foreach (EvalScoreResult score in item.Scores)
        {
            Console.WriteLine($"  {score.Name}: {score.Score:F1}{(score.Passed is bool p ? (p ? " (pass)" : " (fail)") : string.Empty)}");
            if (score.Dimensions is { Count: > 0 } dims)
            {
                foreach (RubricScore d in dims)
                {
                    string scoreStr = d.Score is int s ? s.ToString() : "n/a";
                    Console.WriteLine($"    - {d.Id}: {scoreStr}  (weight={d.Weight}, applicable={d.Applicable})");
                }
            }
        }

        Console.WriteLine();
    }
}

// 6. CI quality gate — fail the build if a critical dimension drops below threshold.
//    Replace "general_quality" with whatever dimension id your rubric actually defines.
Console.WriteLine(new string('=', 60));
Console.WriteLine("Per-dimension quality gate");
Console.WriteLine(new string('=', 60));

try
{
    results.AssertDimensionScoreAtLeast("general_quality", minScore: 3.0, evaluator: rubricName, requireApplicable: true);
    Console.WriteLine($"[PASS] {results.ProviderName}: general_quality >= 3 on every item");
}
catch (InvalidOperationException ex)
{
    Console.WriteLine($"[FAIL] {results.ProviderName}: dimension gate tripped: {ex.Message}");
    System.Environment.ExitCode = 1;
}
