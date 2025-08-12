// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Bot.ObjectModel;

namespace Microsoft.Agents.Workflows.Declarative.Extensions;

internal static class DataValueExtensions
{
    public static string? GetParentId(this BotElement element) => element.Parent?.GetId();

    public static string GetId(this BotElement element)
    {
        return element switch
        {
            DialogAction action => action.Id.Value,
            ConditionItem conditionItem => conditionItem.Id ?? throw new WorkflowModelException($"Undefined identifier for {nameof(ConditionItem)} that is member of {conditionItem.GetParentId() ?? "(root)"}."),
            OnActivity activity => activity.Id.Value,
            _ => throw new UnknownActionException($"Unknown element type: {element.GetType().Name}"),
        };
    }
}
