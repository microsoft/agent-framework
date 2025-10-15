// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.Workflows;

namespace WorkflowSubWorkflowsSample;

/// <summary>
/// This sample demonstrates how to compose workflows hierarchically by using
/// a workflow as an executor within another workflow (sub-workflows).
///
/// A sub-workflow is a workflow that is embedded as an executor within a parent workflow.
/// This allows you to:
/// 1. Encapsulate and reuse complex workflow logic as modular components
/// 2. Build hierarchical workflow structures
/// 3. Create composable, maintainable workflow architectures
///
/// In this example, we create:
/// - A text processing sub-workflow (uppercase → reverse → append suffix)
/// - A parent workflow that adds a prefix, processes through the sub-workflow, and post-processes
///
/// For input "hello", the workflow produces: "INPUT: [FINAL] OLLEH [PROCESSED] [END]"
/// </summary>
public static class Program
{
    private static async Task Main()
    {
        Console.WriteLine("\n=== Sub-Workflow Demonstration ===\n");

        // Step 1: Build a simple text processing sub-workflow
        Console.WriteLine("Building sub-workflow: Uppercase → Reverse → Append Suffix...\n");

        UppercaseExecutor uppercase = new();
        ReverseExecutor reverse = new();
        AppendSuffixExecutor append = new(" [PROCESSED]");

        var subWorkflow = new WorkflowBuilder(uppercase)
            .AddEdge(uppercase, reverse)
            .AddEdge(reverse, append)
            .WithOutputFrom(append)
            .Build();

        // Step 2: Configure the sub-workflow as an executor for use in the parent workflow
        ExecutorIsh subWorkflowExecutor = subWorkflow.ConfigureSubWorkflow("TextProcessingSubWorkflow");

        // Step 3: Build a main workflow that uses the sub-workflow as an executor
        Console.WriteLine("Building main workflow that uses the sub-workflow as an executor...\n");

        PrefixExecutor prefix = new("INPUT: ");
        PostProcessExecutor postProcess = new();

        var mainWorkflow = new WorkflowBuilder(prefix)
            .AddEdge(prefix, subWorkflowExecutor)
            .AddEdge(subWorkflowExecutor, postProcess)
            .WithOutputFrom(postProcess)
            .Build();

        // Step 4: Execute the main workflow
        Console.WriteLine("Executing main workflow with input: 'hello'\n");
        await using Run run = await InProcessExecution.RunAsync(mainWorkflow, "hello");

        // Display results
        foreach (WorkflowEvent evt in run.NewEvents)
        {
            if (evt is ExecutorCompletedEvent executorComplete && executorComplete.Data is not null)
            {
                Console.ForegroundColor = ConsoleColor.Green;
                Console.WriteLine($"[{executorComplete.ExecutorId}] {executorComplete.Data}");
                Console.ResetColor();
            }
            else if (evt is WorkflowOutputEvent output)
            {
                Console.ForegroundColor = ConsoleColor.Cyan;
                Console.WriteLine("\n=== Main Workflow Completed ===");
                Console.WriteLine($"Final Output: {output.Data}");
                Console.ResetColor();
            }
        }

        // Optional: Visualize the workflow structure - Note that sub-workflows are not rendered
        Console.ForegroundColor = ConsoleColor.DarkGray;
        Console.WriteLine("\n=== Workflow Visualization ===\n");
        Console.WriteLine(mainWorkflow.ToMermaidString());
        Console.ResetColor();

        Console.WriteLine("\n✅ Sample Complete: Workflows can be composed hierarchically using sub-workflows\n");
    }
}

// ====================================
// Text Processing Executors
// ====================================

/// <summary>
/// Adds a prefix to the input text.
/// </summary>
internal sealed class PrefixExecutor(string prefix) : Executor<string, string>("PrefixExecutor")
{
    public override ValueTask<string> HandleAsync(string message, IWorkflowContext context, CancellationToken cancellationToken = default)
    {
        string result = prefix + message;
        Console.WriteLine($"[Prefix] '{message}' → '{result}'");
        return ValueTask.FromResult(result);
    }
}

/// <summary>
/// Converts input text to uppercase.
/// </summary>
internal sealed class UppercaseExecutor() : Executor<string, string>("UppercaseExecutor")
{
    public override ValueTask<string> HandleAsync(string message, IWorkflowContext context, CancellationToken cancellationToken = default)
    {
        string result = message.ToUpperInvariant();
        Console.WriteLine($"[Uppercase] '{message}' → '{result}'");
        return ValueTask.FromResult(result);
    }
}

/// <summary>
/// Reverses the input text.
/// </summary>
internal sealed class ReverseExecutor() : Executor<string, string>("ReverseExecutor")
{
    public override ValueTask<string> HandleAsync(string message, IWorkflowContext context, CancellationToken cancellationToken = default)
    {
        string result = string.Concat(message.Reverse());
        Console.WriteLine($"[Reverse] '{message}' → '{result}'");
        return ValueTask.FromResult(result);
    }
}

/// <summary>
/// Appends a suffix to the input text.
/// </summary>
internal sealed class AppendSuffixExecutor(string suffix) : Executor<string, string>("AppendSuffixExecutor")
{
    public override ValueTask<string> HandleAsync(string message, IWorkflowContext context, CancellationToken cancellationToken = default)
    {
        string result = message + suffix;
        Console.WriteLine($"[AppendSuffix] '{message}' → '{result}'");
        return ValueTask.FromResult(result);
    }
}

/// <summary>
/// Performs final post-processing by wrapping the text.
/// </summary>
internal sealed class PostProcessExecutor() : Executor<string, string>("PostProcessExecutor")
{
    public override ValueTask<string> HandleAsync(string message, IWorkflowContext context, CancellationToken cancellationToken = default)
    {
        string result = $"[FINAL] {message} [END]";
        Console.WriteLine($"[PostProcess] '{message}' → '{result}'");
        return ValueTask.FromResult(result);
    }
}
