// Copyright (c) Microsoft. All rights reserved.

using System;
using System.IO;
using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Agents.AI.Workflows.Sample;

/// <summary>
/// Tests for shared state preservation across subworkflow boundaries.
/// Validates fix for issue #2419: ".NET: Shared State is not preserved in Subworkflows"
/// </summary>
internal static partial class Step14EntryPoint
{
    public const string WordStateScope = "WordStateScope";

    /// <summary>
    /// Tests that shared state works WITHIN a subworkflow (internal persistence).
    /// This tests whether state written by one executor in a subworkflow can be
    /// read by another executor in the SAME subworkflow.
    /// </summary>
    public static async ValueTask<int> RunSubworkflowInternalStateAsync(string text, TextWriter writer, IWorkflowExecutionEnvironment environment)
    {
        // All three executors are INSIDE the subworkflow
        TextReadExecutor textRead = new();
        TextTrimExecutor textTrim = new();
        CharCountingExecutor charCount = new();

        Workflow subWorkflow = new WorkflowBuilder(textRead)
            .AddEdge(textRead, textTrim)
            .AddEdge(textTrim, charCount)
            .WithOutputFrom(charCount)
            .Build();

        ExecutorBinding subWorkflowStep = subWorkflow.BindAsExecutor("internalStateSubworkflow");

        // Parent workflow just wraps the subworkflow
        Workflow workflow = new WorkflowBuilder(subWorkflowStep)
            .WithOutputFrom(subWorkflowStep)
            .Build();

        await using Run run = await environment.RunAsync(workflow, text);

        int? result = null;
        foreach (WorkflowEvent evt in run.OutgoingEvents)
        {
            if (evt is WorkflowOutputEvent outputEvent)
            {
                result = outputEvent.As<int>();
                writer.WriteLine($"Subworkflow internal state result: {result}");
            }
            else if (evt is WorkflowErrorEvent failedEvent)
            {
                writer.WriteLine($"Workflow failed: {failedEvent.Data}");
                throw failedEvent.Data as Exception ?? new InvalidOperationException(failedEvent.Data?.ToString());
            }
        }

        return result ?? throw new InvalidOperationException("No output produced");
    }

    /// <summary>
    /// Tests cross-boundary state behavior (parent → subworkflow → parent).
    /// This documents the current behavior for issue #2419: state is isolated across subworkflow boundaries.
    /// </summary>
    public static async ValueTask<Exception?> RunCrossBoundaryStateAsync(string text, TextWriter writer, IWorkflowExecutionEnvironment environment)
    {
        TextReadExecutor textRead = new();
        TextTrimExecutor textTrim = new();
        CharCountingExecutor charCount = new();

        // Create a subworkflow containing just the trim executor
        Workflow subWorkflow = new WorkflowBuilder(textTrim)
            .WithOutputFrom(textTrim)
            .Build();

        ExecutorBinding subWorkflowStep = subWorkflow.BindAsExecutor("textTrimSubworkflow");

        // Create the main workflow: parent → subworkflow → parent
        Workflow workflow = new WorkflowBuilder(textRead)
            .AddEdge(textRead, subWorkflowStep)
            .AddEdge(subWorkflowStep, charCount)
            .WithOutputFrom(charCount)
            .Build();

        await using Run run = await environment.RunAsync(workflow, text);

        foreach (WorkflowEvent evt in run.OutgoingEvents)
        {
            if (evt is WorkflowOutputEvent outputEvent)
            {
                writer.WriteLine($"Cross-boundary state result: {outputEvent.As<int>()}");
                return null; // Success - no error
            }
            else if (evt is WorkflowErrorEvent failedEvent)
            {
                writer.WriteLine($"Workflow failed: {failedEvent.Data}");
                return failedEvent.Data as Exception;
            }
        }

        return new InvalidOperationException("No output produced");
    }

    /// <summary>
    /// Executor that reads text and stores it in shared state with a generated key.
    /// </summary>
    internal sealed partial class TextReadExecutor() : Executor("TextReadExecutor")
    {
        [MessageHandler]
        public async ValueTask<string> HandleAsync(string text, IWorkflowContext context, CancellationToken cancellationToken = default)
        {
            string key = Guid.NewGuid().ToString();
            await context.QueueStateUpdateAsync(key, text, scopeName: WordStateScope, cancellationToken);
            return key;
        }
    }

    /// <summary>
    /// Executor that reads text from shared state, trims it, and updates the state.
    /// </summary>
    internal sealed partial class TextTrimExecutor() : Executor("TextTrimExecutor")
    {
        [MessageHandler]
        public async ValueTask<string> HandleAsync(string key, IWorkflowContext context, CancellationToken cancellationToken = default)
        {
            string? content = await context.ReadStateAsync<string>(key, scopeName: WordStateScope, cancellationToken);
            if (content is null)
            {
                throw new InvalidOperationException($"Word state not found for key: {key}");
            }

            string trimmed = content.Trim();
            await context.QueueStateUpdateAsync(key, trimmed, scopeName: WordStateScope, cancellationToken);
            return key;
        }
    }

    /// <summary>
    /// Executor that reads text from shared state and returns its character count.
    /// </summary>
    internal sealed partial class CharCountingExecutor() : Executor("CharCountingExecutor")
    {
        [MessageHandler]
        public async ValueTask<int> HandleAsync(string key, IWorkflowContext context, CancellationToken cancellationToken = default)
        {
            string? content = await context.ReadStateAsync<string>(key, scopeName: WordStateScope, cancellationToken);
            return content?.Length ?? 0;
        }
    }
}
