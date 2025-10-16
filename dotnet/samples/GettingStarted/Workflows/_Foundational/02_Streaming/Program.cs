// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.Workflows;

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
        builder.AddEdge(uppercase, reverse).WithOutputFrom(reverse);
        var workflow = builder.Build();

        // Execute the workflow in streaming mode
        await using StreamingRun run = await InProcessExecution.StreamAsync(workflow, "Hello, World!");
        await foreach (WorkflowEvent evt in run.WatchStreamAsync())
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
internal sealed class UppercaseExecutor() : Executor<string, string>("UppercaseExecutor")
{
    /// <summary>
    /// Processes the input message by converting it to uppercase.
    /// </summary>
    /// <param name="message">The input text to convert</param>
    /// <param name="context">Workflow context for accessing workflow services and adding events</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests.
    /// The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>The input text converted to uppercase</returns>
    public override ValueTask<string> HandleAsync(string message, IWorkflowContext context, CancellationToken cancellationToken = default) =>
        ValueTask.FromResult(message.ToUpperInvariant()); // The return value will be sent as a message along an edge to subsequent executors
}

/// <summary>
/// Second executor: reverses the input text and completes the workflow.
/// </summary>
internal sealed class ReverseTextExecutor() : Executor<string, string>("ReverseTextExecutor")
{
    /// <summary>
    /// Processes the input message by reversing the text.
    /// </summary>
    /// <param name="message">The input text to reverse</param>
    /// <param name="context">Workflow context for accessing workflow services and adding events</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests.
    /// The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>The input text reversed</returns>
    public override ValueTask<string> HandleAsync(string message, IWorkflowContext context, CancellationToken cancellationToken = default)
    {
        // Because we do not suppress it, the returned result will be yielded as an output from this executor.
        return ValueTask.FromResult(string.Concat(message.Reverse()));
    }
}
