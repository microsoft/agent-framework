// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.Workflows.Declarative.Extensions;
using Microsoft.Bot.ObjectModel;

namespace Microsoft.Agents.Workflows.Declarative.Templates;

internal partial class SendActivityTemplate
{
    internal SendActivityTemplate(SendActivity model)
    {
        this.Model = model;
        this.Id = model.GetId();
        this.Name = this.Id.FormatType();
    }

    internal SendActivity Model { get; }
    internal string Id { get; }
    internal string Name { get; }
}
