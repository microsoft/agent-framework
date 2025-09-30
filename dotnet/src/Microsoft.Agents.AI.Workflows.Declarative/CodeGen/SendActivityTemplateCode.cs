// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Bot.ObjectModel;

namespace Microsoft.Agents.AI.Workflows.Declarative.CodeGen;

internal partial class SendActivityTemplate
{
    public SendActivityTemplate(SendActivity model)
    {
        this.Model = this.Initialize(model);
    }

    public SendActivity Model { get; }
}
