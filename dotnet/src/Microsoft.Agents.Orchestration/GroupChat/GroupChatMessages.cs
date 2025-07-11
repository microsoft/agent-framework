// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.Orchestration;

/// <summary>
/// Common messages used for agent chat patterns.
/// </summary>
internal static class GroupChatMessages
{
    /// <summary>
    /// Broadcast a message to all <see cref="GroupChatAgentActor"/>.
    /// </summary>
    public sealed record Group(IEnumerable<ChatMessage> Messages);

    /// <summary>
    /// Reset/clear the conversation history for all <see cref="GroupChatAgentActor"/>.
    /// </summary>
    public sealed class Reset;

    /// <summary>
    /// The final result.
    /// </summary>
    public sealed record Result(ChatMessage Message);

    /// <summary>
    /// Signal a <see cref="GroupChatAgentActor"/> to respond.
    /// </summary>
    public sealed class Speak;

    /// <summary>
    /// The input task.
    /// </summary>
    public sealed record InputTask(IEnumerable<ChatMessage> Messages)
    {
        /// <summary>
        /// Gets an input task that does not require any action.
        /// </summary>
        public static InputTask None { get; } = new([]);
    }
}
