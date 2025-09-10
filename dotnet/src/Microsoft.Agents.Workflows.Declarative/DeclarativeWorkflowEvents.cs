// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Bot.ObjectModel;

namespace Microsoft.Agents.Workflows.Declarative;

/// <summary>
/// Event that broadcasts the conversation identifier.
/// </summary>
public class ConversationUpdateEvent(string executorid, string conversationId) : ExecutorEvent(executorid, conversationId)
{
    /// <summary>
    /// The conversation ID associated with the workflow.
    /// </summary>
    public string ConversationId { get; } = conversationId;
}

/// <summary>
/// Event that indicates a declarative action is been invoked.
/// </summary>
public class DeclarativeActionInvokeEvent(string actionId, DialogAction action) : WorkflowEvent(action)
{
    /// <summary>
    /// The declarative action id.
    /// </summary>
    public string ActionId => actionId;

    /// <summary>
    /// The declarative action action type name.
    /// </summary>
    public string ActionType => action.GetType().Name;
}

/// <summary>
/// Event that indicates a declarative action has completed.
/// </summary>
public class DeclarativeActionCompleteEvent(string actionId, DialogAction action) : WorkflowEvent(action)
{
    /// <summary>
    /// The declarative action id.
    /// </summary>
    public string ActionId => actionId;

    /// <summary>
    /// The declarative action action type name.
    /// </summary>
    public string ActionType => action.GetType().Name;
}
