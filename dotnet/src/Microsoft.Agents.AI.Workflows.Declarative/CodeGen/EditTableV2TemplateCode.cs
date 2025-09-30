// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Bot.ObjectModel;

namespace Microsoft.Agents.AI.Workflows.Declarative.CodeGen;

internal partial class EditTableV2Template
{
    public EditTableV2Template(EditTableV2 model)
    {
        this.Model = this.Initialize(model);
    }

    public EditTableV2 Model { get; }
}
