// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.Workflows;
using Microsoft.Agents.Workflows.Reflection;
using Microsoft.Shared.Samples;

namespace Workflow;

/// <summary>
/// This sample introduces the concept of shared states within a workflow.
/// It demonstrates how multiple executors can read from and write to shared states,
/// allowing for more complex data sharing and coordination between tasks.
/// </summary>
/// <remarks>
/// Pre-requisites:
/// - Foundational samples must be completed first.
/// - This sample also uses the fan-out and fan-in patterns to achieve parallel processing.
/// </remarks>
public class WorkflowSharedStates(ITestOutputHelper output) : WorkflowSample(output)
{
    private const string FileContentStateScope = "FileContentStateScope";

    [Fact]
    public async Task RunAsync()
    {
        // Create the executors
        var fileRead = new FileReadExecutor();
        var wordCount = new WordCountingExecutor();
        var paragraphCount = new ParagraphCountingExecutor();
        var aggregate = new AggregationExecutor();

        // Build the workflow by connecting executors sequentially
        WorkflowBuilder builder = new(fileRead);
        builder.AddFanOutEdge(fileRead, targets: [wordCount, paragraphCount]);
        builder.AddFanInEdge(aggregate, sources: [wordCount, paragraphCount]);
        var workflow = builder.Build<string>();

        // Execute the workflow with input data
        Run run = await InProcessExecution.RunAsync(workflow, "Lorem_Ipsum.txt");
        foreach (WorkflowEvent evt in run.NewEvents)
        {
            if (evt is WorkflowCompletedEvent workflowCompleted)
            {
                Console.WriteLine(workflowCompleted.Data);
            }
        }
    }

    private sealed class FileReadExecutor() : ReflectingExecutor<FileReadExecutor>("FileReadExecutor"), IMessageHandler<string, string>
    {
        public async ValueTask<string> HandleAsync(string message, IWorkflowContext context)
        {
            // Read file content from embedded resource
            string fileContent = Resources.Read(message);
            // Store file content in a shared state for access by other executors
            string fileID = Guid.NewGuid().ToString();
            await context.QueueStateUpdateAsync<string>(fileID, fileContent, scopeName: FileContentStateScope);

            return fileID;
        }
    }

    private sealed class FileStats
    {
        public int ParagraphCount { get; set; }
        public int WordCount { get; set; }
    }

    private sealed class WordCountingExecutor() : ReflectingExecutor<WordCountingExecutor>("WordCountingExecutor"), IMessageHandler<string, FileStats>
    {
        public async ValueTask<FileStats> HandleAsync(string message, IWorkflowContext context)
        {
            // Retrieve the file content from the shared state
            var fileContent = await context.ReadStateAsync<string>(message, scopeName: FileContentStateScope)
                ?? throw new InvalidOperationException("File content state not found");

            int wordCount = fileContent.Split([' ', '\n', '\r'], StringSplitOptions.RemoveEmptyEntries).Length;

            return new FileStats { WordCount = wordCount };
        }
    }

    private sealed class ParagraphCountingExecutor() : ReflectingExecutor<ParagraphCountingExecutor>("ParagraphCountingExecutor"), IMessageHandler<string, FileStats>
    {
        public async ValueTask<FileStats> HandleAsync(string message, IWorkflowContext context)
        {
            // Retrieve the file content from the shared state
            var fileContent = await context.ReadStateAsync<string>(message, scopeName: FileContentStateScope)
                ?? throw new InvalidOperationException("File content state not found");

            int paragraphCount = fileContent.Split(['\n', '\r'], StringSplitOptions.RemoveEmptyEntries).Length;

            return new FileStats { ParagraphCount = paragraphCount };
        }
    }

    private sealed class AggregationExecutor() : ReflectingExecutor<AggregationExecutor>("AggregationExecutor"), IMessageHandler<FileStats>
    {
        private readonly List<FileStats> _messages = [];

        public async ValueTask HandleAsync(FileStats message, IWorkflowContext context)
        {
            _messages.Add(message);

            if (_messages.Count == 2)
            {
                // Aggregate the results from both executors
                var totalParagraphCount = _messages.Sum(m => m.ParagraphCount);
                var totalWordCount = _messages.Sum(m => m.WordCount);
                await context.AddEventAsync(new WorkflowCompletedEvent($"Total Paragraphs: {totalParagraphCount}, Total Words: {totalWordCount}"));
            }
        }
    }
}
