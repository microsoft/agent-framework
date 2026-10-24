// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.TypeSafe;

/// <summary>
/// Represents the Jev-specific options of one <see cref="JevChatClient"/> request.
/// </summary>
/// <remarks>
/// A <see cref="JevChatClient"/> reads this type from <see cref="ChatOptions.RawRepresentationFactory"/>, which is
/// how Microsoft.Extensions.AI passes options that only one provider understands. Other chat clients ignore it.
/// <see cref="JevChatOptionsExtensions.WithJevQuestions"/> sets the factory for you.
/// </remarks>
public sealed class JevChatRequestOptions
{
    /// <summary>
    /// Gets or sets the questions to answer about the conversation, keyed by an ID that the caller chooses.
    /// </summary>
    /// <remarks>
    /// Each answer of the <see cref="JevResult"/> uses the ID of its question. IDs that start with
    /// <c>__af_tool__</c> are reserved for the questions that route tool calls.
    /// </remarks>
    public required IReadOnlyDictionary<string, JevQuestion> Questions { get; set; }
}
