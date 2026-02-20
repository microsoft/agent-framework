// Copyright (c) Microsoft. All rights reserved.

#pragma warning disable CS0618 // Type or member is obsolete - Testing legacy reflection-based pattern

using System;
using System.IO;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;

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
        StreamingRun run = await environment.RunStreamingAsync(WorkflowInstance, input: "Hello, World!").ConfigureAwait(false);

        await foreach (WorkflowEvent evt in run.WatchStreamAsync().ConfigureAwait(false))
        {
            if (evt is ExecutorCompletedEvent executorCompleted)
            {
                writer.WriteLine($"{executorCompleted.ExecutorId}: {executorCompleted.Data}");
            }
        }
    }
}

internal sealed class UppercaseExecutor() : Executor<string, string>(nameof(UppercaseExecutor), declareCrossRunShareable: true)
{
    public override async ValueTask<string> HandleAsync(string message, IWorkflowContext context, CancellationToken cancellationToken = default) =>
        message.ToUpperInvariant();
}

internal sealed class ReverseTextExecutor() : Executor("ReverseTextExecutor", declareCrossRunShareable: true)
{
    protected override ProtocolBuilder ConfigureProtocol(ProtocolBuilder protocolBuilder)
    {
        return protocolBuilder.ConfigureRoutes(routeBuilder => routeBuilder.AddHandler<string, string>(this.HandleAsync));
    }

    public async ValueTask<string> HandleAsync(string message, IWorkflowContext context, CancellationToken cancellationToken = default)
    {
        string result = string.Concat(message.Reverse());

        await context.YieldOutputAsync(result, cancellationToken).ConfigureAwait(false);
        return result;
    }
}
