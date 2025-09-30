// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using FluentAssertions;

namespace Microsoft.Agents.AI.Workflows.Sample;

internal sealed record class TextProcessingRequest(string Text, string TaskId);
internal sealed record class TextProcessingResult(string TaskId, string Text, int WordCount, int ChatCount);

internal sealed class AllTasksCompletedEvent(IEnumerable<TextProcessingResult> results) : WorkflowEvent(results);

internal static class Step8EntryPoint
{
    public static List<string> TextsToProcess => [
            "Hello world! This is a simple test.",
            "Python is a powerful programming language used for many applications.",
            "Short text.",
            "This is a longer text with multiple sentences. It contains more words and characters. We use it to test our text processing workflow.",
            "",
            "   Spaces   around   text   ",
        ];

    public static async ValueTask<List<TextProcessingResult>> RunAsync(TextWriter writer, List<string> textsToProcess)
    {
        Func<TextProcessingRequest, IWorkflowContext, CancellationToken, ValueTask> processTextAsyncFunc = ProcessTextAsync;
        ExecutorIsh processText = processTextAsyncFunc.AsExecutor("TextProcessor");

        Workflow subWorkflow = new WorkflowBuilder(processText).WithOutputFrom(processText).Build();

        ExecutorIsh textProcessor = subWorkflow.ConfigureSubWorkflow("TextProcessor");
        TextProcessingOrchestrator orchestrator = new();

        Workflow workflow = new WorkflowBuilder(orchestrator)
            .AddEdge(orchestrator, textProcessor)
            .AddEdge(textProcessor, orchestrator)
            .Build();

        Run workflowRun = await InProcessExecution.RunAsync(workflow, textsToProcess);

        RunStatus status = await workflowRun.GetStatusAsync();
        status.Should().Be(RunStatus.Idle);

        List<TextProcessingResult> results = orchestrator.Results;
        results.Sort((left, right) => StringComparer.Ordinal.Compare(left.TaskId, right.TaskId));

        // This is a placeholder for the entry point of Step 8.
        return results;
    }

    private static ValueTask ProcessTextAsync(TextProcessingRequest request, IWorkflowContext context, CancellationToken cancellation = default)
    {
        int wordCount = 0;
        int charCount = 0;

        if (request.Text.Length != 0)
        {
            wordCount = request.Text.Split([' '], StringSplitOptions.RemoveEmptyEntries).Length;
            charCount = request.Text.Length;
        }

        return context.YieldOutputAsync(new TextProcessingResult(request.TaskId, request.Text, wordCount, charCount));
    }

    private sealed class TextProcessingOrchestrator() : Executor("TextOrchestrator")
    {
        public List<TextProcessingResult> Results { get; } = new();
        public HashSet<string> PendingTaskIds { get; } = new();

        protected override RouteBuilder ConfigureRoutes(RouteBuilder routeBuilder)
        {
            return routeBuilder.AddHandler<List<string>>(this.StartProcessingAsync)
                               .AddHandler<TextProcessingResult>(this.CollectResultAsync);
        }

        private async ValueTask StartProcessingAsync(List<string> texts, IWorkflowContext context)
        {
            foreach (TextProcessingRequest request in texts.Select((string value, int index) => new TextProcessingRequest(Text: value, TaskId: $"Task{index}")))
            {
                this.PendingTaskIds.Add(request.TaskId);
                await context.SendMessageAsync(request).ConfigureAwait(false);
            }
        }

        private ValueTask CollectResultAsync(TextProcessingResult result, IWorkflowContext context)
        {
            if (this.PendingTaskIds.Remove(result.TaskId))
            {
                this.Results.Add(result);
            }

            if (this.PendingTaskIds.Count == 0)
            {
                return context.AddEventAsync(new AllTasksCompletedEvent(this.Results));
            }

            return default;
        }
    }
}
