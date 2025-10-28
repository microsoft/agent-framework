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

//internal sealed class AllTasksCompletedEvent(IEnumerable<TextProcessingResult> results) : WorkflowEvent(results);

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

    public static async ValueTask<List<TextProcessingResult>> RunAsync(TextWriter writer, IWorkflowExecutionEnvironment environment, List<string> textsToProcess)
    {
        Func<TextProcessingRequest, IWorkflowContext, CancellationToken, ValueTask> processTextAsyncFunc = ProcessTextAsync;
        ExecutorIsh processText = processTextAsyncFunc.AsExecutor("TextProcessor", threadsafe: true);

        Workflow subWorkflow = new WorkflowBuilder(processText).WithOutputFrom(processText).Build();

        ExecutorIsh textProcessor = subWorkflow.ConfigureSubWorkflow("TextProcessor");
        Func<string, string, ValueTask<Executor>> createOrchestrator = (id, _) => new(new TextProcessingOrchestrator(id));
        var orchestrator = createOrchestrator.ConfigureFactory();

        Workflow workflow = new WorkflowBuilder(orchestrator)
            .AddEdge(orchestrator, textProcessor)
            .AddEdge(textProcessor, orchestrator)
            .WithOutputFrom(orchestrator)
            .Build();

        Run workflowRun = await environment.RunAsync(workflow, textsToProcess);

        RunStatus status = await workflowRun.GetStatusAsync();
        status.Should().Be(RunStatus.Idle);

        WorkflowOutputEvent? maybeOutput = workflowRun.OutgoingEvents.OfType<WorkflowOutputEvent>()
                                                                     .SingleOrDefault();

        maybeOutput.Should().NotBeNull("the workflow should have produced an output event");
        List<TextProcessingResult>? maybeResults = maybeOutput.As<List<TextProcessingResult>>();

        maybeResults.Should().NotBeNull("the output event should contain the results");
        List<TextProcessingResult> results = maybeResults;

        results.Sort((left, right) => StringComparer.Ordinal.Compare(left.TaskId, right.TaskId));

        return results;
    }

    private static ValueTask ProcessTextAsync(TextProcessingRequest request, IWorkflowContext context, CancellationToken cancellationToken = default)
    {
        int wordCount = 0;
        int charCount = 0;

        if (request.Text.Length != 0)
        {
            wordCount = request.Text.Split([' '], StringSplitOptions.RemoveEmptyEntries).Length;
            charCount = request.Text.Length;
        }

        return context.YieldOutputAsync(new TextProcessingResult(request.TaskId, request.Text, wordCount, charCount), cancellationToken);
    }

    private sealed class TextProcessingOrchestrator(string id)
        : StatefulExecutor<TextProcessingOrchestrator.State>(id, () => new(), declareCrossRunShareable: false)
    {
        internal sealed class State
        {
            public List<TextProcessingResult> Results { get; } = new();
            public HashSet<string> PendingTaskIds { get; } = new();

            public bool IsComplete => this.PendingTaskIds.Count == 0;

            public void AddPending(string taskId) => this.PendingTaskIds.Add(taskId);
            public bool CompletePending(string taskId) => this.PendingTaskIds.Remove(taskId);
        }

        protected override RouteBuilder ConfigureRoutes(RouteBuilder routeBuilder)
        {
            return routeBuilder.AddHandler<List<string>>(this.StartProcessingAsync)
                               .AddHandler<TextProcessingResult>(this.CollectResultAsync);
        }

        private async ValueTask StartProcessingAsync(List<string> texts, IWorkflowContext context, CancellationToken cancellationToken)
        {
            await this.InvokeWithStateAsync(QueueProcessingTasksAsync, context, cancellationToken: cancellationToken);

            async ValueTask<State?> QueueProcessingTasksAsync(State state, IWorkflowContext context, CancellationToken cancellationToken)
            {
                foreach (TextProcessingRequest request in texts.Select((string value, int index) => new TextProcessingRequest(Text: value, TaskId: $"Task{index}")))
                {
                    state.PendingTaskIds.Add(request.TaskId);
                    await context.SendMessageAsync(request, cancellationToken: cancellationToken).ConfigureAwait(false);
                }

                return state;
            }
        }

        private async ValueTask CollectResultAsync(TextProcessingResult result, IWorkflowContext context, CancellationToken cancellationToken = default)
        {
            await this.InvokeWithStateAsync(CollectResultAndCheckCompletionAsync, context, cancellationToken: cancellationToken);

            async ValueTask<State?> CollectResultAndCheckCompletionAsync(State state, IWorkflowContext context, CancellationToken cancellationToken)
            {
                if (state.PendingTaskIds.Remove(result.TaskId))
                {
                    state.Results.Add(result);
                }

                if (state.PendingTaskIds.Count == 0)
                {
                    await context.YieldOutputAsync(state.Results, cancellationToken).ConfigureAwait(false);
                }

                return state;
            }
        }
    }
}
