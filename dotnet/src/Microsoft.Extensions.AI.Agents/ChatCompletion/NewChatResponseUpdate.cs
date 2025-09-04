// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;

namespace Microsoft.Extensions.AI;

/// <summary>
/// Contains new properties that will be added to <see cref="ChatResponseUpdate"/> in the future.
/// </summary>
/// <remarks>
/// This class contains temporary properties that are not part of the <see cref="ChatResponseUpdate"/> class yet.
/// Later, these properties will be moved to the official <see cref="ChatResponseUpdate"/> class, and
/// this class will be removed. Therefore, please expect a breaking change if you are using
/// this class directly in your code.
/// </remarks>
public class NewChatResponseUpdate : ChatResponseUpdate
{
    /// <inheritdoc/>
    public NewChatResponseUpdate()
    {
    }

    /// <inheritdoc/>
    public NewChatResponseUpdate(ChatRole? role, string? content) : base(role, content)
    {
    }

    /// <inheritdoc/>
    public NewChatResponseUpdate(ChatRole? role, IList<AIContent>? contents) : base(role, contents)
    {
    }

    /// <summary>
    /// Specifies the status of the response.
    /// </summary>
    public NewResponseStatus? Status { get; set; }

    /// <summary>
    /// Specifies the sequence number of an update within a conversation.
    /// </summary>
    public string? SequenceNumber { get; set; }
}
