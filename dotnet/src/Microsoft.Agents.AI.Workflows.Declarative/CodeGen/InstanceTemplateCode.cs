// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.Workflows.Declarative.Extensions;

namespace Microsoft.Agents.AI.Workflows.Declarative.CodeGen;

internal partial class InstanceTemplate
{
    public InstanceTemplate(string executorId, string rootId, bool hasProvider = false)
    {
        this.InstanceVariable = executorId.FormatName();
        this.ExecutorType = executorId.FormatType();
        this.RootVariable = rootId.FormatName();
        this.HasProvider = hasProvider;
    }

    public string InstanceVariable { get; }
    public string ExecutorType { get; }
    public string RootVariable { get; }
    public bool HasProvider { get; }
}
