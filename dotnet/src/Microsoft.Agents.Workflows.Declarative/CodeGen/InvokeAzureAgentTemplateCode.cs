// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Bot.ObjectModel;

namespace Microsoft.Agents.Workflows.Declarative.CodeGen;

internal partial class InvokeAzureAgentTemplate
{
    public InvokeAzureAgentTemplate(InvokeAzureAgent model)
    {
        this.Model = this.Initialize(model);
        this.UseAgentProvider = true;
    }

    public InvokeAzureAgent Model { get; }
}
