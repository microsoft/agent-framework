// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.Workflows.Declarative.Extensions;
using Microsoft.Bot.ObjectModel;

namespace Microsoft.Agents.Workflows.Declarative.CodeGen;

internal partial class EmptyTemplate
{
    public EmptyTemplate(DialogAction model, string executorComment)
    {
        this.Id = model.GetId();
        this.Name = this.Id.FormatType();
        this.Comment = executorComment;
    }

    public string Id { get; }
    public string Name { get; }
    public string Comment { get; }
}
