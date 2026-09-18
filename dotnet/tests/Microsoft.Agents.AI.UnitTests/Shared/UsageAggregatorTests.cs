// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.UnitTests;

/// <summary>
/// Unit tests for <see cref="UsageAggregator"/>.
/// </summary>
public class UsageAggregatorTests
{
    /// <summary>
    /// Verify that combining two null usage values returns null.
    /// </summary>
    [Fact]
    public void Combine_BothInputsNull_ReturnsNull()
    {
        // Arrange, Act
        UsageDetails? result = UsageAggregator.Combine(null, null);

        // Assert
        Assert.Null(result);
    }

    /// <summary>
    /// Verify that combining one null usage value returns a new copy of the non-null usage value.
    /// </summary>
    [Theory]
    [InlineData(true)]
    [InlineData(false)]
    public void Combine_OneInputNull_ReturnsNewCopy(bool currentIsNull)
    {
        // Arrange
        UsageDetails usage = CreateUsage(2, 3, 5, new() { ["cached"] = 7 });
        UsageSnapshot before = UsageSnapshot.Capture(usage);

        // Act
        UsageDetails? result = currentIsNull
            ? UsageAggregator.Combine(null, usage)
            : UsageAggregator.Combine(usage, null);

        // Assert
        Assert.NotNull(result);
        Assert.NotSame(usage, result);
        Assert.NotSame(usage.AdditionalCounts, result!.AdditionalCounts);
        Assert.Equal(2, result.InputTokenCount);
        Assert.Equal(3, result.OutputTokenCount);
        Assert.Equal(5, result.TotalTokenCount);
        Assert.Equal(7, result.AdditionalCounts!["cached"]);
        Assert.Equal(before, UsageSnapshot.Capture(usage));
    }

    /// <summary>
    /// Verify that token counts are summed while preserving null as not reported.
    /// </summary>
    [Fact]
    public void Combine_TokenCounts_SumsNullAware()
    {
        // Arrange
        UsageDetails current = CreateUsage(input: 2, output: null, total: null);
        UsageDetails incoming = CreateUsage(input: 11, output: 5, total: null);

        // Act
        UsageDetails? result = UsageAggregator.Combine(current, incoming);

        // Assert
        Assert.NotNull(result);
        Assert.NotSame(current, result);
        Assert.NotSame(incoming, result);
        Assert.Equal(13, result!.InputTokenCount);
        Assert.Equal(5, result.OutputTokenCount);
        Assert.Null(result.TotalTokenCount);
    }

    /// <summary>
    /// Verify that additional counts are summed per key and preserve disjoint keys.
    /// </summary>
    [Fact]
    public void Combine_AdditionalCounts_SumsOverlappingAndUnionsDisjointKeys()
    {
        // Arrange
        UsageDetails current = CreateUsage(input: null, output: null, total: null, new() { ["cached"] = 2, ["reasoning"] = 3 });
        UsageDetails incoming = CreateUsage(input: null, output: null, total: null, new() { ["cached"] = 11, ["audio"] = 29 });

        // Act
        UsageDetails? result = UsageAggregator.Combine(current, incoming);

        // Assert
        Assert.NotNull(result);
        Assert.NotSame(current.AdditionalCounts, result!.AdditionalCounts);
        Assert.NotSame(incoming.AdditionalCounts, result.AdditionalCounts);
        Assert.Equal(13, result.AdditionalCounts!["cached"]);
        Assert.Equal(3, result.AdditionalCounts["reasoning"]);
        Assert.Equal(29, result.AdditionalCounts["audio"]);
    }

    /// <summary>
    /// Verify that additional counts are handled when one or both sides do not report any keys.
    /// </summary>
    [Fact]
    public void Combine_AdditionalCounts_HandlesNullDictionaries()
    {
        // Arrange
        UsageDetails withCounts = CreateUsage(input: null, output: null, total: null, new() { ["cached"] = 7 });
        UsageDetails withoutCounts = CreateUsage(input: 1, output: 2, total: 3);

        // Act
        UsageDetails? oneSide = UsageAggregator.Combine(withoutCounts, withCounts);
        UsageDetails? bothSides = UsageAggregator.Combine(withoutCounts, CreateUsage(input: null, output: null, total: null));

        // Assert
        Assert.NotNull(oneSide);
        Assert.Equal(7, oneSide!.AdditionalCounts!["cached"]);
        Assert.NotNull(bothSides);
        Assert.Null(bothSides!.AdditionalCounts);
    }

    /// <summary>
    /// Verify that combining does not mutate either input usage or additional-count dictionary.
    /// </summary>
    [Fact]
    public void Combine_DoesNotMutateInputs()
    {
        // Arrange
        UsageDetails current = CreateUsage(2, 3, 5, new() { ["cached"] = 7, ["reasoning"] = 11 });
        UsageDetails incoming = CreateUsage(13, null, 17, new() { ["cached"] = 19, ["audio"] = 23 });
        UsageSnapshot currentBefore = UsageSnapshot.Capture(current);
        UsageSnapshot incomingBefore = UsageSnapshot.Capture(incoming);

        // Act
        UsageDetails? result = UsageAggregator.Combine(current, incoming);

        // Assert
        Assert.NotNull(result);
        Assert.Equal(currentBefore, UsageSnapshot.Capture(current));
        Assert.Equal(incomingBefore, UsageSnapshot.Capture(incoming));
    }

    /// <summary>
    /// Verify that accumulating usage replaces the running aggregate with new combined instances.
    /// </summary>
    [Fact]
    public void Accumulate_SeveralAccumulations_UpdatesAggregate()
    {
        // Arrange
        UsageDetails? aggregate = null;
        UsageDetails first = CreateUsage(2, 3, 5, new() { ["cached"] = 7 });
        UsageDetails second = CreateUsage(11, null, 16, new() { ["cached"] = 13, ["audio"] = 17 });
        UsageDetails third = CreateUsage(null, 29, null);

        // Act
        UsageAggregator.Accumulate(ref aggregate, first);
        UsageDetails firstAggregate = aggregate!;
        UsageAggregator.Accumulate(ref aggregate, null);
        UsageDetails secondAggregate = aggregate!;
        UsageAggregator.Accumulate(ref aggregate, second);
        UsageAggregator.Accumulate(ref aggregate, third);

        // Assert
        Assert.NotSame(first, firstAggregate);
        Assert.NotSame(firstAggregate, secondAggregate);
        Assert.Equal(13, aggregate!.InputTokenCount);
        Assert.Equal(32, aggregate.OutputTokenCount);
        Assert.Equal(21, aggregate.TotalTokenCount);
        Assert.Equal(20, aggregate.AdditionalCounts!["cached"]);
        Assert.Equal(17, aggregate.AdditionalCounts["audio"]);
    }

    /// <summary>
    /// Verify that every strongly-typed counter exposed by <see cref="UsageDetails"/> is summed, not just the
    /// three headline token counts. Providers such as the GitHub Copilot agent report
    /// <see cref="UsageDetails.CachedInputTokenCount"/>, and reasoning tokens are common for OpenAI-family
    /// models, so dropping any of these would silently lose provider-reported data.
    /// </summary>
    [Fact]
    public void Combine_SumsAllStronglyTypedCounters()
    {
        // Arrange
        UsageDetails current = new()
        {
            InputTokenCount = 1,
            OutputTokenCount = 2,
            TotalTokenCount = 3,
            CachedInputTokenCount = 4,
            ReasoningTokenCount = 5,
            InputAudioTokenCount = 6,
            InputTextTokenCount = 7,
            OutputAudioTokenCount = 8,
            OutputTextTokenCount = 9,
        };
        UsageDetails incoming = new()
        {
            InputTokenCount = 10,
            OutputTokenCount = 20,
            TotalTokenCount = 30,
            CachedInputTokenCount = 40,
            ReasoningTokenCount = 50,
            InputAudioTokenCount = 60,
            InputTextTokenCount = 70,
            OutputAudioTokenCount = 80,
            OutputTextTokenCount = 90,
        };

        // Act
        UsageDetails? result = UsageAggregator.Combine(current, incoming);

        // Assert
        Assert.NotNull(result);
        Assert.Equal(11, result!.InputTokenCount);
        Assert.Equal(22, result.OutputTokenCount);
        Assert.Equal(33, result.TotalTokenCount);
        Assert.Equal(44, result.CachedInputTokenCount);
        Assert.Equal(55, result.ReasoningTokenCount);
        Assert.Equal(66, result.InputAudioTokenCount);
        Assert.Equal(77, result.InputTextTokenCount);
        Assert.Equal(88, result.OutputAudioTokenCount);
        Assert.Equal(99, result.OutputTextTokenCount);
    }

    /// <summary>
    /// Verify that the extra strongly-typed counters survive a merge where only one side reports them, which
    /// is the common case when a single iteration of a loop reports cached or reasoning tokens.
    /// </summary>
    [Fact]
    public void Combine_OneSideOnlyReportsExtraCounters_PreservesThem()
    {
        // Arrange
        UsageDetails current = new() { InputTokenCount = 5 };
        UsageDetails incoming = new() { InputTokenCount = 6, CachedInputTokenCount = 3, ReasoningTokenCount = 4 };

        // Act
        UsageDetails? result = UsageAggregator.Combine(current, incoming);

        // Assert
        Assert.NotNull(result);
        Assert.Equal(11, result!.InputTokenCount);
        Assert.Equal(3, result.CachedInputTokenCount);
        Assert.Equal(4, result.ReasoningTokenCount);
    }

    /// <summary>
    /// <see cref="UsageAggregator.Combine"/> intentionally mirrors the semantics of
    /// <see cref="UsageDetails.Add"/> (which is what <c>FunctionInvokingChatClient</c> uses to aggregate usage
    /// across its own function-calling turns) while avoiding that method's in-place mutation. This asserts the
    /// two agree for every combination of reported and unreported counters.
    /// </summary>
    [Theory]
    [InlineData(true, true)]
    [InlineData(true, false)]
    [InlineData(false, true)]
    public void Combine_MatchesUsageDetailsAddSemantics(bool currentReported, bool incomingReported)
    {
        // Arrange
        UsageDetails? current = currentReported ? CreateFullyPopulatedUsage(1) : null;
        UsageDetails? incoming = incomingReported ? CreateFullyPopulatedUsage(100) : null;

        UsageDetails expected = new();
        if (current is not null)
        {
            expected.Add(current);
        }

        if (incoming is not null)
        {
            expected.Add(incoming);
        }

        // Act
        UsageDetails? actual = UsageAggregator.Combine(current, incoming);

        // Assert
        Assert.NotNull(actual);
        foreach (var property in GetTokenCountProperties())
        {
            Assert.Equal((long?)property.GetValue(expected), (long?)property.GetValue(actual));
        }

        Assert.Equal(
            expected.AdditionalCounts?.OrderBy(static e => e.Key).Select(static e => $"{e.Key}:{e.Value}") ?? [],
            actual.AdditionalCounts?.OrderBy(static e => e.Key).Select(static e => $"{e.Key}:{e.Value}") ?? []);
    }

    /// <summary>
    /// Guards against a future <see cref="UsageDetails"/> counter being added upstream without being summed here.
    /// Because every fix site reports a freshly combined instance on the response, an uncombined counter
    /// would be silently dropped even on single-iteration runs.
    /// </summary>
    [Fact]
    public void Combine_SumsEveryTokenCountPropertyExposedByUsageDetails()
    {
        // Arrange
        UsageDetails current = CreateFullyPopulatedUsage(1);
        UsageDetails incoming = CreateFullyPopulatedUsage(100);

        // Act
        UsageDetails? merged = UsageAggregator.Combine(current, incoming);

        // Assert
        var properties = GetTokenCountProperties().ToList();
        Assert.NotEmpty(properties);
        Assert.NotNull(merged);
        foreach (var property in properties)
        {
            long? currentValue = (long?)property.GetValue(current);
            long? incomingValue = (long?)property.GetValue(incoming);
            Assert.Equal(currentValue + incomingValue, (long?)property.GetValue(merged));
        }
    }

    private static IEnumerable<PropertyInfo> GetTokenCountProperties()
        => typeof(UsageDetails)
            .GetProperties(BindingFlags.Public | BindingFlags.Instance)
            .Where(static p => p.PropertyType == typeof(long?) && p.CanRead && p.CanWrite);

    /// <summary>
    /// Assigns a distinct value to every settable <see cref="long"/> counter so that a counter which is not
    /// summed by <see cref="UsageAggregator.Combine"/> produces a detectable mismatch.
    /// </summary>
    private static UsageDetails CreateFullyPopulatedUsage(long seed)
    {
        UsageDetails usage = new();
        long offset = 0;
        foreach (var property in GetTokenCountProperties())
        {
            property.SetValue(usage, seed + offset++);
        }

        usage.AdditionalCounts = new() { ["provider_specific"] = seed };
        return usage;
    }

    private sealed record UsageSnapshot(long? Input, long? Output, long? Total, string AdditionalCounts)
    {
        public static UsageSnapshot Capture(UsageDetails usage)
            => new(
                usage.InputTokenCount,
                usage.OutputTokenCount,
                usage.TotalTokenCount,
                string.Join(
                    "|",
                    usage.AdditionalCounts?.OrderBy(static entry => entry.Key).Select(static entry => $"{entry.Key}:{entry.Value}") ?? []));
    }

    private static UsageDetails CreateUsage(long? input, long? output, long? total, AdditionalPropertiesDictionary<long>? additionalCounts = null)
    {
        UsageDetails usage = new()
        {
            InputTokenCount = input,
            OutputTokenCount = output,
            TotalTokenCount = total,
        };

        if (additionalCounts is not null)
        {
            usage.AdditionalCounts = additionalCounts;
        }

        return usage;
    }
}
