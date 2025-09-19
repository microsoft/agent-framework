// Copyright (c) Microsoft. All rights reserved.

using System.IO;
using System.Linq;
using System.Threading.Tasks;
using Microsoft.Agents.Workflows.Reflection;

namespace Microsoft.Agents.Workflows.Sample;

internal static class Step1EntryPoint
{
    public static Workflow<string> WorkflowInstance
    {
        get
        {
            UppercaseExecutor uppercase = new();
            ReverseTextExecutor reverse = new();

            WorkflowBuilder builder = new(uppercase);
            builder.AddEdge(uppercase, reverse);

            return builder.Build<string>();
        }
    }

    public static async ValueTask RunAsync(TextWriter writer)
    {
        StreamingRun run = await InProcessExecution.StreamAsync(WorkflowInstance, "Hello, World!").ConfigureAwait(false);

        await foreach (WorkflowEvent evt in run.WatchStreamAsync().ConfigureAwait(false))
        {
            if (evt is ExecutorCompletedEvent executorCompleted)
            {
                writer.WriteLine($"{executorCompleted.ExecutorId}: {executorCompleted.Data}");
            }
        }
    }
}

internal sealed class UppercaseExecutor() : ReflectingExecutor<UppercaseExecutor>("UppercaseExecutor"), IMessageHandler<string, string>
{
    public async ValueTask<string> HandleAsync(string message, IWorkflowContext context) =>
        message.ToUpperInvariant();
}

internal sealed class ReverseTextExecutor() : ReflectingExecutor<ReverseTextExecutor>("ReverseTextExecutor"), IMessageHandler<string, string>
{
    public async ValueTask<string> HandleAsync(string message, IWorkflowContext context)
    {
        string result = string.Concat(message.Reverse());

        await context.AddEventAsync(new WorkflowCompletedEvent(result)).ConfigureAwait(false);
        return result;
    }
}
