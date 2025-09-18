// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Linq;
using System.Threading.Tasks;
using Microsoft.Agents.Workflows;
using Microsoft.Agents.Workflows.Reflection;

namespace WorkflowStreamingSample;

/// <summary>
/// This sample introduces streaming output in workflows.
///
/// While 01_Executors_And_Edges waits for the entire workflow to complete before showing results,
/// this example streams events back to you in real-time as each executor finishes processing.
/// This is useful for monitoring long-running workflows or providing live feedback to users.
///
/// The workflow logic is identical: uppercase text, then reverse it. The difference is in
/// how we observe the execution - we see intermediate results as they happen.
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

        // Execute the workflow in streaming mode
        StreamingRun run = await InProcessExecution.StreamAsync(workflow, "Hello, World!");
        await foreach (WorkflowEvent evt in run.WatchStreamAsync().ConfigureAwait(false))
        {
            if (evt is ExecutorCompletedEvent executorCompleted)
            {
                Console.WriteLine($"{executorCompleted.ExecutorId}: {executorCompleted.Data}");
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
