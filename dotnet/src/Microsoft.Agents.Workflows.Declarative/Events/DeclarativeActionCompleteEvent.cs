// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.Workflows.Declarative.Extensions;
using Microsoft.Bot.ObjectModel;

namespace Microsoft.Agents.Workflows.Declarative;

/// <summary>
/// Event that indicates a declarative action has been invoked.
/// </summary>
public sealed class DeclarativeActionInvokeEvent : WorkflowEvent
{
    /// <summary>
    /// The declarative action id.
    /// </summary>
    public string ActionId { get; }

    /// <summary>
    /// The declarative action type name.
    /// </summary>
    public string ActionType { get; }

    /// <summary>
    /// Identifier of the parent action.
    /// </summary>
    public string? ParentActionId { get; }

    /// <summary>
    /// Identifier of the previous action.
    /// </summary>
    public string? PriorActionId { get; }

    internal DeclarativeActionInvokeEvent(DialogAction action, string? priorActionId) : base(action)
    {
        this.ActionId = action.GetId();
        this.ActionType = action.GetType().Name;
        this.ParentActionId = action.GetParentId();
        this.PriorActionId = priorActionId;
    }
}
