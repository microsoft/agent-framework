// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Linq;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Compaction;

/// <summary>
/// Default implementation of <see cref="IChatHistoryMetricsCalculator"/> that uses
/// JSON serialization length heuristics for token and byte estimation.
/// </summary>
/// <remarks>
/// <para>
/// Token estimation uses a configurable characters-per-token ratio (default ~4) since
/// precise tokenization requires a model-specific tokenizer. For production workloads
/// requiring accurate token counts, implement <see cref="IChatHistoryMetricsCalculator"/>
/// with a model-appropriate tokenizer.
/// </para>
/// </remarks>
public sealed class DefaultChatHistoryMetricsCalculator : IChatHistoryMetricsCalculator
{
    /// <summary>
    /// Gets the singleton instance of the chat history metrics calculator.
    /// </summary>
    /// <remarks>
    /// <see cref="DefaultChatHistoryMetricsCalculator"/> can be safety accessed by
    /// concurrent threads.
    /// </remarks>
    public static readonly DefaultChatHistoryMetricsCalculator Instance = new();

    private const int DefaultCharsPerToken = 4;
    private const int PerMessageOverheadTokens = 4;

    private readonly int _charsPerToken;

    /// <summary>
    /// Initializes a new instance of the <see cref="DefaultChatHistoryMetricsCalculator"/> class.
    /// </summary>
    /// <param name="charsPerToken">
    /// The approximate number of characters per token used for estimation. Default is 4.
    /// </param>
    public DefaultChatHistoryMetricsCalculator(int charsPerToken = DefaultCharsPerToken)
    {
        this._charsPerToken = charsPerToken > 0 ? charsPerToken : DefaultCharsPerToken;
    }

    /// <inheritdoc/>
    public ChatHistoryMetric Calculate(IReadOnlyList<ChatMessage> messages)
    {
        if (messages is null || messages.Count == 0)
        {
            return new();
        }

        int totalTokens = 0;
        long totalBytes = 0;
        int toolCallCount = 0;
        int userTurnCount = 0;
        bool inUserTurn = false;
        List<ChatMessageGroup> groups = [];
        int index = 0;

        while (index < messages.Count)
        {
            ChatMessage message = messages[index];

            // Accumulate per-message metrics
            this.AccumulateMessageMetrics(message, ref totalTokens, ref totalBytes, ref toolCallCount);

            if (message.Role == ChatRole.User)
            {
                if (!inUserTurn)
                {
                    userTurnCount++;
                    inUserTurn = true;
                }
            }
            else
            {
                inUserTurn = false;
            }

            // Identify the group starting at this message
            if (message.Role == ChatRole.System)
            {
                groups.Add(new(index, 1, ChatMessageGroupKind.System));
                index++;
            }
            else if (message.Role == ChatRole.User)
            {
                groups.Add(new(index, 1, ChatMessageGroupKind.UserTurn));
                index++;
            }
            else if (message.Role == ChatRole.Assistant)
            {
                bool hasToolCalls = message.Contents!.Any(c => c is FunctionCallContent);

                if (hasToolCalls)
                {
                    int groupStart = index;
                    index++;

                    while (index < messages.Count && messages[index].Role == ChatRole.Tool)
                    {
                        this.AccumulateMessageMetrics(messages[index], ref totalTokens, ref totalBytes, ref toolCallCount);
                        inUserTurn = false;
                        index++;
                    }

                    groups.Add(new(groupStart, index - groupStart, ChatMessageGroupKind.AssistantToolGroup));
                }
                else
                {
                    groups.Add(new(index, 1, ChatMessageGroupKind.AssistantPlain));
                    index++;
                }
            }
            else if (message.Role == ChatRole.Tool)
            {
                groups.Add(new(index, 1, ChatMessageGroupKind.ToolResult));
                index++;
            }
            else
            {
                groups.Add(new(index, 1, ChatMessageGroupKind.Other));
                index++;
            }
        }

        return new()
        {
            TokenCount = totalTokens,
            ByteCount = totalBytes,
            MessageCount = messages.Count,
            ToolCallCount = toolCallCount,
            UserTurnCount = userTurnCount,
            Groups = groups
        };
    }

    private void AccumulateMessageMetrics(ChatMessage message, ref int totalTokens, ref long totalBytes, ref int toolCallCount)
    {
        string serialized = message.Text;

        int charCount = serialized.Length;
        totalBytes += System.Text.Encoding.UTF8.GetByteCount(serialized);
        totalTokens += (charCount / this._charsPerToken) + PerMessageOverheadTokens;

        if (message.Contents is not null)
        {
            foreach (AIContent content in message.Contents)
            {
                if (content is FunctionCallContent)
                {
                    toolCallCount++;
                }
            }
        }
    }
}
