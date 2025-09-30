// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Bot.ObjectModel;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Workflows.Declarative.CodeGen;

internal partial class SetVariableTemplate
{
    internal SetVariableTemplate(SetVariable model)
    {
        this.Model = this.Initialize(model);
        this.Variable = Throw.IfNull(this.Model.Variable);
    }

    public SetVariable Model { get; }
    public PropertyPath Variable { get; }
}
