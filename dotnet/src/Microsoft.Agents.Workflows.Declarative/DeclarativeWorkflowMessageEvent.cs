// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Extensions.AI;

namespace Microsoft.Agents.Workflows;

/// <summary>
/// Event that represents a message produced by a declarative workflow.
/// </summary>
public class DeclarativeWorkflowMessageEvent(ChatMessage message, UsageDetails? usage = null) : DeclarativeWorkflowEvent(message)
{
    /// <summary>
    /// The message data produced by the workflow, which is a <see cref="ChatMessage"/>.
    /// </summary>
    public new ChatMessage Data => message;

    /// <summary>
    /// The usage details associated with the message, if any.
    /// </summary>
    public UsageDetails? Usage => usage;
}
