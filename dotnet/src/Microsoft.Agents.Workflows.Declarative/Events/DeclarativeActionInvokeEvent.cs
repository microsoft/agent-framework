// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.Workflows.Declarative.Extensions;
using Microsoft.Bot.ObjectModel;

namespace Microsoft.Agents.Workflows.Declarative;

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
