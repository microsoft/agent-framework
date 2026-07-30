// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Concurrent;

namespace VerifySamples;

/// <summary>
/// Orchestrates sample verification: filters, runs in parallel, and collects results.
/// </summary>
internal sealed class VerificationOrchestrator
{
    private readonly SampleVerifier _verifier;
    private readonly ConsoleReporter _reporter;
    private readonly LogFileWriter? _logWriter;
    private readonly string _dotnetRoot;
    private readonly TimeSpan _timeout;
    private readonly bool _buildSamples;

    public VerificationOrchestrator(
        SampleVerifier verifier,
        ConsoleReporter reporter,
        string dotnetRoot,
        TimeSpan timeout,
        LogFileWriter? logWriter = null,
        bool buildSamples = false)
    {
        this._verifier = verifier;
        this._reporter = reporter;
        this._logWriter = logWriter;
        this._dotnetRoot = dotnetRoot;
        this._timeout = timeout;
        this._buildSamples = buildSamples;
    }

    /// <summary>
    /// The result of running all samples through the orchestrator.
    /// </summary>
    internal sealed record RunAllResult(
        ConcurrentDictionary<string, VerificationResult> Results,
        List<(string Name, string Reason)> Skipped,
        List<string> SampleOrder);

    /// <summary>
    /// Filters samples, runs the runnable ones in parallel, and returns all results.
    /// </summary>
    public async Task<RunAllResult> RunAllAsync(
        IReadOnlyList<SampleDefinition> samples,
        int maxParallelism)
    {
        var skipped = new List<(string Name, string Reason)>();
        var runnableSamples = new List<SampleDefinition>();
        var sampleOrder = new List<string>();

        // Separate samples into skipped and runnable
        foreach (var sample in samples)
        {
            sampleOrder.Add(sample.Name);

            if (sample.SkipReason is not null)
            {
                skipped.Add((sample.Name, sample.SkipReason));
                this._reporter.WriteLineWithPrefix(sample.Name, $"SKIPPED — {sample.SkipReason}", ConsoleColor.Yellow);

                if (this._logWriter is not null)
                {
                    await this._logWriter.WriteSkippedAsync(sample.Name, sample.SkipReason);
                }

                continue;
            }

            var missingRequired = sample.RequiredEnvironmentVariables
                .Where(v => string.IsNullOrEmpty(Environment.GetEnvironmentVariable(v)))
                .ToList();

            var missingOptional = sample.OptionalEnvironmentVariables
                .Where(v => string.IsNullOrEmpty(Environment.GetEnvironmentVariable(v)))
                .ToList();

            if (missingRequired.Count > 0 || missingOptional.Count > 0)
            {
                var reasons = new List<string>();
                if (missingRequired.Count > 0)
                {
                    reasons.Add($"Missing required: {string.Join(", ", missingRequired)}");
                }

                if (missingOptional.Count > 0)
                {
                    reasons.Add($"Missing optional (would cause console prompt hang): {string.Join(", ", missingOptional)}");
                }

                var skipReason = string.Join("; ", reasons);
                skipped.Add((sample.Name, skipReason));
                this._reporter.WriteLineWithPrefix(sample.Name, $"SKIPPED — {skipReason}", ConsoleColor.Yellow);

                if (this._logWriter is not null)
                {
                    await this._logWriter.WriteSkippedAsync(sample.Name, skipReason);
                }

                continue;
            }

            runnableSamples.Add(sample);
        }

        // Run samples in parallel
        var results = new ConcurrentDictionary<string, VerificationResult>();
        var semaphore = new SemaphoreSlim(maxParallelism);

        this._reporter.WriteLineWithPrefix(
            "runner", $"Running {runnableSamples.Count} samples (max {maxParallelism} parallel)...");

        try
        {
            var tasks = runnableSamples.Select(sample => this.RunSingleAsync(sample, results, semaphore)).ToArray();
            await Task.WhenAll(tasks);
        }
        finally
        {
            semaphore.Dispose();
        }

        return new RunAllResult(results, skipped, sampleOrder);
    }

    private async Task RunSingleAsync(
        SampleDefinition sample,
        ConcurrentDictionary<string, VerificationResult> results,
        SemaphoreSlim semaphore)
    {
        await semaphore.WaitAsync();
        try
        {
            var log = new List<string>();
            log.Add($"[{sample.Name}] Running...");
            this._reporter.WriteLineWithPrefix(sample.Name, "Running...");

            var projectPath = Path.Combine(this._dotnetRoot, sample.ProjectPath);
            var run = sample.Inputs.Length > 0
                ? await SampleRunner.RunAsync(projectPath, this._timeout, sample.Inputs, sample.InputDelayMs, build: this._buildSamples)
                : await SampleRunner.RunAsync(projectPath, this._timeout, build: this._buildSamples);

            log.Add($"[{sample.Name}] Completed ({run.Elapsed.TotalSeconds:F1}s, exit={run.ExitCode})");
            this._reporter.WriteLineWithPrefix(
                sample.Name, $"Completed ({run.Elapsed.TotalSeconds:F1}s, exit={run.ExitCode}). Verifying...");

            var result = await this._verifier.VerifyAsync(sample, run);

            if (result.Passed)
            {
                log.Add($"[{sample.Name}] PASSED");
                this._reporter.WriteLineWithPrefix(sample.Name, "PASSED", ConsoleColor.Green);
            }
            else
            {
                log.Add($"[{sample.Name}] FAILED");
                this._reporter.WriteLineWithPrefix(sample.Name, "FAILED", ConsoleColor.Red);
                foreach (var failure in result.Failures)
                {
                    log.Add($"[{sample.Name}]   ✗ {failure}");
                    this._reporter.WriteLineWithPrefix(sample.Name, $"  ✗ {failure}", ConsoleColor.Red);
                }
            }

            if (result.AIReasoning is not null)
            {
                log.Add($"[{sample.Name}]   AI: {result.AIReasoning}");
                this._reporter.WriteLineWithPrefix(
                    sample.Name, $"  AI: {Truncate(result.AIReasoning, 300)}", ConsoleColor.DarkGray);
            }

            var verificationResult = new VerificationResult
            {
                SampleName = result.SampleName,
                Passed = result.Passed,
                Summary = result.Summary,
                Failures = result.Failures,
                AIReasoning = result.AIReasoning,
                Stdout = run.Stdout,
                Stderr = run.Stderr,
                LogLines = log,
            };
            results[sample.Name] = verificationResult;

            if (this._logWriter is not null)
            {
                await this._logWriter.WriteSampleResultAsync(verificationResult);
            }
        }
        finally
        {
            semaphore.Release();
        }
    }

    private static string Truncate(string text, int maxLength)
        => text.Length <= maxLength ? text : text[..maxLength] + "...";
}
