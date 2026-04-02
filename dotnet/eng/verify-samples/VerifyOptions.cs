// Copyright (c) Microsoft. All rights reserved.

namespace VerifySamples;

/// <summary>
/// Parsed command-line options for the sample verification tool.
/// </summary>
internal sealed class VerifyOptions
{
    /// <summary>
    /// Maximum number of samples to run concurrently.
    /// </summary>
    public int MaxParallelism { get; init; } = 8;

    /// <summary>
    /// Path to write a CSV summary file, or <c>null</c> to skip.
    /// </summary>
    public string? CsvFilePath { get; init; }

    /// <summary>
    /// Path to write a sequential log file, or <c>null</c> to skip.
    /// </summary>
    public string? LogFilePath { get; init; }

    /// <summary>
    /// The filtered list of samples to process.
    /// </summary>
    public required IReadOnlyList<SampleDefinition> Samples { get; init; }

    /// <summary>
    /// All known sample set registries, keyed by category name.
    /// </summary>
    private static readonly Dictionary<string, IReadOnlyList<SampleDefinition>> s_sampleSets =
        new(StringComparer.OrdinalIgnoreCase)
        {
            ["01-get-started"] = GetStartedSamples.All,
            ["02-agents"] = AgentsSamples.All,
            ["03-workflows"] = WorkflowSamples.All,
        };

    /// <summary>
    /// Parses command-line arguments and resolves the sample list.
    /// Returns <c>null</c> and writes to stderr if the arguments are invalid.
    /// </summary>
    public static VerifyOptions? Parse(string[] args)
    {
        var argList = args.ToList();

        var categoryFilter = ExtractArg(argList, "--category");
        var logFilePath = ExtractArg(argList, "--log");
        var csvFilePath = ExtractArg(argList, "--csv");

        int maxParallelism = 8;
        var parallelArg = ExtractArg(argList, "--parallel");
        if (parallelArg is not null && int.TryParse(parallelArg, out var p) && p > 0)
        {
            maxParallelism = p;
        }

        HashSet<string>? nameFilter = null;
        if (argList.Count > 0)
        {
            nameFilter = argList.ToHashSet(StringComparer.OrdinalIgnoreCase);
        }

        // Build the sample list
        IReadOnlyList<SampleDefinition> samples;
        if (categoryFilter is not null)
        {
            if (!s_sampleSets.TryGetValue(categoryFilter, out var categoryList))
            {
                Console.Error.WriteLine(
                    $"Unknown category '{categoryFilter}'. Available: {string.Join(", ", s_sampleSets.Keys)}");
                return null;
            }

            samples = categoryList;
        }
        else
        {
            samples = s_sampleSets.Values.SelectMany(s => s).ToList();
        }

        if (nameFilter is not null)
        {
            samples = samples.Where(s => nameFilter.Contains(s.Name)).ToList();
        }

        if (samples.Count == 0)
        {
            var allNames = s_sampleSets.Values.SelectMany(s => s).Select(s => s.Name);
            Console.Error.WriteLine($"No matching samples found. Available: {string.Join(", ", allNames)}");
            return null;
        }

        return new VerifyOptions
        {
            MaxParallelism = maxParallelism,
            LogFilePath = logFilePath,
            CsvFilePath = csvFilePath,
            Samples = samples,
        };
    }

    private static string? ExtractArg(List<string> list, string flag)
    {
        var idx = list.IndexOf(flag);
        if (idx < 0)
        {
            return null;
        }

        if (idx + 1 >= list.Count)
        {
            Console.Error.WriteLine($"Missing value for {flag}.");
            list.RemoveAt(idx);
            return null;
        }

        var value = list[idx + 1];
        list.RemoveRange(idx, 2);
        return value;
    }
}
