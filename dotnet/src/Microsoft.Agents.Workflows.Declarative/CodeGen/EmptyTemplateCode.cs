// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.Workflows.Declarative.Extensions;
using Microsoft.Bot.ObjectModel;

namespace Microsoft.Agents.Workflows.Declarative.CodeGen;

internal partial class EmptyTemplate
{
    internal EmptyTemplate(DialogAction model)
    {
        this.Id = model.GetId();
        this.Name = this.Id.FormatType();
    }

    internal string Id { get; }
    internal string Name { get; }
}
