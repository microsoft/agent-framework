// Copyright (c) Microsoft. All rights reserved.

using System.Text;

namespace VerifySamples;

/// <summary>
/// Incrementally writes a sequential (non-interleaved) log file, appending after each sample completes.
/// Thread-safe: multiple parallel tasks may call write methods concurrently.
/// </summary>
internal sealed class LogFileWriter : IDisposable
{
    private readonly string _path;
    private readonly SemaphoreSlim _writeLock = new(1, 1);

    public LogFileWriter(string path)
    {
        this._path = path;
    }

    /// <inheritdoc />
    public void Dispose()
    {
        this._writeLock.Dispose();
    }

    /// <summary>
    /// Writes the log file header. Call once at the start of the run.
    /// </summary>
    public async Task WriteHeaderAsync()
    {
        var sb = new StringBuilder();
        sb.AppendLine($"Sample Verification Log — {DateTime.UtcNow:yyyy-MM-dd HH:mm:ss} UTC");
        sb.AppendLine(new string('═', 72));
        sb.AppendLine();

        await File.WriteAllTextAsync(this._path, sb.ToString());
    }

    /// <summary>
    /// Appends a skipped-sample entry to the log file.
    /// </summary>
    public async Task WriteSkippedAsync(string name, string reason)
    {
        var sb = new StringBuilder();
        sb.AppendLine($"── {name} ──");
        sb.AppendLine($"Status: SKIPPED — {reason}");
        sb.AppendLine();

        await this.AppendAsync(sb.ToString());
    }

    /// <summary>
    /// Appends a completed sample's full output section to the log file.
    /// </summary>
    public async Task WriteSampleResultAsync(VerificationResult result)
    {
        var sb = new StringBuilder();
        sb.AppendLine(new string('─', 72));
        sb.AppendLine($"── {result.SampleName} ──");
        sb.AppendLine($"Status: {(result.Passed ? "PASSED" : "FAILED")}");
        sb.AppendLine();

        foreach (var line in result.LogLines)
        {
            sb.AppendLine(line);
        }

        sb.AppendLine();

        if (!string.IsNullOrWhiteSpace(result.Stdout))
        {
            sb.AppendLine("--- stdout ---");
            sb.AppendLine(result.Stdout.TrimEnd());
            sb.AppendLine("--- end stdout ---");
            sb.AppendLine();
        }

        if (!string.IsNullOrWhiteSpace(result.Stderr))
        {
            sb.AppendLine("--- stderr ---");
            sb.AppendLine(result.Stderr.TrimEnd());
            sb.AppendLine("--- end stderr ---");
            sb.AppendLine();
        }

        if (result.Failures.Count > 0)
        {
            sb.AppendLine("Failures:");
            foreach (var failure in result.Failures)
            {
                sb.AppendLine($"  ✗ {failure}");
            }

            sb.AppendLine();
        }

        if (result.AIReasoning is not null)
        {
            sb.AppendLine("AI Reasoning:");
            sb.AppendLine(result.AIReasoning);
            sb.AppendLine();
        }

        await this.AppendAsync(sb.ToString());
    }

    /// <summary>
    /// Appends the final summary section and elapsed time to the log file.
    /// </summary>
    public async Task WriteSummaryAsync(
        IReadOnlyList<VerificationResult> orderedResults,
        IReadOnlyList<(string Name, string Reason)> skipped,
        TimeSpan elapsed)
    {
        var passCount = orderedResults.Count(r => r.Passed);
        var failCount = orderedResults.Count(r => !r.Passed);

        var sb = new StringBuilder();
        sb.AppendLine(new string('═', 72));
        sb.AppendLine("SUMMARY");
        sb.AppendLine();

        foreach (var result in orderedResults)
        {
            sb.AppendLine($"  {(result.Passed ? "✓" : "✗")} {result.SampleName}: {result.Summary}");
        }

        foreach (var (name, reason) in skipped)
        {
            sb.AppendLine($"  ○ {name}: Skipped — {reason}");
        }

        sb.AppendLine();
        sb.AppendLine($"Results: {passCount} passed{(failCount > 0 ? $", {failCount} failed" : "")}{(skipped.Count > 0 ? $", {skipped.Count} skipped" : "")}");
        sb.AppendLine($"Elapsed: {elapsed.Hours:D2}:{elapsed.Minutes:D2}:{elapsed.Seconds:D2}");

        await this.AppendAsync(sb.ToString());
    }

    private async Task AppendAsync(string text)
    {
        await this._writeLock.WaitAsync();
        try
        {
            await File.AppendAllTextAsync(this._path, text);
        }
        finally
        {
            this._writeLock.Release();
        }
    }
}
