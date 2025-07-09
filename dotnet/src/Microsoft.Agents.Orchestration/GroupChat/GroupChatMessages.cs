// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.Orchestration.GroupChat;

/// <summary>
/// Common messages used for agent chat patterns.
/// </summary>
public static class GroupChatMessages
{
    /// <summary>
    /// An empty message instance as a default.
    /// </summary>
    internal static readonly ChatMessage Empty = new();

    /// <summary>
    /// Broadcast a message to all <see cref="GroupChatAgentActor"/>.
    /// </summary>
    public sealed class Group
    {
        /// <summary>
        /// The chat message being broadcast.
        /// </summary>
        public IEnumerable<ChatMessage> Messages { get; init; } = [];
    }

    /// <summary>
    /// Reset/clear the conversation history for all <see cref="GroupChatAgentActor"/>.
    /// </summary>
    public sealed class Reset;

    /// <summary>
    /// The final result.
    /// </summary>
    public sealed class Result
    {
        /// <summary>
        /// The chat response message.
        /// </summary>
        public ChatMessage Message { get; init; } = Empty;
    }

    /// <summary>
    /// Signal a <see cref="GroupChatAgentActor"/> to respond.
    /// </summary>
    public sealed class Speak;

    /// <summary>
    /// The input task.
    /// </summary>
    public sealed class InputTask
    {
        /// <summary>
        /// A task that does not require any action.
        /// </summary>
        public static readonly InputTask None = new();

        /// <summary>
        /// The input that defines the task goal.
        /// </summary>
        public IEnumerable<ChatMessage> Messages { get; init; } = [];
    }

    /// <summary>
    /// Extension method to convert a <see cref="ChatMessage"/> to a <see cref="Group"/>.
    /// </summary>
    public static Group AsGroupMessage(this ChatMessage message) => new() { Messages = [message] };

    /// <summary>
    /// Extension method to convert a <see cref="ChatMessage"/> to a <see cref="Group"/>.
    /// </summary>
    public static Group AsGroupMessage(this IEnumerable<ChatMessage> messages) => new() { Messages = messages };

    /// <summary>
    /// Extension method to convert a <see cref="ChatMessage"/> to a <see cref="Result"/>.
    /// </summary>
    public static InputTask AsInputTaskMessage(this IEnumerable<ChatMessage> messages) => new() { Messages = messages };

    /// <summary>
    /// Extension method to convert a <see cref="ChatMessage"/> to a <see cref="Result"/>.
    /// </summary>
    public static Result AsResultMessage(this string text) => new() { Message = new(ChatRole.Assistant, text) };
}
