// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Bot.ObjectModel;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.Workflows.Declarative.CodeGen;

internal partial class SetTextVariableTemplate
{
    public SetTextVariableTemplate(SetTextVariable model)
    {
        this.Model = this.Initialize(model);
        this.Variable = Throw.IfNull(this.Model.Variable?.Path);
    }

    public SetTextVariable Model { get; }

    public PropertyPath Variable { get; }
}
