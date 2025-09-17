// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.Workflows.Declarative.Extensions;
using Microsoft.Bot.ObjectModel;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.Workflows.Declarative.CodeGen;

internal partial class ResetVariableTemplate
{
    public ResetVariableTemplate(ResetVariable model)
    {
        this.Model = model;
        this.Id = model.GetId();
        this.Name = this.Id.FormatType();
        this.Variable = Throw.IfNull(this.Model.Variable);
    }

    public ResetVariable Model { get; }

    public string Id { get; }
    public string Name { get; }
    public PropertyPath Variable { get; }
}
