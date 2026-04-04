// Copyright (c) Microsoft. All rights reserved.

using System.Text;

namespace VerifySamples;

/// <summary>
/// Writes a CSV summary of sample verification results.
/// </summary>
internal static class CsvResultWriter
{
    /// <summary>
    /// Writes the results to a CSV file at the specified path.
    /// </summary>
    public static async Task WriteAsync(
        string path,
        IReadOnlyList<VerificationResult> orderedResults,
        IReadOnlyList<(string Name, string Reason)> skipped,
        IReadOnlyList<SampleDefinition> samples)
    {
        var pathLookup = samples.ToDictionary(s => s.Name, s => s.ProjectPath);

        var sb = new StringBuilder();
        sb.AppendLine("Sample,ProjectPath,Status,FailedChecks,Failures");

        foreach (var result in orderedResults)
        {
            var status = result.Passed ? "PASSED" : "FAILED";
            var failedChecks = result.Failures.Count;
            var failures = string.Join("; ", result.Failures);
            pathLookup.TryGetValue(result.SampleName, out var projectPath);
            sb.AppendLine($"{CsvEscape(result.SampleName)},{CsvEscape(projectPath ?? "")},{status},{failedChecks},{CsvEscape(failures)}");
        }

        foreach (var (name, reason) in skipped)
        {
            pathLookup.TryGetValue(name, out var projectPath);
            sb.AppendLine($"{CsvEscape(name)},{CsvEscape(projectPath ?? "")},SKIPPED,0,{CsvEscape(reason)}");
        }

        await File.WriteAllTextAsync(path, sb.ToString());
    }

    /// <summary>
    /// Escapes a value for CSV: wraps in quotes if it contains commas, quotes, or newlines.
    /// </summary>
    private static string CsvEscape(string value)
    {
        if (value.Contains('"') || value.Contains(',') || value.Contains('\n') || value.Contains('\r'))
        {
            return $"\"{value.Replace("\"", "\"\"")}\"";
        }

        return value;
    }
}
