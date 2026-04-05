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
//
// Required environment variables (for AI-powered samples):
//   AZURE_OPENAI_ENDPOINT
//   AZURE_OPENAI_DEPLOYMENT_NAME (optional, defaults to gpt-5-mini)

using System.Diagnostics;
using Azure.AI.OpenAI;
using Azure.Identity;
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
var endpoint = Environment.GetEnvironmentVariable("AZURE_OPENAI_ENDPOINT");
var deploymentName = Environment.GetEnvironmentVariable("AZURE_OPENAI_DEPLOYMENT_NAME") ?? "gpt-5-mini";

OpenAI.Chat.ChatClient? chatClient = null;
if (!string.IsNullOrEmpty(endpoint))
{
    chatClient = new AzureOpenAIClient(new Uri(endpoint), new DefaultAzureCredential())
        .GetChatClient(deploymentName);
}

// Set up optional log file writer
LogFileWriter? logWriter = null;
if (options.LogFilePath is not null)
{
    logWriter = new LogFileWriter(options.LogFilePath);
    await logWriter.WriteHeaderAsync();
}

try
{
    // Run all samples
    var reporter = new ConsoleReporter();
    var verifier = new SampleVerifier(chatClient);
    var orchestrator = new VerificationOrchestrator(verifier, reporter, dotnetRoot, TimeSpan.FromMinutes(3), logWriter);

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
