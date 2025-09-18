// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Bot.ObjectModel;

namespace Microsoft.Agents.Workflows.Declarative.CodeGen;

internal partial class ForeachTemplate
{
    public ForeachTemplate(Foreach model)
    {
        this.Model = this.Initialize(model);
    }

    public Foreach Model { get; }
}
