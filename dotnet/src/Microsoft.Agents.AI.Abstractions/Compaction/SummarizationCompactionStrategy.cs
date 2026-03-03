// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Compaction;

/// <summary>
/// A compaction strategy that uses an LLM to summarize older portions of the conversation,
/// replacing them with a concise summary message that preserves key facts and context.
/// </summary>
/// <remarks>
/// <para>
/// This strategy sits between tool-result clearing (gentle) and truncation (aggressive) in the
/// compaction ladder. Unlike truncation which discards messages entirely, summarization preserves
/// the essential information in compressed form, allowing the agent to maintain awareness of
/// earlier context.
/// </para>
/// <para>
/// The strategy protects system messages and the most recent <c>preserveRecentGroups</c>
/// non-system groups. All older groups are collected and sent to the <see cref="IChatClient"/>
/// for summarization. The resulting summary replaces those messages as a single assistant message.
/// </para>
/// </remarks>
public class SummarizationCompactionStrategy : ChatHistoryCompactionStrategy
{
    private readonly int _maxTokens;

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
    /// <param name="maxTokens">The maximum token budget. Summarization is triggered when the token count exceeds this value.</param>
    /// <param name="preserveRecentGroups">
    /// The number of most-recent non-system message groups to protect from summarization.
    /// Defaults to 4, preserving the current and recent exchanges.
    /// </param>
    /// <param name="summarizationPrompt">
    /// An optional custom system prompt for the summarization LLM call. When <see langword="null"/>,
    /// a default prompt that emphasizes fact-preservation is used.
    /// </param>
    public SummarizationCompactionStrategy(
        IChatClient chatClient,
        int maxTokens,
        int preserveRecentGroups = 4,
        string? summarizationPrompt = null)
        : base(new SummarizationReducer(chatClient, preserveRecentGroups, summarizationPrompt ?? DefaultSummarizationPrompt))
    {
        this._maxTokens = maxTokens;
    }

    /// <inheritdoc/>
    protected override bool ShouldCompact(ChatHistoryMetric metrics) =>
        metrics.TokenCount > this._maxTokens;

    /// <summary>
    /// An <see cref="IChatReducer"/> that sends older message groups to an LLM for summarization,
    /// then replaces them with a single summary message.
    /// </summary>
    private sealed class SummarizationReducer : IChatReducer
    {
        private readonly IChatClient _chatClient;
        private readonly int _preserveRecentGroups;
        private readonly string _summarizationPrompt;

        public SummarizationReducer(IChatClient chatClient, int preserveRecentGroups, string summarizationPrompt)
        {
            this._chatClient = Throw.IfNull(chatClient);
            this._preserveRecentGroups = preserveRecentGroups;
            this._summarizationPrompt = Throw.IfNullOrEmpty(summarizationPrompt);
        }

        public async Task<IEnumerable<ChatMessage>> ReduceAsync(
            IEnumerable<ChatMessage> messages,
            CancellationToken cancellationToken = default)
        {
            IReadOnlyList<ChatMessage> messageList = [.. messages];
            IReadOnlyList<ChatMessageGroup> groups = CurrentMetrics.Groups;

            List<ChatMessageGroup> nonSystemGroups = [.. groups.Where(g => g.Kind != ChatMessageGroupKind.System)];
            int protectedFromIndex = Math.Max(0, nonSystemGroups.Count - this._preserveRecentGroups);

            if (protectedFromIndex == 0)
            {
                // Nothing to summarize — all groups are protected
                return messageList;
            }

            // Collect messages from groups that will be summarized
            List<ChatMessage> toSummarize = [];
            for (int i = 0; i < protectedFromIndex; i++)
            {
                ChatMessageGroup group = nonSystemGroups[i];
                for (int j = group.StartIndex; j < group.StartIndex + group.Count; j++)
                {
                    toSummarize.Add(messageList[j]);
                }
            }

            if (toSummarize.Count == 0)
            {
                return messageList;
            }

            // Build the summarization request
            List<ChatMessage> summarizationRequest =
            [
                new(ChatRole.System, this._summarizationPrompt),
                .. toSummarize,
                new(ChatRole.User, "Summarize the conversation above concisely."),
            ];

            ChatResponse response = await this._chatClient.GetResponseAsync(summarizationRequest, cancellationToken: cancellationToken).ConfigureAwait(false);
            string summaryText = string.IsNullOrWhiteSpace(response.Text) ? "[Summary unavailable]" : response.Text;

            // Build result: system groups + summary + protected groups
            List<ChatMessage> result = [];

            // Keep system messages
            foreach (ChatMessageGroup group in groups)
            {
                if (group.Kind == ChatMessageGroupKind.System)
                {
                    for (int j = group.StartIndex; j < group.StartIndex + group.Count; j++)
                    {
                        result.Add(messageList[j]);
                    }
                }
            }

            // Insert summary
            result.Add(new ChatMessage(ChatRole.Assistant, $"[Summary]\n{summaryText}"));

            // Keep protected groups
            for (int i = protectedFromIndex; i < nonSystemGroups.Count; i++)
            {
                ChatMessageGroup group = nonSystemGroups[i];
                for (int j = group.StartIndex; j < group.StartIndex + group.Count; j++)
                {
                    result.Add(messageList[j]);
                }
            }

            return result;
        }
    }
}
