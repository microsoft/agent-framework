// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Bot.ObjectModel;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Workflows.Declarative.CodeGen;

internal partial class ForeachTemplate
{
    public ForeachTemplate(Foreach model)
    {
        this.Model = this.Initialize(model);
        this.Index = this.Model.Index?.Path;
        this.Value = Throw.IfNull(this.Model.Value);
    }

    public Foreach Model { get; }
    public PropertyPath? Index { get; }
    public PropertyPath Value { get; }
}
