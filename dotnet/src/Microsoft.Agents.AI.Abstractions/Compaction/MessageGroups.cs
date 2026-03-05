// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Linq;
using System.Text;
using Microsoft.Extensions.AI;
using Microsoft.ML.Tokenizers;

namespace Microsoft.Agents.AI.Compaction;

/// <summary>
/// Represents a collection of <see cref="MessageGroup"/> instances derived from a flat list of <see cref="ChatMessage"/> objects.
/// </summary>
/// <remarks>
/// <para>
/// <see cref="MessageGroups"/> provides structural grouping of messages into logical units that
/// respect the atomic group preservation constraint: tool call assistant messages and their corresponding
/// tool result messages are always grouped together.
/// </para>
/// <para>
/// This collection supports exclusion-based projection, where groups can be marked as excluded
/// without being removed, allowing compaction strategies to toggle visibility while preserving
/// the full history for diagnostics or storage.
/// </para>
/// <para>
/// Each group tracks its own <see cref="MessageGroup.MessageCount"/>, <see cref="MessageGroup.ByteCount"/>,
/// and <see cref="MessageGroup.TokenCount"/>. The collection provides aggregate properties for both
/// the total (all groups) and included (non-excluded groups only) counts.
/// </para>
/// </remarks>
public sealed class MessageGroups
{
    /// <summary>
    /// Gets the list of message groups in this collection.
    /// </summary>
    public IList<MessageGroup> Groups { get; }

    /// <summary>
    /// Gets the tokenizer used for computing token counts, or <see langword="null"/> if token counts are estimated.
    /// </summary>
    public Tokenizer? Tokenizer { get; }

    /// <summary>
    /// Initializes a new instance of the <see cref="MessageGroups"/> class with the specified groups.
    /// </summary>
    /// <param name="groups">The message groups.</param>
    /// <param name="tokenizer">An optional tokenizer retained for computing token counts when adding new groups.</param>
    public MessageGroups(IList<MessageGroup> groups, Tokenizer? tokenizer = null)
    {
        this.Groups = groups;
        this.Tokenizer = tokenizer;
    }

    /// <summary>
    /// Creates a <see cref="MessageGroups"/> from a flat list of <see cref="ChatMessage"/> instances.
    /// </summary>
    /// <param name="messages">The messages to group.</param>
    /// <param name="tokenizer">
    /// An optional <see cref="Tokenizer"/> for computing token counts on each group.
    /// When <see langword="null"/>, token counts are estimated as <c>ByteCount / 4</c>.
    /// </param>
    /// <returns>A new <see cref="MessageGroups"/> with messages organized into logical groups.</returns>
    /// <remarks>
    /// The grouping algorithm:
    /// <list type="bullet">
    /// <item><description>System messages become <see cref="MessageGroupKind.System"/> groups.</description></item>
    /// <item><description>User messages become <see cref="MessageGroupKind.User"/> groups.</description></item>
    /// <item><description>Assistant messages with tool calls, followed by their corresponding tool result messages, become <see cref="MessageGroupKind.ToolCall"/> groups.</description></item>
    /// <item><description>Assistant messages marked with <see cref="MessageGroup.SummaryPropertyKey"/> become <see cref="MessageGroupKind.Summary"/> groups.</description></item>
    /// <item><description>Assistant messages without tool calls become <see cref="MessageGroupKind.AssistantText"/> groups.</description></item>
    /// </list>
    /// </remarks>
    public static MessageGroups Create(IList<ChatMessage> messages, Tokenizer? tokenizer = null)
    {
        List<MessageGroup> groups = [];
        int index = 0;
        int currentTurn = 0;

        while (index < messages.Count)
        {
            ChatMessage message = messages[index];

            if (message.Role == ChatRole.System)
            {
                // System messages are not part of any turn
                groups.Add(CreateGroup(MessageGroupKind.System, [message], tokenizer, turnIndex: null));
                index++;
            }
            else if (message.Role == ChatRole.User)
            {
                currentTurn++;
                groups.Add(CreateGroup(MessageGroupKind.User, [message], tokenizer, currentTurn));
                index++;
            }
            else if (message.Role == ChatRole.Assistant && HasToolCalls(message))
            {
                List<ChatMessage> groupMessages = [message];
                index++;

                // Collect all subsequent tool result messages
                while (index < messages.Count && messages[index].Role == ChatRole.Tool)
                {
                    groupMessages.Add(messages[index]);
                    index++;
                }

                groups.Add(CreateGroup(MessageGroupKind.ToolCall, groupMessages, tokenizer, currentTurn));
            }
            else if (message.Role == ChatRole.Assistant && IsSummaryMessage(message))
            {
                groups.Add(CreateGroup(MessageGroupKind.Summary, [message], tokenizer, currentTurn));
                index++;
            }
            else
            {
                groups.Add(CreateGroup(MessageGroupKind.AssistantText, [message], tokenizer, currentTurn));
                index++;
            }
        }

        return new MessageGroups(groups, tokenizer);
    }

    /// <summary>
    /// Creates a new <see cref="MessageGroup"/> with byte and token counts computed using this collection's
    /// <see cref="Tokenizer"/>, and adds it to the <see cref="Groups"/> list at the specified index.
    /// </summary>
    /// <param name="index">The zero-based index at which the group should be inserted.</param>
    /// <param name="kind">The kind of message group.</param>
    /// <param name="messages">The messages in the group.</param>
    /// <param name="turnIndex">The optional turn index to assign to the new group.</param>
    /// <returns>The newly created <see cref="MessageGroup"/>.</returns>
    public MessageGroup InsertGroup(int index, MessageGroupKind kind, IReadOnlyList<ChatMessage> messages, int? turnIndex = null)
    {
        MessageGroup group = CreateGroup(kind, messages, this.Tokenizer, turnIndex);
        this.Groups.Insert(index, group);
        return group;
    }

    /// <summary>
    /// Creates a new <see cref="MessageGroup"/> with byte and token counts computed using this collection's
    /// <see cref="Tokenizer"/>, and appends it to the end of the <see cref="Groups"/> list.
    /// </summary>
    /// <param name="kind">The kind of message group.</param>
    /// <param name="messages">The messages in the group.</param>
    /// <param name="turnIndex">The optional turn index to assign to the new group.</param>
    /// <returns>The newly created <see cref="MessageGroup"/>.</returns>
    public MessageGroup AddGroup(MessageGroupKind kind, IReadOnlyList<ChatMessage> messages, int? turnIndex = null)
    {
        MessageGroup group = CreateGroup(kind, messages, this.Tokenizer, turnIndex);
        this.Groups.Add(group);
        return group;
    }

    /// <summary>
    /// Returns only the messages from groups that are not excluded.
    /// </summary>
    /// <returns>A list of <see cref="ChatMessage"/> instances from included groups, in order.</returns>
    public IEnumerable<ChatMessage> GetIncludedMessages() =>
        this.Groups.Where(group => !group.IsExcluded).SelectMany(group => group.Messages);

    /// <summary>
    /// Returns all messages from all groups, including excluded ones.
    /// </summary>
    /// <returns>A list of all <see cref="ChatMessage"/> instances, in order.</returns>
    public IEnumerable<ChatMessage> GetAllMessages() => this.Groups.SelectMany(group => group.Messages);

    #region Total aggregates (all groups, including excluded)

    /// <summary>
    /// Gets the total number of groups, including excluded ones.
    /// </summary>
    public int TotalGroupCount => this.Groups.Count;

    /// <summary>
    /// Gets the total number of messages across all groups, including excluded ones.
    /// </summary>
    public int TotalMessageCount => this.Groups.Sum(g => g.MessageCount);

    /// <summary>
    /// Gets the total UTF-8 byte count across all groups, including excluded ones.
    /// </summary>
    public int TotalByteCount => this.Groups.Sum(g => g.ByteCount);

    /// <summary>
    /// Gets the total token count across all groups, including excluded ones.
    /// </summary>
    public int TotalTokenCount => this.Groups.Sum(g => g.TokenCount);

    #endregion

    #region Included aggregates (non-excluded groups only)

    /// <summary>
    /// Gets the total number of groups that are not excluded.
    /// </summary>
    public int IncludedGroupCount => this.Groups.Count(g => !g.IsExcluded);

    /// <summary>
    /// Gets the total number of messages across all included (non-excluded) groups.
    /// </summary>
    public int IncludedMessageCount => this.Groups.Where(g => !g.IsExcluded).Sum(g => g.MessageCount);

    /// <summary>
    /// Gets the total UTF-8 byte count across all included (non-excluded) groups.
    /// </summary>
    public int IncludedByteCount => this.Groups.Where(g => !g.IsExcluded).Sum(g => g.ByteCount);

    /// <summary>
    /// Gets the total token count across all included (non-excluded) groups.
    /// </summary>
    public int IncludedTokenCount => this.Groups.Where(g => !g.IsExcluded).Sum(g => g.TokenCount);

    #endregion

    #region Turn aggregates

    /// <summary>
    /// Gets the total number of user turns across all groups (including those with excluded groups).
    /// </summary>
    public int TotalTurnCount => this.Groups.Select(group => group.TurnIndex).Distinct().Count(turnIndex => turnIndex is not null);

    /// <summary>
    /// Gets the number of user turns that have at least one non-excluded group.
    /// </summary>
    public int IncludedTurnCount => this.Groups.Where(group => !group.IsExcluded).Select(group => group.TurnIndex).Distinct().Count(turnIndex => turnIndex is not null);

    /// <summary>
    /// Returns all groups that belong to the specified user turn.
    /// </summary>
    /// <param name="turnIndex">The zero-based turn index.</param>
    /// <returns>The groups belonging to the turn, in order.</returns>
    public IEnumerable<MessageGroup> GetTurnGroups(int turnIndex) =>
        this.Groups.Where(g => g.TurnIndex == turnIndex);

    #endregion

    /// <summary>
    /// Computes the UTF-8 byte count for a set of messages.
    /// </summary>
    /// <param name="messages">The messages to compute byte count for.</param>
    /// <returns>The total UTF-8 byte count of all message text content.</returns>
    public static int ComputeByteCount(IReadOnlyList<ChatMessage> messages)
    {
        int total = 0;
        for (int i = 0; i < messages.Count; i++)
        {
            string text = messages[i].Text ?? string.Empty;
            if (text.Length > 0)
            {
                total += Encoding.UTF8.GetByteCount(text);
            }
        }

        return total;
    }

    /// <summary>
    /// Computes the token count for a set of messages using the specified tokenizer.
    /// </summary>
    /// <param name="messages">The messages to compute token count for.</param>
    /// <param name="tokenizer">The tokenizer to use for counting tokens.</param>
    /// <returns>The total token count across all message text content.</returns>
    public static int ComputeTokenCount(IReadOnlyList<ChatMessage> messages, Tokenizer tokenizer)
    {
        int total = 0;
        for (int i = 0; i < messages.Count; i++)
        {
            string text = messages[i].Text ?? string.Empty;
            if (text.Length > 0)
            {
                total += tokenizer.CountTokens(text);
            }
        }

        return total;
    }

    private static MessageGroup CreateGroup(MessageGroupKind kind, IReadOnlyList<ChatMessage> messages, Tokenizer? tokenizer, int? turnIndex)
    {
        int byteCount = ComputeByteCount(messages);
        int tokenCount = tokenizer is not null
            ? ComputeTokenCount(messages, tokenizer)
            : byteCount / 4;

        return new MessageGroup(kind, messages, byteCount, tokenCount, turnIndex);
    }

    private static bool HasToolCalls(ChatMessage message)
    {
        if (message.Contents is null)
        {
            return false;
        }

        foreach (AIContent content in message.Contents)
        {
            if (content is FunctionCallContent)
            {
                return true;
            }
        }

        return false;
    }

    private static bool IsSummaryMessage(ChatMessage message)
    {
        return message.AdditionalProperties?.TryGetValue(MessageGroup.SummaryPropertyKey, out object? value) is true
            && value is true;
    }
}
