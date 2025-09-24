// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.Workflows.Declarative.Extensions;

namespace Microsoft.Agents.Workflows.Declarative.CodeGen;

internal partial class EmptyTemplate
{
    public EmptyTemplate(string actionId, string rootId, string? action = null)
    {
        this.Id = actionId;
        this.Name = this.Id.FormatType();
        this.InstanceVariable = this.Id.FormatName();
        this.RootVariable = rootId.FormatName();
        this.Action = action;
    }

    public string Id { get; }
    public string Name { get; }
    public string InstanceVariable { get; }
    public string RootVariable { get; }
    public string? Action { get; }
}
