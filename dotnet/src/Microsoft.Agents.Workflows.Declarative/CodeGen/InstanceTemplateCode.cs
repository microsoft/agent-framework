// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.Workflows.Declarative.Extensions;

namespace Microsoft.Agents.Workflows.Declarative.CodeGen;

internal partial class InstanceTemplate
{
    public InstanceTemplate(string executorId)
    {
        this.InstanceVariable = executorId.FormatName();
        this.ExecutorType = executorId.FormatType();
    }

    public string InstanceVariable { get; }
    public string ExecutorType { get; }
}
