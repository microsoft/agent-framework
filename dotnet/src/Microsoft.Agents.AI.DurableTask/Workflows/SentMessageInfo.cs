// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.Workflows;

namespace Microsoft.Agents.AI.DurableTask.Workflows;

/// <summary>
/// Information about a message sent via <see cref="IWorkflowContext.SendMessageAsync"/>.
/// </summary>
internal sealed class SentMessageInfo
{
    /// <summary>
    /// Gets or sets the serialized message content.
    /// </summary>
    public string? Message { get; set; }

    /// <summary>
    /// Gets or sets the full type name of the message.
    /// </summary>
    public string? TypeName { get; set; }
}
