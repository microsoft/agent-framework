// Copyright (c) Microsoft. All rights reserved.

using System.Text;

namespace VerifySamples;

/// <summary>
/// Writes a Markdown summary of sample verification results.
/// </summary>
internal static class MarkdownResultWriter
{
    /// <summary>
    /// Writes the results to a Markdown file at the specified path.
    /// </summary>
    public static async Task WriteAsync(
        string path,
        IReadOnlyList<VerificationResult> orderedResults,
        IReadOnlyList<(string Name, string Reason)> skipped,
        TimeSpan elapsed)
    {
        var passCount = orderedResults.Count(r => r.Passed);
        var failCount = orderedResults.Count(r => !r.Passed);

        var sb = new StringBuilder();
        sb.AppendLine("# Sample Verification Results");
        sb.AppendLine();
        sb.AppendLine($"**{passCount} passed, {failCount} failed, {skipped.Count} skipped** | Elapsed: {elapsed.Hours:D2}:{elapsed.Minutes:D2}:{elapsed.Seconds:D2}");
        sb.AppendLine();

        // Results table
        sb.AppendLine("| Sample | Status | Failed Checks | Failures |");
        sb.AppendLine("|--------|--------|---------------|----------|");

        foreach (var result in orderedResults)
        {
            var status = result.Passed ? "✅ PASSED" : "❌ FAILED";
            var failedChecks = result.Failures.Count;
            var failures = MdEscape(string.Join("; ", result.Failures));
            sb.AppendLine($"| {MdEscape(result.SampleName)} | {status} | {failedChecks} | {failures} |");
        }

        foreach (var (name, reason) in skipped)
        {
            sb.AppendLine($"| {MdEscape(name)} | ⏭️ SKIPPED | 0 | {MdEscape(reason)} |");
        }

        // Collapsible AI reasoning details for failures
        var failures2 = orderedResults.Where(r => !r.Passed && !string.IsNullOrEmpty(r.AIReasoning)).ToList();
        if (failures2.Count > 0)
        {
            sb.AppendLine();
            sb.AppendLine("## Failure Details");
            sb.AppendLine();

            foreach (var result in failures2)
            {
                sb.AppendLine($"<details><summary><strong>{HtmlEscape(result.SampleName)}</strong></summary>");
                sb.AppendLine();
                if (result.Failures.Count > 0)
                {
                    foreach (var failure in result.Failures)
                    {
                        sb.AppendLine($"- {MdEscape(failure)}");
                    }

                    sb.AppendLine();
                }

                sb.AppendLine("**AI Reasoning:**");
                sb.AppendLine();
                sb.AppendLine("```");
                sb.AppendLine(result.AIReasoning);
                sb.AppendLine("```");
                sb.AppendLine();
                sb.AppendLine("</details>");
                sb.AppendLine();
            }
        }

        await File.WriteAllTextAsync(path, sb.ToString());
    }

    /// <summary>
    /// Escapes pipe characters and newlines for use inside Markdown table cells.
    /// </summary>
    private static string MdEscape(string value)
    {
        return value.Replace("|", "\\|").Replace("\n", " ").Replace("\r", "");
    }

    /// <summary>
    /// Escapes HTML special characters for use inside HTML tags.
    /// </summary>
    private static string HtmlEscape(string value)
    {
        return value.Replace("&", "&amp;").Replace("<", "&lt;").Replace(">", "&gt;").Replace("\"", "&quot;");
    }
}
