// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.Workflows.Declarative;

/// <summary>
/// Event that broadcasts the conversation identifier.
/// </summary>
public class MessageActivityEvent(string message) : WorkflowEvent(message)
{
    /// <summary>
    /// The conversation ID associated with the workflow.
    /// </summary>
    public string Message => message;
}
