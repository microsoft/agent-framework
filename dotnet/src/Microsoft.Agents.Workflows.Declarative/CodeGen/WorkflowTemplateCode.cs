// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.Workflows.Declarative.Extensions;
using Microsoft.Agents.Workflows.Declarative.PowerFx;

namespace Microsoft.Agents.Workflows.Declarative.CodeGen;

internal partial class WorkflowTemplate
{
    internal WorkflowTemplate(
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
