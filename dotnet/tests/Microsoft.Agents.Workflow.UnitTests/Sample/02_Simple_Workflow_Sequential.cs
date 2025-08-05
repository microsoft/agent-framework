// Copyright (c) Microsoft. All rights reserved.

using System.Threading.Tasks;
using Microsoft.Agents.Workflows.Core;
using Microsoft.Agents.Workflows.Execution;

namespace Microsoft.Agents.Workflows.Sample;

internal static class Step2EntryPoint
{
    public static async ValueTask RunAsync()
    {
        UppercaseExecutor uppercase = new();
        ReverseTextExecutor reverse = new();

        WorkflowBuilder builder = new(uppercase);
        builder.AddEdge(uppercase, reverse);

        Workflow<string> workflow = builder.Build<string>();
        LocalRunner<string> runner = new(workflow);

        var handle = await runner.StreamAsync("Hello, World!").ConfigureAwait(false);
        await handle.RunToCompletionAsync().ConfigureAwait(false);
    }
}

internal sealed class UppercaseExecutor : Executor, IMessageHandler<string, string>
{
    public ValueTask<string> HandleAsync(string message, IWorkflowContext context)
    {
        return CompletedValueTaskSource.FromResult(message.ToUpperInvariant());
    }
}

internal sealed class ReverseTextExecutor : Executor, IMessageHandler<string, string>
{
    public ValueTask<string> HandleAsync(string message, IWorkflowContext context)
    {
        char[] charArray = message.ToCharArray();
        System.Array.Reverse(charArray);
        return CompletedValueTaskSource.FromResult(new string(charArray));
    }
}
