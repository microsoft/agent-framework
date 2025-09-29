// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Bot.ObjectModel;

namespace Microsoft.Agents.AI.Workflows.Declarative.CodeGen;

internal partial class SetMultipleVariablesTemplate
{
    public SetMultipleVariablesTemplate(SetMultipleVariables model)
    {
        this.Model = this.Initialize(model);
    }

    public SetMultipleVariables Model { get; }
}
