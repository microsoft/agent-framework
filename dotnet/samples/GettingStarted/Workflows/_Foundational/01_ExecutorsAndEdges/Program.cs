// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Linq;
using System.Threading.Tasks;
using Microsoft.Agents.Workflows;
using Microsoft.Agents.Workflows.Reflection;

namespace WorkflowExecutorsAndEdgesSample;

/// <summary>
/// This sample introduces the concepts of executors and edges in a workflow.
///
/// Workflows are built from executors (processing units) connected by edges (data flow paths).
/// In this example, we create a simple text processing pipeline that:
/// 1. Takes input text and converts it to uppercase using an UppercaseExecutor
/// 2. Takes the uppercase text and reverses it using a ReverseTextExecutor
///
/// The executors are connected sequentially, so data flows from one to the next in order.
/// For input "Hello, World!", the workflow produces "!DLROW ,OLLEH".
/// </summary>
public static class Program
{
    private static async Task Main()
    {
        // Create the executors
        UppercaseExecutor uppercase = new();
        ReverseTextExecutor reverse = new();

        // Build the workflow by connecting executors sequentially
        WorkflowBuilder builder = new(uppercase);
        builder.AddEdge(uppercase, reverse);
        var workflow = builder.Build<string>();

        // Execute the workflow with input data
        Run run = await InProcessExecution.RunAsync(workflow, "Hello, World!");
        foreach (WorkflowEvent evt in run.NewEvents)
        {
            if (evt is ExecutorCompletedEvent executorComplete)
            {
                Console.WriteLine($"{executorComplete.ExecutorId}: {executorComplete.Data}");
            }
        }
    }
}

/// <summary>
/// First executor: converts input text to uppercase.
/// </summary>
internal sealed class UppercaseExecutor() : ReflectingExecutor<UppercaseExecutor>("UppercaseExecutor"), IMessageHandler<string, string>
{
    /// <summary>
    /// Processes the input message by converting it to uppercase.
    /// </summary>
    /// <param name="message">The input text to convert</param>
    /// <param name="context">Workflow context for accessing workflow services and adding events</param>
    /// <returns>The input text converted to uppercase</returns>
    public async ValueTask<string> HandleAsync(string message, IWorkflowContext context) =>
        message.ToUpperInvariant(); // The return value will be sent as a message along an edge to subsequent executors
}

/// <summary>
/// Second executor: reverses the input text and completes the workflow.
/// </summary>
internal sealed class ReverseTextExecutor() : ReflectingExecutor<ReverseTextExecutor>("ReverseTextExecutor"), IMessageHandler<string, string>
{
    /// <summary>
    /// Processes the input message by reversing the text.
    /// </summary>
    /// <param name="message">The input text to reverse</param>
    /// <param name="context">Workflow context for accessing workflow services and adding events</param>
    /// <returns>The input text reversed</returns>
    public async ValueTask<string> HandleAsync(string message, IWorkflowContext context)
    {
        string result = string.Concat(message.Reverse());

        // Signal that the workflow is complete
        await context.AddEventAsync(new WorkflowCompletedEvent(result)).ConfigureAwait(false);

        return result;
    }
}
