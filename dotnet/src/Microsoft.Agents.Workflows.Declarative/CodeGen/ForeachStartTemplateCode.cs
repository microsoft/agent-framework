// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Bot.ObjectModel;

namespace Microsoft.Agents.Workflows.Declarative.CodeGen;

internal partial class ForeachStartTemplate
{
    public ForeachStartTemplate(Foreach model)
    {
        this.Model = this.Initialize(model);
    }

    public Foreach Model { get; }
}
