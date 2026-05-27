// Copyright (c) Microsoft. All rights reserved.

namespace VerifySamples;

/// <summary>
/// Thread-safe console output with sample-name prefixes and colored status.
/// </summary>
internal sealed class ConsoleReporter
{
    private readonly object _lock = new();

    /// <summary>
    /// Writes a complete prefixed line atomically to the console.
    /// </summary>
    public void WriteLineWithPrefix(string sampleName, string message, ConsoleColor? color = null)
    {
        lock (this._lock)
        {
            Console.ForegroundColor = ConsoleColor.Cyan;
            Console.Write($"[{sampleName}] ");
            if (color.HasValue)
            {
                Console.ForegroundColor = color.Value;
            }
            else
            {
                Console.ResetColor();
            }

            Console.WriteLine(message);
            Console.ResetColor();
        }
    }

    /// <summary>
    /// Prints the final summary table and elapsed time to the console.
    /// </summary>
    public void PrintSummary(
        IReadOnlyList<VerificationResult> orderedResults,
        IReadOnlyList<(string Name, string Reason)> skipped,
        TimeSpan elapsed)
    {
        var passCount = orderedResults.Count(r => r.Passed);
        var failCount = orderedResults.Count(r => !r.Passed);

        Console.WriteLine();
        Console.WriteLine(new string('─', 60));
        Console.ForegroundColor = ConsoleColor.White;
        Console.WriteLine("SUMMARY");
        Console.ResetColor();

        foreach (var result in orderedResults)
        {
            Console.ForegroundColor = result.Passed ? ConsoleColor.Green : ConsoleColor.Red;
            Console.Write(result.Passed ? "  ✓ " : "  ✗ ");
            Console.ResetColor();
            Console.WriteLine($"{result.SampleName}: {result.Summary}");
        }

        foreach (var (name, reason) in skipped)
        {
            Console.ForegroundColor = ConsoleColor.Yellow;
            Console.Write("  ○ ");
            Console.ResetColor();
            Console.WriteLine($"{name}: Skipped — {reason}");
        }

        Console.WriteLine();
        Console.Write("Results: ");
        Console.ForegroundColor = ConsoleColor.Green;
        Console.Write($"{passCount} passed");
        Console.ResetColor();

        if (failCount > 0)
        {
            Console.Write(", ");
            Console.ForegroundColor = ConsoleColor.Red;
            Console.Write($"{failCount} failed");
            Console.ResetColor();
        }

        if (skipped.Count > 0)
        {
            Console.Write(", ");
            Console.ForegroundColor = ConsoleColor.Yellow;
            Console.Write($"{skipped.Count} skipped");
            Console.ResetColor();
        }

        Console.WriteLine();
        Console.ForegroundColor = ConsoleColor.DarkGray;
        Console.WriteLine($"Elapsed: {elapsed.Hours:D2}:{elapsed.Minutes:D2}:{elapsed.Seconds:D2}");
        Console.ResetColor();
    }
}
