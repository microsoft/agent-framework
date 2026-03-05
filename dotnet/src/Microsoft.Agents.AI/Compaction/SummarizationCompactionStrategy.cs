// Copyright (c) Microsoft. All rights reserved.

using System.Text;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Compaction;

/// <summary>
/// A compaction strategy that summarizes older message groups using an <see cref="IChatClient"/>,
/// replacing them with a single summary message.
/// </summary>
/// <remarks>
/// <para>
/// When the number of included message groups exceeds <see cref="MaxGroupsBeforeSummary"/>,
/// this strategy extracts the oldest non-system groups (up to the threshold), sends them
/// to an <see cref="IChatClient"/> for summarization, and replaces those groups with a single
/// assistant message containing the summary.
/// </para>
/// <para>
/// System message groups are always preserved and never included in summarization.
/// </para>
/// </remarks>
public sealed class SummarizationCompactionStrategy : ICompactionStrategy
{
    private const string DefaultSummarizationPrompt =
        "Summarize the following conversation concisely, preserving key facts, decisions, and context. " +
        "Focus on information that would be needed to continue the conversation effectively.";

    /// <summary>
    /// Initializes a new instance of the <see cref="SummarizationCompactionStrategy"/> class.
    /// </summary>
    /// <param name="chatClient">The chat client to use for generating summaries.</param>
    /// <param name="maxGroupsBeforeSummary">The maximum number of included groups allowed before summarization is triggered.</param>
    /// <param name="summarizationPrompt">Optional custom prompt for the summarization request. If <see langword="null"/>, a default prompt is used.</param>
    public SummarizationCompactionStrategy(IChatClient chatClient, int maxGroupsBeforeSummary, string? summarizationPrompt = null)
    {
        this.ChatClient = Throw.IfNull(chatClient);
        this.MaxGroupsBeforeSummary = maxGroupsBeforeSummary;
        this.SummarizationPrompt = summarizationPrompt ?? DefaultSummarizationPrompt;
    }

    /// <summary>
    /// Gets the chat client used for generating summaries.
    /// </summary>
    public IChatClient ChatClient { get; }

    /// <summary>
    /// Gets the maximum number of included groups allowed before summarization is triggered.
    /// </summary>
    public int MaxGroupsBeforeSummary { get; }

    /// <summary>
    /// Gets the prompt used when requesting summaries from the chat client.
    /// </summary>
    public string SummarizationPrompt { get; }

    /// <inheritdoc/>
    public async Task<bool> CompactAsync(MessageIndex groups, CancellationToken cancellationToken = default)
    {
        int includedCount = groups.IncludedGroupCount;
        if (includedCount <= this.MaxGroupsBeforeSummary)
        {
            return false;
        }

        // Determine how many groups to summarize (keep the most recent MaxGroupsBeforeSummary groups)
        int groupsToSummarize = includedCount - this.MaxGroupsBeforeSummary;

        // Collect the oldest non-system included groups for summarization
        StringBuilder conversationText = new();
        int summarized = 0;
        int insertIndex = -1;

        for (int i = 0; i < groups.Groups.Count && summarized < groupsToSummarize; i++)
        {
            MessageGroup group = groups.Groups[i];
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
            group.ExcludeReason = "Summarized by SummarizationCompactionStrategy";
            summarized++;
        }

        if (summarized == 0)
        {
            return false;
        }

        // Generate summary using the chat client
        ChatResponse response = await this.ChatClient.GetResponseAsync(
            [
                new ChatMessage(ChatRole.System, this.SummarizationPrompt),
                new ChatMessage(ChatRole.User, conversationText.ToString()),
            ],
            cancellationToken: cancellationToken).ConfigureAwait(false);

        string summaryText = response.Text ?? string.Empty;

        // Insert a summary group at the position of the first summarized group
        ChatMessage summaryMessage = new(ChatRole.Assistant, $"[Summary of earlier conversation]: {summaryText}");
        (summaryMessage.AdditionalProperties ??= [])[MessageGroup.SummaryPropertyKey] = true;

        if (insertIndex >= 0)
        {
            groups.InsertGroup(insertIndex, MessageGroupKind.Summary, [summaryMessage]);
        }
        else
        {
            groups.AddGroup(MessageGroupKind.Summary, [summaryMessage]);
        }

        return true;
    }
}
