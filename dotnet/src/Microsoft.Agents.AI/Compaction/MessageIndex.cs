// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using System.Linq;
using System.Text;
using Microsoft.Extensions.AI;
using Microsoft.ML.Tokenizers;
using Microsoft.Shared.DiagnosticIds;

namespace Microsoft.Agents.AI.Compaction;

/// <summary>
/// A collection of <see cref="MessageGroup"/> instances and derived metrics based on a flat list of <see cref="ChatMessage"/> objects.
/// </summary>
/// <remarks>
/// <see cref="MessageIndex"/> provides structural grouping of messages into logical <see cref="MessageGroup"/> units.  Individual
/// groups can be marked as excluded without being removed, allowing compaction strategies to toggle visibility while preserving
/// the full history for diagnostics or storage.  Metrics are provided both including and excluding excluded groups,
/// allowing strategies to make informed decisions based on the impact of potential exclusions.
/// </remarks>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public sealed class MessageIndex
{
    private int _currentTurn;
    private ChatMessage? _lastProcessedMessage;

    /// <summary>
    /// Gets the list of message groups in this collection.
    /// </summary>
    public IList<MessageGroup> Groups { get; }

    /// <summary>
    /// Gets the tokenizer used for computing token counts, or <see langword="null"/> if token counts are estimated.
    /// </summary>
    public Tokenizer? Tokenizer { get; }

    /// <summary>
    /// Initializes a new instance of the <see cref="MessageIndex"/> class with the specified groups.
    /// </summary>
    /// <param name="groups">The message groups.</param>
    /// <param name="tokenizer">An optional tokenizer retained for computing token counts when adding new groups.</param>
    public MessageIndex(IList<MessageGroup> groups, Tokenizer? tokenizer = null)
    {
        this.Tokenizer = tokenizer;
        this.Groups = groups;

        // Restore turn counter and last processed message from the groups
        for (int index = groups.Count - 1; index >= 0; --index)
        {
            if (this._lastProcessedMessage is null && this.Groups[index].Kind != MessageGroupKind.Summary)
            {
                IReadOnlyList<ChatMessage> groupMessages = this.Groups[index].Messages;
                this._lastProcessedMessage = groupMessages[^1];
            }

            if (this.Groups[index].TurnIndex.HasValue)
            {
                this._currentTurn = this.Groups[index].TurnIndex!.Value;

                // Both values restored — no need to keep scanning
                if (this._lastProcessedMessage is not null)
                {
                    break;
                }
            }
        }
    }

    /// <summary>
    /// Creates a <see cref="MessageIndex"/> from a flat list of <see cref="ChatMessage"/> instances.
    /// </summary>
    /// <param name="messages">The messages to group.</param>
    /// <param name="tokenizer">
    /// An optional <see cref="Tokenizer"/> for computing token counts on each group.
    /// When <see langword="null"/>, token counts are estimated as <c>ByteCount / 4</c>.
    /// </param>
    /// <returns>A new <see cref="MessageIndex"/> with messages organized into logical groups.</returns>
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
    internal static MessageIndex Create(IList<ChatMessage> messages, Tokenizer? tokenizer = null)
    {
        MessageIndex instance = new([], tokenizer);
        instance.AppendFromMessages(messages, 0);
        return instance;
    }

    /// <summary>
    /// Incrementally updates the groups with new messages from the conversation.
    /// </summary>
    /// <param name="allMessages">
    /// The full list of messages for the conversation. This must be the same list (or a replacement with the same
    /// prefix) that was used to create or last update this instance.
    /// </param>
    /// <remarks>
    /// <para>
    /// Uses equality on the last processed message to detect changes.  Only the messages after that position are
    /// processed and appended as new groups. Existing groups and their compaction state (exclusions) are preserved.
    /// </para>
    /// <para>
    /// If the last processed message is not found (e.g., the message list was replaced entirely
    /// or a sliding window shifted past it), all groups are cleared and rebuilt from scratch.
    /// </para>
    /// <para>
    /// If the last message in <paramref name="allMessages"/> is matches the last
    /// processed message, no work is performed.
    /// </para>
    /// </remarks>
    internal void Update(IList<ChatMessage> allMessages)
    {
        if (allMessages.Count == 0)
        {
            this.Groups.Clear();
            this._currentTurn = 0;
            this._lastProcessedMessage = null;
            return;
        }

        // If the last message is unchanged and the list hasn't shrunk, there is nothing new to process.
        if (this._lastProcessedMessage is not null &&
            allMessages.Count >= this.RawMessageCount &&
            allMessages[allMessages.Count - 1].ContentEquals(this._lastProcessedMessage))
        {
            return;
        }

        // Walk backwards to locate where we left off.
        int foundIndex = -1;
        if (this._lastProcessedMessage is not null)
        {
            for (int i = allMessages.Count - 1; i >= 0; --i)
            {
                if (allMessages[i].ContentEquals(this._lastProcessedMessage))
                {
                    foundIndex = i;
                    break;
                }
            }
        }

        if (foundIndex < 0)
        {
            // Last processed message not found — total rebuild.
            this.Groups.Clear();
            this._currentTurn = 0;
            this.AppendFromMessages(allMessages, 0);
            return;
        }

        // Guard against a sliding window that removed messages from the front:
        // the number of messages up to (and including) the found position must
        // match the number of messages already represented by existing groups.
        if (foundIndex + 1 < this.RawMessageCount)
        {
            // Front of the message list was trimmed — rebuild.
            this.Groups.Clear();
            this._currentTurn = 0;
            this.AppendFromMessages(allMessages, 0);
            return;
        }

        // Process only the delta messages.
        this.AppendFromMessages(allMessages, foundIndex + 1);
    }

    private void AppendFromMessages(IList<ChatMessage> messages, int startIndex)
    {
        int index = startIndex;

        while (index < messages.Count)
        {
            ChatMessage message = messages[index];

            if (message.Role == ChatRole.System)
            {
                // System messages are not part of any turn
                this.Groups.Add(CreateGroup(MessageGroupKind.System, [message], this.Tokenizer, turnIndex: null));
                index++;
            }
            else if (message.Role == ChatRole.User)
            {
                this._currentTurn++;
                this.Groups.Add(CreateGroup(MessageGroupKind.User, [message], this.Tokenizer, this._currentTurn));
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

                this.Groups.Add(CreateGroup(MessageGroupKind.ToolCall, groupMessages, this.Tokenizer, this._currentTurn));
            }
            else if (message.Role == ChatRole.Assistant && IsSummaryMessage(message))
            {
                this.Groups.Add(CreateGroup(MessageGroupKind.Summary, [message], this.Tokenizer, this._currentTurn));
                index++;
            }
            else
            {
                this.Groups.Add(CreateGroup(MessageGroupKind.AssistantText, [message], this.Tokenizer, this._currentTurn));
                index++;
            }
        }

        if (messages.Count > 0)
        {
            this._lastProcessedMessage = messages[^1];
        }
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

    /// <summary>
    /// Gets the total number of groups, including excluded ones.
    /// </summary>
    public int TotalGroupCount => this.Groups.Count;

    /// <summary>
    /// Gets the total number of messages across all groups, including excluded ones.
    /// </summary>
    public int TotalMessageCount => this.Groups.Sum(group => group.MessageCount);

    /// <summary>
    /// Gets the total UTF-8 byte count across all groups, including excluded ones.
    /// </summary>
    public int TotalByteCount => this.Groups.Sum(group => group.ByteCount);

    /// <summary>
    /// Gets the total token count across all groups, including excluded ones.
    /// </summary>
    public int TotalTokenCount => this.Groups.Sum(group => group.TokenCount);

    /// <summary>
    /// Gets the total number of groups that are not excluded.
    /// </summary>
    public int IncludedGroupCount => this.Groups.Count(group => !group.IsExcluded);

    /// <summary>
    /// Gets the total number of messages across all included (non-excluded) groups.
    /// </summary>
    public int IncludedMessageCount => this.Groups.Where(group => !group.IsExcluded).Sum(group => group.MessageCount);

    /// <summary>
    /// Gets the total UTF-8 byte count across all included (non-excluded) groups.
    /// </summary>
    public int IncludedByteCount => this.Groups.Where(group => !group.IsExcluded).Sum(group => group.ByteCount);

    /// <summary>
    /// Gets the total token count across all included (non-excluded) groups.
    /// </summary>
    public int IncludedTokenCount => this.Groups.Where(group => !group.IsExcluded).Sum(group => group.TokenCount);

    /// <summary>
    /// Gets the total number of user turns across all groups (including those with excluded groups).
    /// </summary>
    public int TotalTurnCount => this.Groups.Select(group => group.TurnIndex).Distinct().Count(turnIndex => turnIndex is not null);

    /// <summary>
    /// Gets the number of user turns that have at least one non-excluded group.
    /// </summary>
    public int IncludedTurnCount => this.Groups.Where(group => !group.IsExcluded && group.TurnIndex is not null && group.TurnIndex > 0).Select(group => group.TurnIndex).Distinct().Count();

    /// <summary>
    /// Gets the total number of groups across all included (non-excluded) groups that are not <see cref="MessageGroupKind.System"/>.
    /// </summary>
    public int IncludedNonSystemGroupCount => this.Groups.Count(group => !group.IsExcluded && group.Kind != MessageGroupKind.System);

    /// <summary>
    /// Gets the total number of original messages (that are not summaries).
    /// </summary>
    public int RawMessageCount => this.Groups.Where(group => group.Kind != MessageGroupKind.Summary).Sum(group => group.MessageCount);

    /// <summary>
    /// Returns all groups that belong to the specified user turn.
    /// </summary>
    /// <param name="turnIndex">The zero-based turn index.</param>
    /// <returns>The groups belonging to the turn, in order.</returns>
    public IEnumerable<MessageGroup> GetTurnGroups(int turnIndex) => this.Groups.Where(group => group.TurnIndex == turnIndex);

    /// <summary>
    /// Computes the UTF-8 byte count for a set of messages across all content types.
    /// </summary>
    /// <param name="messages">The messages to compute byte count for.</param>
    /// <returns>The total UTF-8 byte count of all message content.</returns>
    internal static int ComputeByteCount(IReadOnlyList<ChatMessage> messages)
    {
        int total = 0;
        for (int i = 0; i < messages.Count; i++)
        {
            IList<AIContent> contents = messages[i].Contents;
            for (int j = 0; j < contents.Count; j++)
            {
                total += ComputeContentByteCount(contents[j]);
            }
        }

        return total;
    }

    /// <summary>
    /// Computes the token count for a set of messages using the specified tokenizer.
    /// </summary>
    /// <param name="messages">The messages to compute token count for.</param>
    /// <param name="tokenizer">The tokenizer to use for counting tokens.</param>
    /// <returns>The total token count across all message content.</returns>
    /// <remarks>
    /// Text-bearing content (<see cref="TextContent"/> and <see cref="TextReasoningContent"/>)
    /// is tokenized directly. All other content types estimate tokens as <c>byteCount / 4</c>.
    /// </remarks>
    internal static int ComputeTokenCount(IReadOnlyList<ChatMessage> messages, Tokenizer tokenizer)
    {
        int total = 0;
        for (int i = 0; i < messages.Count; i++)
        {
            IList<AIContent> contents = messages[i].Contents;
            for (int j = 0; j < contents.Count; j++)
            {
                AIContent content = contents[j];
                switch (content)
                {
                    case TextContent text:
                        if (text.Text is { Length: > 0 } t)
                        {
                            total += tokenizer.CountTokens(t);
                        }

                        break;

                    case TextReasoningContent reasoning:
                        if (reasoning.Text is { Length: > 0 } rt)
                        {
                            total += tokenizer.CountTokens(rt);
                        }

                        if (reasoning.ProtectedData is { Length: > 0 } pd)
                        {
                            total += tokenizer.CountTokens(pd);
                        }

                        break;

                    default:
                        total += ComputeContentByteCount(content) / 4;
                        break;
                }
            }
        }

        return total;
    }

    private static int ComputeContentByteCount(AIContent content)
    {
        switch (content)
        {
            case TextContent text:
                return GetStringByteCount(text.Text);

            case TextReasoningContent reasoning:
                return GetStringByteCount(reasoning.Text) + GetStringByteCount(reasoning.ProtectedData);

            case DataContent data:
                return data.Data.Length + GetStringByteCount(data.MediaType) + GetStringByteCount(data.Name);

            case UriContent uri:
                return (uri.Uri is Uri uriValue ? GetStringByteCount(uriValue.OriginalString) : 0) + GetStringByteCount(uri.MediaType);

            case FunctionCallContent call:
                int callBytes = GetStringByteCount(call.CallId) + GetStringByteCount(call.Name);
                if (call.Arguments is not null)
                {
                    foreach (KeyValuePair<string, object?> arg in call.Arguments)
                    {
                        callBytes += GetStringByteCount(arg.Key);
                        callBytes += GetStringByteCount(arg.Value?.ToString());
                    }
                }

                return callBytes;

            case FunctionResultContent result:
                return GetStringByteCount(result.CallId) + GetStringByteCount(result.Result?.ToString());

            case ErrorContent error:
                return GetStringByteCount(error.Message) + GetStringByteCount(error.ErrorCode) + GetStringByteCount(error.Details);

            case HostedFileContent file:
                return GetStringByteCount(file.FileId) + GetStringByteCount(file.MediaType) + GetStringByteCount(file.Name);

            default:
                return 0;
        }
    }

    private static int GetStringByteCount(string? value) =>
        value is { Length: > 0 } ? Encoding.UTF8.GetByteCount(value) : 0;

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
