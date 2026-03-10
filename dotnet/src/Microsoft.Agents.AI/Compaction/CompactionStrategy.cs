// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Diagnostics;
using System.Diagnostics.CodeAnalysis;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Logging.Abstractions;
using Microsoft.Shared.DiagnosticIds;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Compaction;

/// <summary>
/// Base class for strategies that compact a <see cref="CompactionMessageIndex"/> to reduce context size.
/// </summary>
/// <remarks>
/// <para>
/// Compaction strategies operate on <see cref="CompactionMessageIndex"/> instances, which organize messages
/// into atomic groups that respect the tool-call/result pairing constraint. Strategies mutate the collection
/// in place by marking groups as excluded, removing groups, or replacing message content (e.g., with summaries).
/// </para>
/// <para>
/// Every strategy requires a <see cref="CompactionTrigger"/> that determines whether compaction should
/// proceed based on current <see cref="CompactionMessageIndex"/> metrics (token count, message count, turn count, etc.).
/// The base class evaluates this trigger at the start of <see cref="CompactAsync"/> and skips compaction when
/// the trigger returns <see langword="false"/>.
/// </para>
/// <para>
/// An optional <b>target</b> condition controls when compaction stops. Strategies incrementally exclude
/// groups and re-evaluate the target after each exclusion, stopping as soon as the target returns
/// <see langword="true"/>. When no target is specified, it defaults to the inverse of the trigger —
/// meaning compaction stops when the trigger condition would no longer fire.
/// </para>
/// <para>
/// Strategies can be applied at three lifecycle points:
/// <list type="bullet">
/// <item><description><b>In-run</b>: During the tool loop, before each LLM call, to keep context within token limits.</description></item>
/// <item><description><b>Pre-write</b>: Before persisting messages to storage via <see cref="ChatHistoryProvider"/>.</description></item>
/// <item><description><b>On existing storage</b>: As a maintenance operation to compact stored history.</description></item>
/// </list>
/// </para>
/// <para>
/// Multiple strategies can be composed by applying them sequentially to the same <see cref="CompactionMessageIndex"/>
/// via <see cref="PipelineCompactionStrategy"/>.
/// </para>
/// </remarks>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public abstract class CompactionStrategy
{
    /// <summary>
    /// Initializes a new instance of the <see cref="CompactionStrategy"/> class.
    /// </summary>
    /// <param name="trigger">
    /// The <see cref="CompactionTrigger"/> that determines whether compaction should proceed.
    /// </param>
    /// <param name="target">
    /// An optional target condition that controls when compaction stops. Strategies re-evaluate
    /// this predicate after each incremental exclusion and stop when it returns <see langword="true"/>.
    /// When <see langword="null"/>, defaults to the inverse of the <paramref name="trigger"/> — compaction
    /// stops as soon as the trigger condition would no longer fire.
    /// </param>
    protected CompactionStrategy(CompactionTrigger trigger, CompactionTrigger? target = null)
    {
        this.Trigger = Throw.IfNull(trigger);
        this.Target = target ?? (index => !trigger(index));
    }

    /// <summary>
    /// Gets the trigger predicate that controls when compaction proceeds.
    /// </summary>
    protected CompactionTrigger Trigger { get; }

    /// <summary>
    /// Gets the target predicate that controls when compaction stops.
    /// Strategies re-evaluate this after each incremental exclusion and stop when it returns <see langword="true"/>.
    /// </summary>
    protected CompactionTrigger Target { get; }

    /// <summary>
    /// Applies the strategy-specific compaction logic to the specified message index.
    /// </summary>
    /// <remarks>
    /// This method is called by <see cref="CompactAsync"/> only when the <see cref="Trigger"/>
    /// returns <see langword="true"/>. Implementations do not need to evaluate the trigger or
    /// report metrics — the base class handles both. Implementations should use <see cref="Target"/>
    /// to determine when to stop compacting incrementally.
    /// </remarks>
    /// <param name="index">The message index to compact. The strategy mutates this collection in place.</param>
    /// <param name="logger">The <see cref="ILogger"/> for emitting compaction diagnostics.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests.</param>
    /// <returns>A task whose result is <see langword="true"/> if any compaction was performed, <see langword="false"/> otherwise.</returns>
    protected abstract ValueTask<bool> CompactCoreAsync(CompactionMessageIndex index, ILogger logger, CancellationToken cancellationToken);

    /// <summary>
    /// Evaluates the <see cref="Trigger"/> and, when it fires, delegates to
    /// <see cref="CompactCoreAsync"/> and reports compaction metrics.
    /// </summary>
    /// <param name="index">The message index to compact. The strategy mutates this collection in place.</param>
    /// <param name="logger">An optional <see cref="ILogger"/> for emitting compaction diagnostics. When <see langword="null"/>, logging is disabled.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests.</param>
    /// <returns>A task representing the asynchronous operation. The task result is <see langword="true"/> if compaction occurred, <see langword="false"/> otherwise.</returns>
    public async ValueTask<bool> CompactAsync(CompactionMessageIndex index, ILogger? logger = null, CancellationToken cancellationToken = default)
    {
        string strategyName = this.GetType().Name;
        logger ??= NullLogger.Instance;

        using Activity? activity = CompactionTelemetry.ActivitySource.StartActivity(CompactionTelemetry.ActivityNames.Compact);
        activity?.SetTag(CompactionTelemetry.Tags.Strategy, strategyName);

        if (index.IncludedNonSystemGroupCount <= 1 || !this.Trigger(index))
        {
            activity?.SetTag(CompactionTelemetry.Tags.Triggered, false);
            logger.LogCompactionSkipped(strategyName);
            return false;
        }

        activity?.SetTag(CompactionTelemetry.Tags.Triggered, true);

        int beforeTokens = index.IncludedTokenCount;
        int beforeGroups = index.IncludedGroupCount;
        int beforeMessages = index.IncludedMessageCount;

        Stopwatch stopwatch = Stopwatch.StartNew();

        bool compacted = await this.CompactCoreAsync(index, logger, cancellationToken).ConfigureAwait(false);

        stopwatch.Stop();

        activity?.SetTag(CompactionTelemetry.Tags.Compacted, compacted);

        if (compacted)
        {
            activity?
                .SetTag(CompactionTelemetry.Tags.BeforeTokens, beforeTokens)
                .SetTag(CompactionTelemetry.Tags.AfterTokens, index.IncludedTokenCount)
                .SetTag(CompactionTelemetry.Tags.BeforeMessages, beforeMessages)
                .SetTag(CompactionTelemetry.Tags.AfterMessages, index.IncludedMessageCount)
                .SetTag(CompactionTelemetry.Tags.BeforeGroups, beforeGroups)
                .SetTag(CompactionTelemetry.Tags.AfterGroups, index.IncludedGroupCount)
                .SetTag(CompactionTelemetry.Tags.DurationMs, stopwatch.ElapsedMilliseconds);

            logger.LogCompactionCompleted(
                strategyName,
                stopwatch.ElapsedMilliseconds,
                beforeMessages,
                index.IncludedMessageCount,
                beforeGroups,
                index.IncludedGroupCount,
                beforeTokens,
                index.IncludedTokenCount);
        }

        return compacted;
    }

    /// <summary>
    /// Ensures the provided value is not a negative number.
    /// </summary>
    /// <param name="value">The target value.</param>
    /// <returns>0 if negative; otherwise the value</returns>
    protected static int EnsureNonNegative(int value) => Math.Max(0, value);
}
