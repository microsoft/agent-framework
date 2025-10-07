// Copyright (c) Microsoft. All rights reserved.

using System.IO;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.InProc;
using Microsoft.Agents.AI.Workflows.UnitTests;
using static Microsoft.Agents.AI.Workflows.Sample.Step1EntryPoint;

namespace Microsoft.Agents.AI.Workflows.Sample;

internal static class Step1aEntryPoint
{
    public static async ValueTask RunAsync(TextWriter writer, ExecutionMode executionMode)
    {
        InProcessExecutionEnvironment env = executionMode.GetEnvironment();
        Run run = await env.RunAsync(WorkflowInstance, "Hello, World!").ConfigureAwait(false);

        Assert.Equal(RunStatus.Idle, await run.GetStatusAsync());

        foreach (WorkflowEvent evt in run.NewEvents)
        {
            if (evt is ExecutorCompletedEvent executorCompleted)
            {
                writer.WriteLine($"{executorCompleted.ExecutorId}: {executorCompleted.Data}");
            }
        }
    }
}
