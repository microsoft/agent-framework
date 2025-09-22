// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.Workflows.Declarative.Extensions;

namespace Microsoft.Agents.Workflows.Declarative.CodeGen;

internal partial class EmptyTemplate
{
    public EmptyTemplate(string actionId, string executorComment)
    {
        this.Id = actionId;
        this.Name = this.Id.FormatType();
        this.Comment = executorComment;
    }

    public string Id { get; }
    public string Comment { get; }
    public string Name { get; }
}
