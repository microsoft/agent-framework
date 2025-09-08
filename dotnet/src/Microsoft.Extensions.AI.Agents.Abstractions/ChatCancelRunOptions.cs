// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Extensions.AI;

/// <summary>
/// Options for cancelling long-running operation.
/// </summary>
public class ChatCancelRunOptions
{
    /// <summary>Gets or sets an identifier for a conversation a long-running operation is associated with.</summary>
    public string? ConversationId { get; set; }
}
