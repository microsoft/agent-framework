// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI;

/// <summary>
/// Combines <see cref="UsageDetails"/> reported by the individual service or agent invocations that make up
/// a single logical run.
/// </summary>
/// <remarks>
/// Several components re-invoke an inner agent or chat client in a loop within a single run (for example
/// when auto-approving tool calls, injecting messages, or re-running an agent until an evaluator is
/// satisfied). Each inner invocation reports its own usage, and the aggregate must be surfaced to the
/// caller so that the reported token counts reflect the entire run rather than just its final step.
/// </remarks>
internal static class UsageAggregator
{
    /// <summary>
    /// Combines two <see cref="UsageDetails"/> instances into a new instance containing their summed values.
    /// </summary>
    /// <param name="current">The running aggregate, or <see langword="null"/> if nothing has been accumulated yet.</param>
    /// <param name="incoming">The usage reported by the latest invocation, or <see langword="null"/> if none was reported.</param>
    /// <returns>
    /// A new <see cref="UsageDetails"/> containing the summed token counts and additional counts, or
    /// <see langword="null"/> when both <paramref name="current"/> and <paramref name="incoming"/> are
    /// <see langword="null"/>.
    /// </returns>
    /// <remarks>
    /// Neither argument is mutated, and neither argument is ever returned by reference, since both may be
    /// owned and observed by callers and <see cref="UsageDetails.Add"/> combines in place. Every
    /// strongly-typed counter exposed by <see cref="UsageDetails"/> is summed, matching the set covered by
    /// <see cref="UsageDetails.Add"/>, so that no provider-reported counter is lost when a combined instance
    /// replaces the original. Token counts are summed in a null-aware manner: combining a
    /// <see langword="null"/> count with a non-null count yields the non-null count, and combining two
    /// <see langword="null"/> counts yields <see langword="null"/>. Entries in
    /// <see cref="UsageDetails.AdditionalCounts"/> are summed per key so that provider-specific counters
    /// (such as cached, reasoning, or cost counters) aggregate correctly.
    /// </remarks>
    public static UsageDetails? Combine(UsageDetails? current, UsageDetails? incoming)
    {
        if (current is null && incoming is null)
        {
            return null;
        }

        var combined = new UsageDetails
        {
            InputTokenCount = AddCounts(current?.InputTokenCount, incoming?.InputTokenCount),
            OutputTokenCount = AddCounts(current?.OutputTokenCount, incoming?.OutputTokenCount),
            TotalTokenCount = AddCounts(current?.TotalTokenCount, incoming?.TotalTokenCount),
            CachedInputTokenCount = AddCounts(current?.CachedInputTokenCount, incoming?.CachedInputTokenCount),
            ReasoningTokenCount = AddCounts(current?.ReasoningTokenCount, incoming?.ReasoningTokenCount),
            InputAudioTokenCount = AddCounts(current?.InputAudioTokenCount, incoming?.InputAudioTokenCount),
            InputTextTokenCount = AddCounts(current?.InputTextTokenCount, incoming?.InputTextTokenCount),
            OutputAudioTokenCount = AddCounts(current?.OutputAudioTokenCount, incoming?.OutputAudioTokenCount),
            OutputTextTokenCount = AddCounts(current?.OutputTextTokenCount, incoming?.OutputTextTokenCount),
        };

        AdditionalPropertiesDictionary<long>? additionalCounts = CombineAdditionalCounts(current?.AdditionalCounts, incoming?.AdditionalCounts);
        if (additionalCounts is not null)
        {
            combined.AdditionalCounts = additionalCounts;
        }

        return combined;
    }

    /// <summary>
    /// Adds the <paramref name="incoming"/> usage into the running aggregate referenced by
    /// <paramref name="current"/>, replacing it with a new combined instance.
    /// </summary>
    /// <param name="current">The running aggregate to update. May be <see langword="null"/>.</param>
    /// <param name="incoming">The usage reported by the latest invocation, or <see langword="null"/> if none was reported.</param>
    public static void Accumulate(ref UsageDetails? current, UsageDetails? incoming)
        => current = Combine(current, incoming);

    /// <summary>
    /// Adds two nullable counts, treating <see langword="null"/> as "not reported" rather than as zero so
    /// that an aggregate only reports a count when at least one contributor reported one.
    /// </summary>
    private static long? AddCounts(long? current, long? incoming)
        => current is null ? incoming : incoming is null ? current : current + incoming;

    /// <summary>
    /// Produces a new dictionary containing the per-key sums of the supplied additional counts, or
    /// <see langword="null"/> when neither side has any entries.
    /// </summary>
    private static AdditionalPropertiesDictionary<long>? CombineAdditionalCounts(
        AdditionalPropertiesDictionary<long>? current,
        AdditionalPropertiesDictionary<long>? incoming)
    {
        bool hasCurrent = current is { Count: > 0 };
        bool hasIncoming = incoming is { Count: > 0 };

        if (!hasCurrent && !hasIncoming)
        {
            return null;
        }

        var combined = new AdditionalPropertiesDictionary<long>();

        if (hasCurrent)
        {
            foreach (var entry in current!)
            {
                combined[entry.Key] = entry.Value;
            }
        }

        if (hasIncoming)
        {
            foreach (var entry in incoming!)
            {
                combined[entry.Key] = combined.TryGetValue(entry.Key, out long existing)
                    ? existing + entry.Value
                    : entry.Value;
            }
        }

        return combined;
    }
}
