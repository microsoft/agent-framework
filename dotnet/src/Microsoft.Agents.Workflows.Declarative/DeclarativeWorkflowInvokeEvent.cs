// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.Workflows.Declarative;

/// <summary>
/// Event that represents a message produced by a declarative workflow.
/// </summary>
public class DeclarativeWorkflowInvokeEvent(string conversationId) : DeclarativeWorkflowEvent(conversationId)
{
    /// <summary>
    /// The conversation ID associated with the workflow.
    /// </summary>
    public new string Data => conversationId;
}
