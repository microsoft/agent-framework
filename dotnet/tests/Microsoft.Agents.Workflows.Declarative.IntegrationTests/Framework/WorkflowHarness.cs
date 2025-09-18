// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;

namespace Microsoft.Agents.Workflows.Declarative.IntegrationTests.Framework;

internal static class WorkflowHarness
{
    public static async Task<WorkflowEvents> RunAsync<TInput>(Workflow<TInput> workflow, TInput input) where TInput : notnull
    {
        StreamingRun run = await InProcessExecution.StreamAsync(workflow, input);
        IReadOnlyList<WorkflowEvent> workflowEvents = run.WatchStreamAsync().ToEnumerable().ToList();
        return new WorkflowEvents(workflowEvents);
    }
}
