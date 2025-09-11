// Copyright (c) Microsoft. All rights reserved.

using System.IO;
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
    public async ValueTask<string> HandleAsync(string message, IWorkflowContext context)
    {
        string result = message.ToUpperInvariant();
        return result;
    }
}

internal sealed class ReverseTextExecutor() : ReflectingExecutor<ReverseTextExecutor>("ReverseTextExecutor"), IMessageHandler<string, string>
{
    public async ValueTask<string> HandleAsync(string message, IWorkflowContext context)
    {
        char[] charArray = message.ToCharArray();
        System.Array.Reverse(charArray);
        string result = new(charArray);

        await context.AddEventAsync(new WorkflowCompletedEvent(result)).ConfigureAwait(false);
        return result;
    }
}
