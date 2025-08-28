// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.Workflows;
using Microsoft.Agents.Workflows.Reflection;

namespace Workflow;

/// <summary>
/// This class demonstrates a simple sequential workflow with two executors in streaming mode.
/// The sample is identical to Step01a_Sequential, except that it streams back events as the
/// workflow runs.
/// </summary>
public class Step01b_Sequential_Streaming(ITestOutputHelper output) : WorkflowSample(output)
{
    [Fact]
    public async Task RunAsync()
    {
        // Create the executors
        UppercaseExecutor uppercase = new();
        ReverseTextExecutor reverse = new();

        // Build the workflow
        WorkflowBuilder builder = new(uppercase);
        builder.AddEdge(uppercase, reverse);
        var workflow = builder.Build<string>();

        // Execute the workflow in streaming mode
        StreamingRun run = await InProcessExecution.StreamAsync(workflow, "Hello, World!");
        await foreach (WorkflowEvent evt in run.WatchStreamAsync().ConfigureAwait(false))
        {
            if (evt is ExecutorCompleteEvent executorComplete)
            {
                Console.WriteLine($"{executorComplete.ExecutorId}: {executorComplete.Data}");
            }
        }
    }

    private sealed class UppercaseExecutor() : ReflectingExecutor<UppercaseExecutor>("UppercaseExecutor"), IMessageHandler<string, string>
    {
        public async ValueTask<string> HandleAsync(string message, IWorkflowContext context)
        {
            string result = message.ToUpperInvariant();
            return result;
        }
    }

    private sealed class ReverseTextExecutor() : ReflectingExecutor<ReverseTextExecutor>("ReverseTextExecutor"), IMessageHandler<string, string>
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
}
