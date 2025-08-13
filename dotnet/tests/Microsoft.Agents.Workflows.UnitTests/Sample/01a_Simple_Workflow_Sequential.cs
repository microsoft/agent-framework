// Copyright (c) Microsoft. All rights reserved.

using System.IO;
using System.Threading.Tasks;

namespace Microsoft.Agents.Workflows.Sample;

internal static class Step1aEntryPoint
{
    public static async ValueTask RunAsync(TextWriter writer)
    {
        UppercaseExecutor uppercase = new();
        ReverseTextExecutor reverse = new();

        WorkflowBuilder builder = new(uppercase);
        builder.AddEdge(uppercase, reverse);

        Workflow<string> workflow = builder.Build<string>();

        Run run = await InProcessExecution.RunAsync(workflow, "Hello, World!").ConfigureAwait(false);

        Assert.Equal(RunStatus.Completed, run.Status);

        foreach (WorkflowEvent evt in run.NewEvents)
        {
            if (evt is ExecutorCompleteEvent executorComplete)
            {
                writer.WriteLine($"{executorComplete.ExecutorId}: {executorComplete.Data}");
            }
        }
    }
}
