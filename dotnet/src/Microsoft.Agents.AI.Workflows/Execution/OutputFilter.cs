// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;

namespace Microsoft.Agents.AI.Workflows.Execution;

internal sealed class OutputFilter(Workflow workflow)
{
    public bool CanOutput(string sourceExecutorId, object output)
    {
        return workflow.OutputExecutors.ContainsKey(sourceExecutorId);
    }

    public bool TryGetTags(string sourceExecutorId, [NotNullWhen(true)] out HashSet<OutputTag>? tags)
        => workflow.OutputExecutors.TryGetValue(sourceExecutorId, out tags);
}
