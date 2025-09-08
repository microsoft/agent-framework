// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Extensions.AI;

/// <summary>
/// Options for deleting long-running operation.
/// </summary>
public class ChatDeleteRunOptions
{
    /// <summary>Gets or sets an identifier for a conversation a long-running operation is associated with.</summary>
    public string? ConversationId { get; set; }
}
