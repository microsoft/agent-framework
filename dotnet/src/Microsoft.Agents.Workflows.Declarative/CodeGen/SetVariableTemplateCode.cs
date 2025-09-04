// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.Workflows.Declarative.Extensions;
using Microsoft.Bot.ObjectModel;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.Workflows.Declarative.Templates;

internal partial class SetVariableTemplate
{
    internal SetVariableTemplate(SetVariable model)
    {
        this.Model = model;
        this.Id = model.GetId();
        this.Name = this.Id.FormatType();
        this.VariableName = Throw.IfNull(this.Model.Variable?.Path.VariableName);
        this.TopicName = Throw.IfNull(this.Model.Variable?.Path.VariableScopeName);
    }

    internal SetVariable Model { get; }

    internal string Id { get; }
    internal string Name { get; }
    internal string VariableName { get; }
    internal string TopicName { get; }
}
