// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.Workflows.Declarative.Extensions;
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
/// Event that indicates a declarative action has been invoked.
/// </summary>
public class DeclarativeActionInvokeEvent(string actionId, DialogAction action, string? priorActionId) : WorkflowEvent(action)
{
    /// <summary>
    /// The declarative action id.
    /// </summary>
    public string ActionId => actionId;

    /// <summary>
    /// The declarative action type name.
    /// </summary>
    public string ActionType => action.GetType().Name;

    /// <summary>
    /// Identifier of the parent action.
    /// </summary>
    public string? ParentActionId => action.GetParentId();

    /// <summary>
    /// Identifier of the previous action.
    /// </summary>
    public string? PriorActionId => priorActionId;
}

/// <summary>
/// Event that indicates a declarative action has completed.
/// </summary>
public class DeclarativeActionCompleteEvent(string actionId, DialogAction action) : WorkflowEvent(action)
{
    /// <summary>
    /// The declarative action identifier.
    /// </summary>
    public string ActionId => actionId;

    /// <summary>
    /// The declarative action type name.
    /// </summary>
    public string ActionType => action.GetType().Name;

    /// <summary>
    /// Identifier of the parent action.
    /// </summary>
    public string? ParentActionId => action.GetParentId();
}
