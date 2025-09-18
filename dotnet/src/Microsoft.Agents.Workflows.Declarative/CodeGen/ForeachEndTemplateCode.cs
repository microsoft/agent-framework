// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Bot.ObjectModel;

namespace Microsoft.Agents.Workflows.Declarative.CodeGen;

internal partial class ForeachEndTemplate
{
    public ForeachEndTemplate(Foreach model)
    {
        this.Model = this.Initialize(model);
    }

    public Foreach Model { get; }
}
