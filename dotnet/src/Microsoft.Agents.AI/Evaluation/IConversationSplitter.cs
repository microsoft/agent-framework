// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Linq;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI;

/// <summary>
/// Strategy for splitting a conversation into query and response halves for evaluation.
/// </summary>
/// <remarks>
/// Use one of the built-in splitters from <see cref="ConversationSplitters"/> or implement
/// your own for domain-specific splitting logic (e.g., splitting before a memory-retrieval
/// tool call to evaluate recall quality).
/// </remarks>
public interface IConversationSplitter
{
    /// <summary>
    /// Splits a conversation into query messages and response messages.
    /// </summary>
    /// <param name="conversation">The full conversation to split.</param>
    /// <returns>A tuple of (query messages, response messages).</returns>
    (IReadOnlyList<ChatMessage> QueryMessages, IReadOnlyList<ChatMessage> ResponseMessages) Split(
        IReadOnlyList<ChatMessage> conversation);
}

/// <summary>
/// Built-in conversation splitters for common evaluation patterns.
/// </summary>
/// <remarks>
/// <list type="bullet">
///   <item><see cref="LastTurn"/>: Evaluates whether the agent answered the <em>latest</em> question well.</item>
///   <item><see cref="Full"/>: Evaluates whether the <em>whole conversation trajectory</em> served the original request.</item>
/// </list>
/// For custom splits, implement <see cref="IConversationSplitter"/> directly.
/// </remarks>
public static class ConversationSplitters
{
    /// <summary>
    /// Split at the last user message. Everything up to and including that message
    /// is the query; everything after is the response. This is the default strategy.
    /// </summary>
    public static IConversationSplitter LastTurn { get; } = new LastTurnSplitter();

    /// <summary>
    /// The first user message (and any preceding system messages) is the query;
    /// the entire remainder of the conversation is the response.
    /// Evaluates overall conversation trajectory.
    /// </summary>
    public static IConversationSplitter Full { get; } = new FullSplitter();

    private sealed class LastTurnSplitter : IConversationSplitter
    {
        public (IReadOnlyList<ChatMessage>, IReadOnlyList<ChatMessage>) Split(
            IReadOnlyList<ChatMessage> conversation)
        {
            int lastUserIdx = -1;
            for (int i = 0; i < conversation.Count; i++)
            {
                if (conversation[i].Role == ChatRole.User)
                {
                    lastUserIdx = i;
                }
            }

            if (lastUserIdx >= 0)
            {
                return (
                    conversation.Take(lastUserIdx + 1).ToList(),
                    conversation.Skip(lastUserIdx + 1).ToList());
            }

            return (new List<ChatMessage>(), conversation.ToList());
        }
    }

    private sealed class FullSplitter : IConversationSplitter
    {
        public (IReadOnlyList<ChatMessage>, IReadOnlyList<ChatMessage>) Split(
            IReadOnlyList<ChatMessage> conversation)
        {
            int firstUserIdx = -1;
            for (int i = 0; i < conversation.Count; i++)
            {
                if (conversation[i].Role == ChatRole.User)
                {
                    firstUserIdx = i;
                    break;
                }
            }

            if (firstUserIdx >= 0)
            {
                return (
                    conversation.Take(firstUserIdx + 1).ToList(),
                    conversation.Skip(firstUserIdx + 1).ToList());
            }

            return (new List<ChatMessage>(), conversation.ToList());
        }
    }
}
