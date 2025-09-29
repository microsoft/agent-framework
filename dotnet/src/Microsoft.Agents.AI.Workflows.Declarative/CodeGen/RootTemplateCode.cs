// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.Workflows.Declarative.Extensions;
using Microsoft.Agents.AI.Workflows.Declarative.PowerFx;

namespace Microsoft.Agents.AI.Workflows.Declarative.CodeGen;

internal partial class RootTemplate
{
    internal RootTemplate(
        string workflowId,
        WorkflowTypeInfo typeInfo)
    {
        this.Id = workflowId;
        this.TypeInfo = typeInfo;
        this.TypeName = workflowId.FormatType();
    }

    public string Id { get; }
    public WorkflowTypeInfo TypeInfo { get; }
    public string TypeName { get; }
}
