// Copyright (c) Microsoft. All rights reserved.

using System.IO;
using System.Threading.Tasks;
using Microsoft.Agents.Workflows.Core;
using Microsoft.Agents.Workflows.Execution;

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
        LocalRunner<string> runner = new(workflow);

        //var handle = await runner.StreamAsync("Hello, World!").ConfigureAwait(false);

        Run run = await runner.RunAsync("Hello, World!").ConfigureAwait(false);

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
