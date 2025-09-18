// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Bot.ObjectModel;

namespace Microsoft.Agents.Workflows.Declarative.CodeGen;

internal partial class BlankTemplate
{
    public BlankTemplate(DialogAction model)
    {
        this.Model = this.Initialize(model);
    }

    public DialogAction Model { get; }
}
