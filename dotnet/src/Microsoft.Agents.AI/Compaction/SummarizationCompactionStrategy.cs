// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Diagnostics.CodeAnalysis;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.Logging;
using Microsoft.Shared.DiagnosticIds;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Compaction;

/// <summary>
/// A compaction strategy that uses an LLM to summarize older portions of the conversation,
/// replacing them with a single summary message that preserves key facts and context.
/// </summary>
/// <remarks>
/// <para>
/// This strategy protects system messages and the most recent <see cref="MinimumPreservedGroups"/>
/// non-system groups. All older groups are collected and sent to the <see cref="IChatClient"/>
/// for summarization. The resulting summary replaces those messages as a single assistant message
/// with <see cref="CompactionGroupKind.Summary"/>.
/// </para>
/// <para>
/// <see cref="MinimumPreservedGroups"/> is a hard floor: even if the <see cref="CompactionStrategy.Target"/>
/// has not been reached, compaction will not touch the last <see cref="MinimumPreservedGroups"/> non-system groups.
/// </para>
/// <para>
/// The <see cref="CompactionTrigger"/> predicate controls when compaction proceeds. Use
/// <see cref="CompactionTriggers"/> for common trigger conditions such as token thresholds.
/// </para>
/// </remarks>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public sealed class SummarizationCompactionStrategy : CompactionStrategy
{
    /// <summary>
    /// The default summarization prompt used when none is provided.
    /// </summary>
    public const string DefaultSummarizationPrompt =
        """
        You are a conversation summarizer. Produce a concise summary of the conversation that preserves:

        - Key facts, decisions, and user preferences
        - Important context needed for future turns
        - Tool call outcomes and their significance

        Omit pleasantries and redundant exchanges. Be factual and brief.
        """;

    /// <summary>
    /// The default minimum number of most-recent non-system groups to preserve.
    /// </summary>
    public const int DefaultMinimumPreserved = 8;

    /// <summary>
    /// Initializes a new instance of the <see cref="SummarizationCompactionStrategy"/> class.
    /// </summary>
    /// <param name="chatClient">The <see cref="IChatClient"/> to use for generating summaries. A smaller, faster model is recommended.</param>
    /// <param name="trigger">
    /// The <see cref="CompactionTrigger"/> that controls when compaction proceeds.
    /// </param>
    /// <param name="minimumPreservedGroups">
    /// The minimum number of most-recent non-system message groups to preserve.
    /// This is a hard floor — compaction will not summarize groups beyond this limit,
    /// regardless of the target condition. Defaults to 8, preserving the current and recent exchanges.
    /// </param>
    /// <param name="summarizationPrompt">
    /// An optional custom system prompt for the summarization LLM call. When <see langword="null"/>,
    /// <see cref="DefaultSummarizationPrompt"/> is used.
    /// </param>
    /// <param name="target">
    /// An optional target condition that controls when compaction stops. When <see langword="null"/>,
    /// defaults to the inverse of the <paramref name="trigger"/> — compaction stops as soon as the trigger would no longer fire.
    /// </param>
    public SummarizationCompactionStrategy(
        IChatClient chatClient,
        CompactionTrigger trigger,
        int minimumPreservedGroups = DefaultMinimumPreserved,
        string? summarizationPrompt = null,
        CompactionTrigger? target = null)
        : base(trigger, target)
    {
        this.ChatClient = Throw.IfNull(chatClient);
        this.MinimumPreservedGroups = EnsureNonNegative(minimumPreservedGroups);
        this.SummarizationPrompt = summarizationPrompt ?? DefaultSummarizationPrompt;
    }

    /// <summary>
    /// Gets the chat client used for generating summaries.
    /// </summary>
    public IChatClient ChatClient { get; }

    /// <summary>
    /// Gets the minimum number of most-recent non-system groups that are always preserved.
    /// This is a hard floor that compaction cannot exceed, regardless of the target condition.
    /// </summary>
    public int MinimumPreservedGroups { get; }

    /// <summary>
    /// Gets the prompt used when requesting summaries from the chat client.
    /// </summary>
    public string SummarizationPrompt { get; }

    /// <inheritdoc/>
    protected override async ValueTask<bool> CompactCoreAsync(CompactionMessageIndex index, ILogger logger, CancellationToken cancellationToken)
    {
        // Count non-system, non-excluded groups to determine which are protected
        int nonSystemIncludedCount = 0;
        for (int i = 0; i < index.Groups.Count; i++)
        {
            CompactionMessageGroup group = index.Groups[i];
            if (!group.IsExcluded && group.Kind != CompactionGroupKind.System)
            {
                nonSystemIncludedCount++;
            }
        }

        int protectedFromEnd = Math.Min(this.MinimumPreservedGroups, nonSystemIncludedCount);
        int maxSummarizable = nonSystemIncludedCount - protectedFromEnd;

        if (maxSummarizable <= 0)
        {
            return false;
        }

        // Mark oldest non-system groups for summarization one at a time until the target is met.
        // Track which groups were excluded so we can restore them if the LLM call fails.
        List<ChatMessage> summarizationMessages = [new ChatMessage(ChatRole.System, this.SummarizationPrompt)];
        List<CompactionMessageGroup> excludedGroups = [];
        int insertIndex = -1;

        for (int i = 0; i < index.Groups.Count && excludedGroups.Count < maxSummarizable; i++)
        {
            CompactionMessageGroup group = index.Groups[i];
            if (group.IsExcluded || group.Kind == CompactionGroupKind.System)
            {
                continue;
            }

            if (insertIndex < 0)
            {
                insertIndex = i;
            }

            // Collect messages from this group for summarization
            summarizationMessages.AddRange(group.Messages);

            group.IsExcluded = true;
            group.ExcludeReason = $"Summarized by {nameof(SummarizationCompactionStrategy)}";
            excludedGroups.Add(group);

            // Stop marking when target condition is met
            if (this.Target(index))
            {
                break;
            }
        }

        // Generate summary using the chat client (single LLM call for all marked groups)
        int summarized = excludedGroups.Count;
        if (logger.IsEnabled(LogLevel.Debug))
        {
            logger.LogSummarizationStarting(summarized, summarizationMessages.Count - 1, this.ChatClient.GetType().Name);
        }

        using Activity? summarizeActivity = CompactionTelemetry.ActivitySource.StartActivity(CompactionTelemetry.ActivityNames.Summarize);
        summarizeActivity?.SetTag(CompactionTelemetry.Tags.GroupsSummarized, summarized);

        ChatResponse response;
        try
        {
            response = await this.ChatClient.GetResponseAsync(
                summarizationMessages,
                cancellationToken: cancellationToken).ConfigureAwait(false);
        }
        catch (Exception ex) when (ex is not OperationCanceledException)
        {
            // Restore excluded groups so the conversation is not left in an inconsistent state
            for (int i = 0; i < excludedGroups.Count; i++)
            {
                excludedGroups[i].IsExcluded = false;
                excludedGroups[i].ExcludeReason = null;
            }

            logger.LogSummarizationFailed(summarized, ex.Message);

            return false;
        }

        string summaryText = string.IsNullOrWhiteSpace(response.Text) ? "[Summary unavailable]" : response.Text;

        summarizeActivity?.SetTag(CompactionTelemetry.Tags.SummaryLength, summaryText.Length);

        // Insert a summary group at the position of the first summarized group
        ChatMessage summaryMessage = new(ChatRole.Assistant, $"[Summary]\n{summaryText}");
        (summaryMessage.AdditionalProperties ??= [])[CompactionMessageGroup.SummaryPropertyKey] = true;

        index.InsertGroup(insertIndex, CompactionGroupKind.Summary, [summaryMessage]);

        logger.LogSummarizationCompleted(summaryText.Length, insertIndex);

        return true;
    }
}
