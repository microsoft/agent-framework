// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.Workflows.Declarative.Extensions;
using Microsoft.Bot.ObjectModel;

namespace Microsoft.Agents.AI.Workflows.Declarative.CodeGen;

internal partial class DefaultTemplate
{
    public DefaultTemplate(DialogAction model, string rootId, string? action = null)
    {
        this.Initialize(model);
        this.Action = action;
        this.InstanceVariable = this.Id.FormatName();
        this.RootVariable = rootId.FormatName();
    }

    public string? Action { get; }
    public string InstanceVariable { get; }
    public string RootVariable { get; }
}
