// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Bot.ObjectModel;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Workflows.Declarative.CodeGen;

internal partial class ResetVariableTemplate
{
    public ResetVariableTemplate(ResetVariable model)
    {
        this.Model = this.Initialize(model);
        this.Variable = Throw.IfNull(this.Model.Variable);
    }

    public ResetVariable Model { get; }

    public PropertyPath Variable { get; }
}
