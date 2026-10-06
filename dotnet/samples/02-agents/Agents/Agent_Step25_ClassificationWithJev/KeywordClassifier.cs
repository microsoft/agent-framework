// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics.CodeAnalysis;

/// <summary>
/// A local classifier that stands in for another classification client. It has its own request and response types,
/// knows nothing about Jev, and needs no network: it scores each option by the words it shares with the text.
/// </summary>
[SuppressMessage("Performance", "CA1812:Avoid uninstantiated internal classes", Justification = "Instantiated by the service provider")]
internal sealed class KeywordClassifier
{
    private static readonly char[] s_separators = [' ', ',', '.', '!', '?', ';', ':', '\'', '"', '(', ')', '-', '\n', '\r', '\t'];

    public Task<ClassificationResponse> ClassifyAsync(ClassificationRequest request, CancellationToken cancellationToken)
    {
        HashSet<string> words = Words(request.Text);
        var results = new Dictionary<string, ClassificationResult>();
        foreach (ClassificationTask task in request.Tasks)
        {
            // One point per shared word, plus one so that every option keeps some probability.
            double[] points = [.. task.Options.Select(option => Words(option.Description).Count(words.Contains) + 1.0)];
            double total = points.Sum();
            results[task.Id] = new ClassificationResult(
                task.Kind,
                [.. task.Options.Select((option, index) => new ScoredOption(option.Key, option.Description, points[index] / total))]);
        }

        return Task.FromResult(new ClassificationResponse(results));
    }

    // Words are compared in upper case and without a plural "S", so "invoice" matches "invoices".
    private static HashSet<string> Words(string text) =>
        [.. text.ToUpperInvariant().Split(s_separators, StringSplitOptions.RemoveEmptyEntries).Where(word => word.Length > 3).Select(word => word.TrimEnd('S'))];
}

/// <summary>What the classifier decides for one task.</summary>
internal enum ClassificationKind
{
    PickOne,
    Rate,
    YesNo,
}

/// <summary>The classifier's request: the text and the tasks to decide about it.</summary>
internal sealed record ClassificationRequest(string Text, IReadOnlyList<ClassificationTask> Tasks);

/// <summary>One task: pick one option, rate on ordered options, or decide yes or no.</summary>
internal sealed record ClassificationTask(string Id, ClassificationKind Kind, IReadOnlyList<ClassificationOption> Options);

/// <summary>An option of a task and the words that describe it.</summary>
internal sealed record ClassificationOption(string Key, string Description);

/// <summary>The classifier's response: one result per task, by task ID.</summary>
internal sealed record ClassificationResponse(IReadOnlyDictionary<string, ClassificationResult> Results);

/// <summary>The result of one task: every option with its probability.</summary>
internal sealed record ClassificationResult(ClassificationKind Kind, IReadOnlyList<ScoredOption> Options);

/// <summary>An option with the probability that the classifier gives it.</summary>
internal sealed record ScoredOption(string Key, string Description, double Probability);
