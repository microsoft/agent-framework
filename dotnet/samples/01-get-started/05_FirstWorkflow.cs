// Copyright (c) Microsoft. All rights reserved.

// Step 5: Your First Workflow
// Chain processing steps together in a sequential workflow.
// Executors are processing units connected by edges that define data flow.
//
// For more on workflows, see: ../03-workflows/
// For docs: https://learn.microsoft.com/agent-framework/workflows/overview

using Microsoft.Agents.AI.Workflows;

// <define_executors>
// First executor: converts input text to uppercase
Func<string, string> uppercaseFunc = s => s.ToUpperInvariant();
var uppercase = uppercaseFunc.BindAsExecutor("UppercaseExecutor");

// Second executor: reverses the text
var reverse = new ReverseTextExecutor();
// </define_executors>

// <build_workflow>
WorkflowBuilder builder = new(uppercase);
builder.AddEdge(uppercase, reverse).WithOutputFrom(reverse);
var workflow = builder.Build();
// </build_workflow>

// <run_workflow>
await using Run run = await InProcessExecution.RunAsync(workflow, "Hello, World!");
foreach (WorkflowEvent evt in run.NewEvents)
{
    if (evt is ExecutorCompletedEvent executorComplete)
    {
        Console.WriteLine($"{executorComplete.ExecutorId}: {executorComplete.Data}");
    }
}
// </run_workflow>

/// <summary>
/// Executor that reverses the input text.
/// </summary>
internal sealed class ReverseTextExecutor() : Executor<string, string>("ReverseTextExecutor")
{
    public override ValueTask<string> HandleAsync(string message, IWorkflowContext context, CancellationToken cancellationToken = default)
        => ValueTask.FromResult(string.Concat(message.Reverse()));
}
