// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Bot.ObjectModel;

namespace Microsoft.Agents.AI.Workflows.Declarative.CodeGen;

internal partial class InvokeAzureAgentTemplate
{
    public InvokeAzureAgentTemplate(InvokeAzureAgent model)
    {
        this.Model = this.Initialize(model);
        this.Messages = this.Model.Output?.Messages?.Path;
        this.UseAgentProvider = true;
    }

    public InvokeAzureAgent Model { get; }

    public PropertyPath? Messages { get; }
}
