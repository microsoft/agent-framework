// Copyright (c) Microsoft. All rights reserved.

using System.Linq;
using Microsoft.Bot.ObjectModel;

namespace Microsoft.Agents.AI.Workflows.Declarative.Extensions;

internal static class DialogBaseExtensions
{
    public static TDialog WrapWithBot<TDialog>(this TDialog dialog) where TDialog : DialogBase
    {
        BotDefinition bot
            = new BotDefinition.Builder
            {
                Components =
                    {
                        new DialogComponent.Builder
                        {
                            SchemaName = dialog.HasSchemaName ? dialog.SchemaName : "default-schema",
                            Dialog = dialog.ToBuilder(),
                        }
                    }
            }.Build();

        return bot.Descendants().OfType<TDialog>().First();
    }
}
