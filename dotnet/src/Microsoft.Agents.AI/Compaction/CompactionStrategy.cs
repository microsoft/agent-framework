// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics;
using System.Diagnostics.CodeAnalysis;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Shared.DiagnosticIds;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Compaction;

/// <summary>
/// Base class for strategies that compact a <see cref="MessageIndex"/> to reduce context size.
/// </summary>
/// <remarks>
/// <para>
/// Compaction strategies operate on <see cref="MessageIndex"/> instances, which organize messages
/// into atomic groups that respect the tool-call/result pairing constraint. Strategies mutate the collection
/// in place by marking groups as excluded, removing groups, or replacing message content (e.g., with summaries).
/// </para>
/// <para>
/// Every strategy requires a <see cref="CompactionTrigger"/> that determines whether compaction should
/// proceed based on current <see cref="MessageIndex"/> metrics (token count, message count, turn count, etc.).
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
/// Multiple strategies can be composed by applying them sequentially to the same <see cref="MessageIndex"/>
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
    /// Evaluates the <see cref="Trigger"/> and, when it fires, delegates to
    /// <see cref="ApplyCompactionAsync"/> and reports compaction metrics.
    /// </summary>
    /// <param name="index">The message index to compact. The strategy mutates this collection in place.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests.</param>
    /// <returns>A task representing the asynchronous operation. The task result is <see langword="true"/> if compaction occurred, <see langword="false"/> otherwise.</returns>
    public async Task<bool> CompactAsync(MessageIndex index, CancellationToken cancellationToken = default)
    {
        if (!this.Trigger(index))
        {
            return false;
        }

        int beforeTokens = index.IncludedTokenCount;
        int beforeGroups = index.IncludedGroupCount;
        int beforeMessages = index.IncludedMessageCount;

        Stopwatch stopwatch = Stopwatch.StartNew();

        bool compacted = await this.ApplyCompactionAsync(index, cancellationToken).ConfigureAwait(false);

        stopwatch.Stop();

        if (compacted)
        {
            Debug.WriteLine(
                $"""
                COMPACTION: {this.GetType().Name}                
                    Duration {stopwatch.ElapsedMilliseconds}ms
                    Messages {beforeMessages} => {index.IncludedMessageCount}
                    Groups {beforeGroups} => {index.IncludedGroupCount}
                    Tokens {beforeTokens} => {index.IncludedTokenCount}
                """);
        }

        return compacted;
    }

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
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests.</param>
    /// <returns>A task whose result is <see langword="true"/> if any compaction was performed, <see langword="false"/> otherwise.</returns>
    protected abstract Task<bool> ApplyCompactionAsync(MessageIndex index, CancellationToken cancellationToken);
}
