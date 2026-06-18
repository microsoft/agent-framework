// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Diagnostics.CodeAnalysis;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.Logging;
using Microsoft.Shared.DiagnosticIds;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Compaction;

/// <summary>
/// A compaction strategy that derives token thresholds from a model's context window size
/// and maximum output tokens, applying a two-phase compaction pipeline:
/// <list type="number">
/// <item><description><b>Tool result eviction</b> (<see cref="ToolResultCompactionStrategy"/>) — collapses old tool call groups
/// into concise summaries when the token count exceeds the <see cref="ToolEvictionThreshold"/>.</description></item>
/// <item><description><b>Truncation</b> (<see cref="TruncationCompactionStrategy"/>) — removes the oldest non-system message groups
/// when the token count exceeds the <see cref="TruncationThreshold"/>.</description></item>
/// </list>
/// </summary>
/// <remarks>
/// <para>
/// The <b>input budget</b> is defined as <c>maxContextWindowTokens - maxOutputTokens</c>, representing
/// the maximum number of tokens available for the conversation input (including system messages, tools, and history).
/// </para>
/// <para>
/// This strategy is a convenience wrapper around <see cref="PipelineCompactionStrategy"/> that automates
/// threshold calculation from model specifications.
/// </para>
/// </remarks>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public sealed class ContextWindowCompactionStrategy : CompactionStrategy
{
    /// <summary>
    /// The default fraction of the input budget at which tool result eviction triggers.
    /// </summary>
    public const double DefaultToolEvictionThreshold = 0.5;

    /// <summary>
    /// The default fraction of the input budget at which truncation triggers.
    /// </summary>
    public const double DefaultTruncationThreshold = 0.8;

    private readonly PipelineCompactionStrategy _pipeline;

    /// <summary>
    /// Initializes a new instance of the <see cref="ContextWindowCompactionStrategy"/> class.
    /// </summary>
    /// <param name="maxContextWindowTokens">
    /// The maximum number of tokens the model's context window supports (e.g., 1,050,000 for gpt-5.4).
    /// </param>
    /// <param name="maxOutputTokens">
    /// The maximum number of output tokens the model can generate per response (e.g., 128,000 for gpt-5.4).
    /// </param>
    /// <param name="toolEvictionThreshold">
    /// The fraction of the input budget (0.0, 1.0] at which tool result eviction triggers.
    /// Defaults to <see cref="DefaultToolEvictionThreshold"/> (0.5).
    /// </param>
    /// <param name="truncationThreshold">
    /// The fraction of the input budget (0.0, 1.0] at which truncation triggers.
    /// Defaults to <see cref="DefaultTruncationThreshold"/> (0.8).
    /// Must be greater than or equal to <paramref name="toolEvictionThreshold"/>.
    /// </param>
    /// <exception cref="ArgumentOutOfRangeException">
    /// <paramref name="maxContextWindowTokens"/> is not positive, or
    /// <paramref name="maxOutputTokens"/> is negative or greater than or equal to <paramref name="maxContextWindowTokens"/>, or
    /// <paramref name="toolEvictionThreshold"/> or <paramref name="truncationThreshold"/> is not in (0.0, 1.0], or
    /// <paramref name="truncationThreshold"/> is less than <paramref name="toolEvictionThreshold"/>.
    /// </exception>
    public ContextWindowCompactionStrategy(
        int maxContextWindowTokens,
        int maxOutputTokens,
        double toolEvictionThreshold = DefaultToolEvictionThreshold,
        double truncationThreshold = DefaultTruncationThreshold)
        : base(CompactionTriggers.Always)
    {
        Throw.IfLessThanOrEqual(maxContextWindowTokens, 0);
        Throw.IfLessThan(maxOutputTokens, 0);
        Throw.IfGreaterThanOrEqual(maxOutputTokens, maxContextWindowTokens);

        ValidateThreshold(toolEvictionThreshold, nameof(toolEvictionThreshold));
        ValidateThreshold(truncationThreshold, nameof(truncationThreshold));

        if (truncationThreshold < toolEvictionThreshold)
        {
            throw new ArgumentOutOfRangeException(nameof(truncationThreshold), truncationThreshold,
                $"Truncation threshold ({truncationThreshold}) must be greater than or equal to tool eviction threshold ({toolEvictionThreshold}).");
        }

        this.MaxContextWindowTokens = maxContextWindowTokens;
        this.MaxOutputTokens = maxOutputTokens;
        this.InputBudgetTokens = maxContextWindowTokens - maxOutputTokens;
        this.ToolEvictionThreshold = toolEvictionThreshold;
        this.TruncationThreshold = truncationThreshold;

        int toolEvictionTokens = (int)(this.InputBudgetTokens * toolEvictionThreshold);
        int truncationTokens = (int)(this.InputBudgetTokens * truncationThreshold);

        this._pipeline = new PipelineCompactionStrategy(
            new ToolResultCompactionStrategy(
                trigger: CompactionTriggers.TokensExceed(toolEvictionTokens),
                minimumPreservedGroups: 2),
            new TruncationCompactionStrategy(
                trigger: CompactionTriggers.TokensExceed(truncationTokens),
                minimumPreservedGroups: 2));
    }

    /// <summary>
    /// Gets the maximum context window size in tokens.
    /// </summary>
    public int MaxContextWindowTokens { get; }

    /// <summary>
    /// Gets the maximum output tokens per response.
    /// </summary>
    public int MaxOutputTokens { get; }

    /// <summary>
    /// Gets the computed input budget in tokens (<see cref="MaxContextWindowTokens"/> minus <see cref="MaxOutputTokens"/>).
    /// </summary>
    public int InputBudgetTokens { get; }

    /// <summary>
    /// Gets the fraction of the input budget at which tool result eviction triggers.
    /// </summary>
    public double ToolEvictionThreshold { get; }

    /// <summary>
    /// Gets the fraction of the input budget at which truncation triggers.
    /// </summary>
    public double TruncationThreshold { get; }

    /// <inheritdoc/>
    protected override async ValueTask<bool> CompactCoreAsync(CompactionMessageIndex index, ILogger logger, CancellationToken cancellationToken)
    {
        return await this._pipeline.CompactAsync(index, logger, cancellationToken).ConfigureAwait(false);
    }

    private static void ValidateThreshold(double value, string paramName)
    {
        if (value is <= 0.0 or > 1.0)
        {
            throw new ArgumentOutOfRangeException(paramName, value, "Threshold must be in the range (0.0, 1.0].");
        }
    }
}
