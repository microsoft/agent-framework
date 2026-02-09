// Copyright (c) Microsoft. All rights reserved.
// Description: Linear step-by-step workflow with executors connected sequentially.
// Docs: https://learn.microsoft.com/agent-framework/workflows/overview

using Microsoft.Agents.AI.Workflows;

namespace WorkflowSamples.Sequential;

// <sequential_workflow>
/// <summary>
/// Demonstrates a sequential workflow where executors are connected in a linear chain.
/// Data flows from one executor to the next in order.
/// For input "Hello, World!", the workflow produces "!DLROW ,OLLEH".
/// </summary>
public static class Program
{
    private static async Task Main()
    {
        // Create the executors
        Func<string, string> uppercaseFunc = s => s.ToUpperInvariant();
        var uppercase = uppercaseFunc.BindAsExecutor("UppercaseExecutor");

        ReverseTextExecutor reverse = new();

        // Build the workflow by connecting executors sequentially
        WorkflowBuilder builder = new(uppercase);
        builder.AddEdge(uppercase, reverse).WithOutputFrom(reverse);
        var workflow = builder.Build();

        // Execute the workflow with input data
        await using Run run = await InProcessExecution.RunAsync(workflow, "Hello, World!");
        foreach (WorkflowEvent evt in run.NewEvents)
        {
            if (evt is ExecutorCompletedEvent executorComplete)
            {
                Console.WriteLine($"{executorComplete.ExecutorId}: {executorComplete.Data}");
            }
        }
    }
}
// </sequential_workflow>

// <reverse_text_executor>
/// <summary>
/// Executor that reverses the input text.
/// </summary>
internal sealed class ReverseTextExecutor() : Executor<string, string>("ReverseTextExecutor")
{
    public override ValueTask<string> HandleAsync(string message, IWorkflowContext context, CancellationToken cancellationToken = default)
    {
        return ValueTask.FromResult(string.Concat(message.Reverse()));
    }
}
// </reverse_text_executor>
