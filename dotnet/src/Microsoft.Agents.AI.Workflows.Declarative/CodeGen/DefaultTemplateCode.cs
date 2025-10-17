// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.Workflows.Declarative.Extensions;

namespace Microsoft.Agents.AI.Workflows.Declarative.CodeGen;

internal partial class DefaultTemplate
{
    public DefaultTemplate(string id, string rootId, string? action = null)
    {
        this.Id = id;
        this.InstanceVariable = this.Id.FormatName();
        this.RootVariable = rootId.FormatName();
    }

    public string Id { get; }
    public string InstanceVariable { get; }
    public string RootVariable { get; }
    public string? Action { get; }
}
