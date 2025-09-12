// Copyright (c) Microsoft. All rights reserved.

using System.IO;
using System.Threading.Tasks;

using static Microsoft.Agents.Workflows.Sample.Step1EntryPoint;

namespace Microsoft.Agents.Workflows.Sample;

internal static class Step1aEntryPoint
{
    public static async ValueTask RunAsync(TextWriter writer)
    {
        Run run = await InProcessExecution.RunAsync(WorkflowInstance, "Hello, World!").ConfigureAwait(false);

        Assert.Equal(RunStatus.Completed, run.Status);

        foreach (WorkflowEvent evt in run.NewEvents)
        {
            if (evt is ExecutorCompletedEvent executorCompleted)
            {
                writer.WriteLine($"{executorCompleted.ExecutorId}: {executorCompleted.Data}");
            }
        }
    }
}
