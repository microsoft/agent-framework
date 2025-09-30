// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI.Workflows.Declarative;

/// <summary>
/// Event that broadcasts the conversation identifier.
/// </summary>
public sealed class MessageActivityEvent : WorkflowEvent
{
    /// <summary>
    /// The conversation ID associated with the workflow.
    /// </summary>
    public string Message { get; }

    internal MessageActivityEvent(string message) : base(message)
    {
        this.Message = message;
    }
}
