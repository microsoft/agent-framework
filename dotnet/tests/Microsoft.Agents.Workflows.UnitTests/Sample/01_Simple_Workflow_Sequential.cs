// Copyright (c) Microsoft. All rights reserved.

using System.IO;
using System.Threading.Tasks;
using Microsoft.Agents.Workflows.Core;
using Microsoft.Agents.Workflows.Execution;

namespace Microsoft.Agents.Workflows.Sample;

internal static class Step1EntryPoint
{
    public static async ValueTask RunAsync(TextWriter writer)
    {
        UppercaseExecutor uppercase = new();
        ReverseTextExecutor reverse = new();

        WorkflowBuilder builder = new(uppercase);
        builder.AddEdge(uppercase, reverse);

        Workflow<string> workflow = builder.Build<string>();
        LocalRunner<string> runner = new(workflow);

        var handle = await runner.StreamAsync("Hello, World!").ConfigureAwait(false);

        await foreach (WorkflowEvent evt in handle.WatchStreamAsync().ConfigureAwait(false))
        {
            if (evt is ExecutorCompleteEvent executorComplete)
            {
                writer.WriteLine($"{executorComplete.ExecutorId}: {executorComplete.Data}");
            }
        }
    }
}

internal sealed class UppercaseExecutor() : Executor<UppercaseExecutor>("UppercaseExecutor"), IMessageHandler<string, string>
{
    public async ValueTask<string> HandleAsync(string message, IWorkflowContext context)
    {
        string result = message.ToUpperInvariant();

        await context.SendMessageAsync(result).ConfigureAwait(false);
        return result;
    }
}

internal sealed class ReverseTextExecutor() : Executor<ReverseTextExecutor>("ReverseTextExecutor"), IMessageHandler<string, string>
{
    public async ValueTask<string> HandleAsync(string message, IWorkflowContext context)
    {
        char[] charArray = message.ToCharArray();
        System.Array.Reverse(charArray);
        string result = new(charArray);

        await context.SendMessageAsync(result).ConfigureAwait(false);
        await context.AddEventAsync(new WorkflowCompletedEvent() { Data = result }).ConfigureAwait(false);
        return result;
    }
}
