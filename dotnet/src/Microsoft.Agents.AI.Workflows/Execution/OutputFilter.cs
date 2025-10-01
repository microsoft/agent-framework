// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI.Workflows.Execution;

internal sealed class OutputFilter(Workflow workflow)
{
    public bool CanOutput(string sourceExecutorId, object output)
    {
        return workflow.OutputExecutors.Contains(sourceExecutorId);
    }
}
