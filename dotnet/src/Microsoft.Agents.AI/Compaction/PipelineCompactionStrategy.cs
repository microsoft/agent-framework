// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.Logging;
using Microsoft.Shared.DiagnosticIds;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Compaction;

/// <summary>
/// A compaction strategy that executes a sequential pipeline of <see cref="CompactionStrategy"/> instances
/// against the same <see cref="CompactionMessageIndex"/>.
/// </summary>
/// <remarks>
/// <para>
/// Each strategy in the pipeline operates on the result of the previous one, enabling composed behaviors
/// such as summarizing older messages first and then truncating to fit a token budget.
/// </para>
/// <para>
/// The pipeline itself always executes while each child strategy evaluates its own
/// <see cref="CompactionStrategy.Trigger"/> independently to decide whether it should compact.
/// </para>
/// </remarks>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public sealed class PipelineCompactionStrategy : CompactionStrategy
{
    /// <summary>
    /// Initializes a new instance of the <see cref="PipelineCompactionStrategy"/> class.
    /// </summary>
    /// <param name="strategies">The ordered sequence of strategies to execute.</param>
    public PipelineCompactionStrategy(params IEnumerable<CompactionStrategy> strategies)
        : base(CompactionTriggers.Always)
    {
        this.Strategies = [.. Throw.IfNull(strategies)];
    }

    /// <summary>
    /// Gets the ordered list of strategies in this pipeline.
    /// </summary>
    public IReadOnlyList<CompactionStrategy> Strategies { get; }

    /// <inheritdoc/>
    protected override async ValueTask<bool> CompactCoreAsync(CompactionMessageIndex index, ILogger logger, CancellationToken cancellationToken)
    {
        bool anyCompacted = false;

        foreach (CompactionStrategy strategy in this.Strategies)
        {
            bool compacted = await strategy.CompactAsync(index, logger, cancellationToken).ConfigureAwait(false);

            if (compacted)
            {
                anyCompacted = true;
            }
        }

        return anyCompacted;
    }
}
