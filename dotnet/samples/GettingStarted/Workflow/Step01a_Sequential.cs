// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.Workflows;
using Microsoft.Agents.Workflows.Reflection;

namespace Workflow;

/// <summary>
/// This class demonstrates a simple sequential workflow with two executors.
/// Executors and edges are basic building blocks of workflows. In this sample,
/// the workflow consists of an UppercaseExecutor followed by a ReverseTextExecutor.
/// The UpperCaseExecutor converts input text to uppercase, and the ReverseTextExecutor
/// reverses the text. The two executors are connected via an edge. Data flows from
/// one executor to the next through these edges. Together, the resulting workflow
/// processes the input text by first converting it to uppercase and then reversing it.
/// </summary>
public class Step01a_Sequential(ITestOutputHelper output) : WorkflowSample(output)
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

        // Execute the workflow
        Run run = await InProcessExecution.RunAsync(workflow, "Hello, World!");
        foreach (WorkflowEvent evt in run.NewEvents)
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
