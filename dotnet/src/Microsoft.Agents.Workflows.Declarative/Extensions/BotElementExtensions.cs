// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Bot.ObjectModel;

namespace Microsoft.Agents.Workflows.Declarative.Extensions;

internal static class BotElementExtensions
{
    public static string? GetParentId(this BotElement element) => element.Parent?.GetId();

    public static string GetId(this BotElement element) =>
        element switch
        {
            DialogAction action => action.Id.Value,
            ConditionItem conditionItem => conditionItem.Id ?? throw new DeclarativeModelException($"Undefined identifier for {nameof(ConditionItem)} that is member of {conditionItem.GetParentId() ?? "(root)"}."),
            OnActivity activity => activity.Id.Value,
            SystemTrigger trigger => trigger.Id.Value,
            _ => throw new DeclarativeModelException($"Unknown identify for element type: {element.GetType().Name}"),
        };
}
