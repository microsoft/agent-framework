// Copyright (c) Microsoft. All rights reserved.

using System;
using System.IO;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.Reflection;

namespace Microsoft.Agents.AI.Workflows.Sample;

internal static class Step1EntryPoint
{
    public static Workflow WorkflowInstance
    {
        get
        {
            UppercaseExecutor uppercase = new();
            ReverseTextExecutor reverse = new();

            WorkflowBuilder builder = new(uppercase);
            builder.AddEdge(uppercase, reverse).WithOutputFrom(reverse);

            return builder.Build();
        }
    }

    public static async ValueTask RunAsync(TextWriter writer, IWorkflowExecutionEnvironment environment)
    {
        StreamingRun run = await environment.StreamAsync(WorkflowInstance, input: "Hello, World!").ConfigureAwait(false);

        await foreach (WorkflowEvent evt in run.WatchStreamAsync().ConfigureAwait(false))
        {
            if (evt is ExecutorCompletedEvent executorCompleted)
            {
                writer.WriteLine($"{executorCompleted.ExecutorId}: {executorCompleted.Data}");
            }
        }
    }
}

internal sealed class UppercaseExecutor() : ReflectingExecutor<UppercaseExecutor>("UppercaseExecutor", declareCrossRunShareable: true), IMessageHandler<string, string>
{
    public async ValueTask<string> HandleAsync(string message, IWorkflowContext context, CancellationToken cancellationToken = default) =>
        message.ToUpperInvariant();
}

internal sealed class ReverseTextExecutor() : ReflectingExecutor<ReverseTextExecutor>("ReverseTextExecutor", declareCrossRunShareable: true), IMessageHandler<string, string>
{
    public async ValueTask<string> HandleAsync(string message, IWorkflowContext context, CancellationToken cancellationToken = default)
    {
        string result = string.Concat(message.Reverse());

        await context.YieldOutputAsync(result, cancellationToken).ConfigureAwait(false);
        return result;
    }
}
