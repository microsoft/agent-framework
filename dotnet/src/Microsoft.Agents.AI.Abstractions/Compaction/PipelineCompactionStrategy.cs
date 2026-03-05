// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Compaction;

/// <summary>
/// A compaction strategy that executes a sequential pipeline of <see cref="ICompactionStrategy"/> instances
/// against the same <see cref="MessageIndex"/>.
/// </summary>
/// <remarks>
/// <para>
/// Each strategy in the pipeline operates on the result of the previous one, enabling composed behaviors
/// such as summarizing older messages first and then truncating to fit a token budget.
/// </para>
/// <para>
/// When <see cref="EarlyStop"/> is <see langword="true"/> and a <see cref="TargetIncludedGroupCount"/> is configured,
/// the pipeline stops executing after a strategy reduces the included group count to or below the target.
/// This avoids unnecessary work when an earlier strategy is sufficient.
/// </para>
/// </remarks>
public sealed class PipelineCompactionStrategy : ICompactionStrategy
{
    /// <summary>
    /// Initializes a new instance of the <see cref="PipelineCompactionStrategy"/> class.
    /// </summary>
    /// <param name="strategies">The ordered sequence of strategies to execute. Must not be empty.</param>
    ///// <param name="cache">An optional cache for <see cref="MessageIndex"/> instances. When <see langword="null"/>, a default <see cref="InMemoryMessageIndexCache"/> is created.</param>
    public PipelineCompactionStrategy(params IEnumerable<ICompactionStrategy> strategies/*, IMessageIndexCache? cache = null*/)
    {
        this.Strategies = [.. Throw.IfNull(strategies)];
    }

    /// <summary>
    /// Gets the ordered list of strategies in this pipeline.
    /// </summary>
    public IReadOnlyList<ICompactionStrategy> Strategies { get; }

    /// <summary>
    /// Gets or sets a value indicating whether the pipeline should stop executing after a strategy
    /// brings the included group count to or below <see cref="TargetIncludedGroupCount"/>.
    /// </summary>
    /// <value>
    /// Defaults to <see langword="false"/>, meaning all strategies are always executed.
    /// </value>
    public bool EarlyStop { get; set; }

    /// <summary>
    /// Gets or sets the target number of included groups at which the pipeline stops
    /// when <see cref="EarlyStop"/> is <see langword="true"/>.
    /// </summary>
    /// <value>
    /// Defaults to <see langword="null"/>, meaning early stop checks are not performed
    /// even when <see cref="EarlyStop"/> is <see langword="true"/>.
    /// </value>
    public int? TargetIncludedGroupCount { get; set; }

    /// <inheritdoc/>
    public async Task<bool> CompactAsync(MessageIndex groups, CancellationToken cancellationToken = default)
    {
        bool anyCompacted = false;

        foreach (ICompactionStrategy strategy in this.Strategies)
        {
            bool compacted = await strategy.CompactAsync(groups, cancellationToken).ConfigureAwait(false);

            if (compacted)
            {
                anyCompacted = true;
            }

            if (this.EarlyStop && this.TargetIncludedGroupCount is int targetIncludedGroupCount && groups.IncludedGroupCount <= targetIncludedGroupCount)
            {
                break;
            }
        }

        return anyCompacted;
    }
}
