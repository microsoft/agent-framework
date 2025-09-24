// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.Workflows.Declarative.Extensions;

namespace Microsoft.Agents.Workflows.Declarative.CodeGen;

internal partial class EmptyTemplate
{
    public EmptyTemplate(string actionId, string rootId, string? action = null)
    {
        this.Id = actionId;
        this.Action = action;
        this.Name = this.Id.FormatType();
        this.InstanceVariable = this.Id.FormatName();
        this.RootVariable = rootId.FormatName();
    }

    public string Id { get; }
    public string? Action { get; }
    public string Name { get; }
    public string InstanceVariable { get; }
    public string RootVariable { get; }
}
