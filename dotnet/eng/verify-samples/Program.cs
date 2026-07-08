// Copyright (c) Microsoft. All rights reserved.

// This tool runs the 01-get-started, 02-agents, and 03-workflows samples and verifies their output.
// Deterministic samples are verified with exact string matching.
// Non-deterministic (LLM) samples are verified using an agent-framework agent.
//
// Usage:
//   dotnet run                                          # Run all samples
//   dotnet run -- 01_hello_agent 05_first_workflow      # Run specific samples by name
//   dotnet run -- --category 01-get-started             # Run the 01-get-started category
//   dotnet run -- --category 02-agents                  # Run the 02-agents category
//   dotnet run -- --category 03-workflows               # Run the 03-workflows category
//   dotnet run -- --parallel 16                         # Run up to 16 samples concurrently
//   dotnet run -- --log results.log                     # Write sequential log to file
//   dotnet run -- --csv results.csv                     # Write CSV summary to file
//   dotnet run -- --md results.md                       # Write Markdown summary to file
//   dotnet run -- --build                                # Build samples during run (default: --no-build)
// Note: By default, this tool expects sample build outputs to already exist.
// Pre-build the solution before running, or pass --build to avoid missing build output failures.
//
// Required environment variables (for AI-powered verification):
//   FOUNDRY_PROJECT_ENDPOINT  — Your Azure AI Foundry project endpoint
//   FOUNDRY_MODEL             — Model deployment name (optional, defaults to gpt-5.4-mini)

using System.Diagnostics;
using Azure.AI.Projects;
using Azure.Identity;
using Microsoft.Agents.AI;
using VerifySamples;

var options = VerifyOptions.Parse(args);
if (options is null)
{
    return 1;
}

var stopwatch = Stopwatch.StartNew();

// Resolve the dotnet/ root directory (verify-samples is at dotnet/eng/verify-samples/)
var dotnetRoot = Path.GetFullPath(Path.Combine(AppContext.BaseDirectory, "..", "..", "..", "..", ".."));
if (!File.Exists(Path.Combine(dotnetRoot, "agent-framework-dotnet.slnx")))
{
    dotnetRoot = Path.GetFullPath(Path.Combine(Directory.GetCurrentDirectory(), "..", ".."));
}

// Set up the AI verifier
var foundryEndpoint = Environment.GetEnvironmentVariable("FOUNDRY_PROJECT_ENDPOINT");
var foundryModel = Environment.GetEnvironmentVariable("FOUNDRY_MODEL") ?? "gpt-5.4-mini";

AIAgent? verifierAgent = null;
if (!string.IsNullOrEmpty(foundryEndpoint))
{
    verifierAgent = new AIProjectClient(new Uri(foundryEndpoint), new DefaultAzureCredential())
        .AsAIAgent(
            model: foundryModel,
            instructions: """
                You are a test output verifier. You will be given:
                1. The actual stdout output of a program
                2. The stderr output (if any)
                3. A list of expectations about what the output should contain or demonstrate

                Your job is to determine whether the actual output satisfies each expectation.
                Be reasonable — the output comes from an LLM so exact wording won't match, but the
                semantic intent should be clearly satisfied.

                In your response, you MUST:
                - Always provide ai_reasoning with a brief overall assessment.
                - Always provide exactly one entry in expectation_results for each expectation,
                  in the same order as the input list.
                - For each expectation_results entry, echo the expectation text in the expectation
                  field and explain your assessment in the detail field, citing evidence from the output.
                """,
            name: "OutputVerifier");
}

// Set up optional log file writer
LogFileWriter? logWriter = null;
if (options.LogFilePath is not null)
{
    logWriter = new LogFileWriter(options.LogFilePath);
    await logWriter.WriteHeaderAsync();
}

Console.WriteLine($"Foundry endpoint: {foundryEndpoint ?? "(not set — AI verification disabled)"}, Model: {foundryModel}");

try
{
    // Run all samples
    var reporter = new ConsoleReporter();
    var verifier = new SampleVerifier(verifierAgent);
    var orchestrator = new VerificationOrchestrator(verifier, reporter, dotnetRoot, TimeSpan.FromMinutes(3), logWriter, buildSamples: options.BuildSamples);

    var run = await orchestrator.RunAllAsync(options.Samples, options.MaxParallelism);

    stopwatch.Stop();

    // Print summary
    var orderedResults = run.SampleOrder
        .Where(run.Results.ContainsKey)
        .Select(name => run.Results[name])
        .ToList();

    reporter.PrintSummary(orderedResults, run.Skipped, stopwatch.Elapsed);

    // Write log file summary
    if (logWriter is not null)
    {
        await logWriter.WriteSummaryAsync(orderedResults, run.Skipped, stopwatch.Elapsed);
        Console.WriteLine($"Log written to: {options.LogFilePath}");
    }

    // Write CSV summary
    if (options.CsvFilePath is not null)
    {
        await CsvResultWriter.WriteAsync(options.CsvFilePath, orderedResults, run.Skipped, options.Samples);
        Console.WriteLine($"CSV written to: {options.CsvFilePath}");
    }

    // Write Markdown summary
    if (options.MarkdownFilePath is not null)
    {
        await MarkdownResultWriter.WriteAsync(options.MarkdownFilePath, orderedResults, run.Skipped, stopwatch.Elapsed);
        Console.WriteLine($"Markdown written to: {options.MarkdownFilePath}");
    }

    return orderedResults.Any(r => !r.Passed) ? 1 : 0;
}
finally
{
    logWriter?.Dispose();
}
