// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.Workflows.Declarative.Extensions;

namespace Microsoft.Agents.Workflows.Declarative.Templates;

internal partial class InstanceTemplate
{
    internal InstanceTemplate(string executorId)
    {
        this.InstanceVariable = executorId.FormatName();
        this.ExecutorType = executorId.FormatType() + "Executor";
    }

    public string InstanceVariable { get; }
    public string ExecutorType { get; }
}
