// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.Workflows.Declarative.Extensions;
using Microsoft.Bot.ObjectModel;

namespace Microsoft.Agents.Workflows.Declarative.CodeGen;

internal partial class ClearAllVariablesTemplate
{
    public ClearAllVariablesTemplate(ClearAllVariables model)
    {
        this.Model = model;
        this.Id = model.GetId();
        this.Name = this.Id.FormatType();
        this.ScopeName = "Topic"; // %%% TODO
    }

    public ClearAllVariables Model { get; }

    public string Id { get; }
    public string Name { get; }
    public string ScopeName { get; }
}
