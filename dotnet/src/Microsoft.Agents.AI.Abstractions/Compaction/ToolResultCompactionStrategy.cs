// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Compaction;

/// <summary>
/// A compaction strategy that collapses old assistant-tool-call groups into single
/// concise assistant messages, removing the detailed tool results while preserving
/// a record of which tools were called.
/// </summary>
/// <remarks>
/// <para>
/// This is the gentlest compaction strategy — it does not remove any user messages or
/// plain assistant responses. It only targets <see cref="ChatMessageGroupKind.AssistantToolGroup"/>
/// entries outside the protected recent window, replacing each multi-message group
/// (assistant call + tool results) with a single assistant message like
/// <c>[Tool calls: get_weather, search_docs]</c>.
/// </para>
/// <para>
/// The trigger condition fires only when token count exceeds <c>maxTokens</c> and
/// there is at least one tool call in the conversation.
/// </para>
/// </remarks>
public class ToolResultCompactionStrategy : ChatHistoryCompactionStrategy
{
    /// <summary>
    /// The default value for `preserveRecentGroups` used when constructing <see cref="ToolResultCompactionStrategy"/>.
    /// </summary>
    public const int DefaultPreserveRecentGroups = 2;

    private readonly int _maxTokens;

    /// <summary>
    /// Initializes a new instance of the <see cref="ToolResultCompactionStrategy"/> class.
    /// </summary>
    /// <param name="maxTokens">The maximum token budget. Tool groups are collapsed when the token count exceeds this value.</param>
    /// <param name="preserveRecentGroups">
    /// The number of most-recent non-system message groups to protect from collapsing.
    /// Defaults to 2, ensuring the current turn's tool interactions remain visible.
    /// </param>
    public ToolResultCompactionStrategy(int maxTokens, int preserveRecentGroups = DefaultPreserveRecentGroups)
        : base(new ToolResultClearingReducer(preserveRecentGroups))
    {
        this._maxTokens = maxTokens;
    }

    /// <inheritdoc/>
    protected override bool ShouldCompact(ChatHistoryMetric metrics) =>
        metrics.TokenCount > this._maxTokens && metrics.ToolCallCount > 0;

    /// <summary>
    /// An <see cref="IChatReducer"/> that collapses <see cref="ChatMessageGroupKind.AssistantToolGroup"/>
    /// entries into single summary messages, preserving the most recent groups.
    /// </summary>
    private sealed class ToolResultClearingReducer(int preserveRecentGroups) : IChatReducer
    {
        public Task<IEnumerable<ChatMessage>> ReduceAsync(
            IEnumerable<ChatMessage> messages,
            CancellationToken cancellationToken = default)
        {
            IReadOnlyList<ChatMessage> messageList = [.. messages];
            IReadOnlyList<ChatMessageGroup> groups = CurrentMetrics.Groups;

            List<ChatMessageGroup> nonSystemGroups = [.. groups.Where(g => g.Kind != ChatMessageGroupKind.System)];
            int protectedFromIndex = Math.Max(0, nonSystemGroups.Count - preserveRecentGroups);
            HashSet<int> protectedGroupStarts = [];
            for (int i = protectedFromIndex; i < nonSystemGroups.Count; i++)
            {
                protectedGroupStarts.Add(nonSystemGroups[i].StartIndex);
            }

            List<ChatMessage> result = new(messageList.Count);
            bool anyCollapsed = false;

            foreach (ChatMessageGroup group in groups)
            {
                if (group.Kind == ChatMessageGroupKind.AssistantToolGroup && !protectedGroupStarts.Contains(group.StartIndex))
                {
                    // Collapse this tool group into a single summary message
                    List<string> toolNames = [];
                    for (int j = group.StartIndex; j < group.StartIndex + group.Count; j++)
                    {
                        if (messageList[j].Contents is not null)
                        {
                            foreach (AIContent content in messageList[j].Contents)
                            {
                                if (content is FunctionCallContent fcc)
                                {
                                    toolNames.Add(fcc.Name);
                                }
                            }
                        }
                    }

                    string summary = $"[Tool calls: {string.Join(", ", toolNames)}]";
                    result.Add(new ChatMessage(ChatRole.Assistant, summary));
                    anyCollapsed = true;
                }
                else
                {
                    // Keep this group as-is
                    for (int j = group.StartIndex; j < group.StartIndex + group.Count; j++)
                    {
                        result.Add(messageList[j]);
                    }
                }
            }

            return Task.FromResult<IEnumerable<ChatMessage>>(anyCollapsed ? result : messageList);
        }
    }
}
