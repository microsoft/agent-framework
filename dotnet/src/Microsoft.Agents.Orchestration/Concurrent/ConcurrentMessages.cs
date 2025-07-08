// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.Orchestration.Concurrent;

/// <summary>
/// Common messages used by the <see cref="ConcurrentOrchestration{TInput, TOutput}"/>.
/// </summary>
internal static class ConcurrentMessages
{
    /// <summary>
    /// An empty message instance as a default.
    /// </summary>
    public static readonly ChatMessage Empty = new();

    /// <summary>
    /// The input task for a <see cref="ConcurrentOrchestration{TInput, TOutput}"/>.
    /// </summary>
    public sealed class Request
    {
        /// <summary>
        /// The request input.
        /// </summary>
        public IList<ChatMessage> Messages { get; init; } = [];
    }

    /// <summary>
    /// A result from a <see cref="ConcurrentOrchestration{TInput, TOutput}"/>.
    /// </summary>
    public sealed class Result
    {
        /// <summary>
        /// The result message.
        /// </summary>
        public ChatMessage Message { get; init; } = Empty;
    }

    /// <summary>
    /// Extension method to convert a <see cref="string"/> to a <see cref="Result"/>.
    /// </summary>
    public static Result AsResultMessage(this string text, ChatRole? role = null) => new() { Message = new ChatMessage(role ?? ChatRole.Assistant, text) };

    /// <summary>
    /// Extension method to convert a <see cref="ChatMessage"/> to a <see cref="Result"/>.
    /// </summary>
    public static Result AsResultMessage(this ChatMessage message) => new() { Message = message };

    /// <summary>
    /// Extension method to convert a collection of <see cref="ChatMessage"/> to a <see cref="ConcurrentMessages.Request"/>.
    /// </summary>
    public static Request AsInputMessage(this IEnumerable<ChatMessage> messages) => new() { Messages = [.. messages] };
}
