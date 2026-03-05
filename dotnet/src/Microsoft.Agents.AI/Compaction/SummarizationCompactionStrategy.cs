// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Diagnostics.CodeAnalysis;
using System.Linq;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Shared.DiagnosticIds;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Compaction;

/// <summary>
/// A compaction strategy that uses an LLM to summarize older portions of the conversation,
/// replacing them with a single summary message that preserves key facts and context.
/// </summary>
/// <remarks>
/// <para>
/// This strategy protects system messages and the most recent <see cref="MinimumPreserved"/>
/// non-system groups. All older groups are collected and sent to the <see cref="IChatClient"/>
/// for summarization. The resulting summary replaces those messages as a single assistant message
/// with <see cref="MessageGroupKind.Summary"/>.
/// </para>
/// <para>
/// <see cref="MinimumPreserved"/> is a hard floor: even if the <see cref="CompactionStrategy.Target"/>
/// has not been reached, compaction will not touch the last <see cref="MinimumPreserved"/> non-system groups.
/// </para>
/// <para>
/// The <see cref="CompactionTrigger"/> predicate controls when compaction proceeds.
/// When <see langword="null"/>, the strategy compacts whenever there are groups older than the preserve window.
/// Use <see cref="CompactionTriggers"/> for common trigger conditions such as token thresholds.
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
    /// Initializes a new instance of the <see cref="SummarizationCompactionStrategy"/> class.
    /// </summary>
    /// <param name="chatClient">The <see cref="IChatClient"/> to use for generating summaries. A smaller, faster model is recommended.</param>
    /// <param name="trigger">
    /// The <see cref="CompactionTrigger"/> that controls when compaction proceeds.
    /// </param>
    /// <param name="minimumPreserved">
    /// The minimum number of most-recent non-system message groups to preserve.
    /// This is a hard floor — compaction will not summarize groups beyond this limit,
    /// regardless of the target condition. Defaults to 4, preserving the current and recent exchanges.
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
        int minimumPreserved = 4,
        string? summarizationPrompt = null,
        CompactionTrigger? target = null)
        : base(trigger, target)
    {
        this.ChatClient = Throw.IfNull(chatClient);
        this.MinimumPreserved = minimumPreserved;
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
    public int MinimumPreserved { get; }

    /// <summary>
    /// Gets the prompt used when requesting summaries from the chat client.
    /// </summary>
    public string SummarizationPrompt { get; }

    /// <inheritdoc/>
    protected override async Task<bool> ApplyCompactionAsync(MessageIndex index, CancellationToken cancellationToken)
    {
        // Count non-system, non-excluded groups to determine which are protected
        int nonSystemIncludedCount = 0;
        for (int i = 0; i < index.Groups.Count; i++)
        {
            MessageGroup group = index.Groups[i];
            if (!group.IsExcluded && group.Kind != MessageGroupKind.System)
            {
                nonSystemIncludedCount++;
            }
        }

        int protectedFromEnd = Math.Min(this.MinimumPreserved, nonSystemIncludedCount);
        int maxSummarizable = nonSystemIncludedCount - protectedFromEnd;

        if (maxSummarizable <= 0)
        {
            return false;
        }

        // Mark oldest non-system groups for summarization one at a time until the target is met
        StringBuilder conversationText = new();
        int summarized = 0;
        int insertIndex = -1;

        for (int i = 0; i < index.Groups.Count && summarized < maxSummarizable; i++)
        {
            MessageGroup group = index.Groups[i];
            if (group.IsExcluded || group.Kind == MessageGroupKind.System)
            {
                continue;
            }

            if (insertIndex < 0)
            {
                insertIndex = i;
            }

            // Build text representation of the group for summarization
            foreach (ChatMessage message in group.Messages)
            {
                string text = message.Text ?? string.Empty;
                if (!string.IsNullOrEmpty(text))
                {
                    conversationText.AppendLine($"{message.Role}: {text}");
                }
            }

            group.IsExcluded = true;
            group.ExcludeReason = $"Summarized by {nameof(SummarizationCompactionStrategy)}";
            summarized++;

            // Stop marking when target condition is met
            if (this.Target(index))
            {
                break;
            }
        }

        // Generate summary using the chat client (single LLM call for all marked groups)
        ChatResponse response = await this.ChatClient.GetResponseAsync(
            [
                new ChatMessage(ChatRole.System, this.SummarizationPrompt),
                .. index.Groups
                    .Where(g => !g.IsExcluded && g.Kind == MessageGroupKind.System)
                    .SelectMany(g => g.Messages),
                new ChatMessage(ChatRole.User, conversationText.ToString()),
                new ChatMessage(ChatRole.User, "Summarize the conversation above concisely."),
            ],
            cancellationToken: cancellationToken).ConfigureAwait(false);

        string summaryText = string.IsNullOrWhiteSpace(response.Text) ? "[Summary unavailable]" : response.Text;

        // Insert a summary group at the position of the first summarized group
        ChatMessage summaryMessage = new(ChatRole.Assistant, $"[Summary]\n{summaryText}");
        (summaryMessage.AdditionalProperties ??= [])[MessageGroup.SummaryPropertyKey] = true;

        index.InsertGroup(insertIndex, MessageGroupKind.Summary, [summaryMessage]);

        return true;
    }
}
