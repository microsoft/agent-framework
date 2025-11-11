// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.Workflows;

namespace WorkflowSharedStatesSample;

/// <summary>
/// This sample introduces the concept of shared states within a workflow.
/// It demonstrates how multiple executors can read from and write to shared states,
/// allowing for more complex data sharing and coordination between tasks.
/// </summary>
/// <remarks>
/// Pre-requisites:
/// - Foundational samples should be completed first.
/// - This sample also uses the fan-out and fan-in patterns to achieve parallel processing.
/// </remarks>
public static class Program
{
    private static async Task Main()
    {
        // Create the executors
        var fileRead = new FileReadExecutor();
        var wordCount = new WordCountingExecutor();
        var paragraphCount = new ParagraphCountingExecutor();
        var aggregate = new AggregationExecutor();

        // Build the workflow by connecting executors sequentially
        var workflow = new WorkflowBuilder(fileRead)
            .AddFanOutEdge(fileRead, [wordCount, paragraphCount])
            .AddFanInEdge([wordCount, paragraphCount], aggregate)
            .WithOutputFrom(aggregate)
            .Build();

        // Execute the workflow with input data
        await using Run run = await InProcessExecution.RunAsync(workflow, "Lorem_Ipsum.txt");
        foreach (WorkflowEvent evt in run.NewEvents)
        {
            if (evt is WorkflowOutputEvent outputEvent)
            {
                Console.WriteLine(outputEvent.Data);
            }
        }
    }
}

/// <summary>
/// Constants for shared state scopes.
/// </summary>
internal static class FileContentStateConstants
{
    public const string FileContentStateScope = "FileContentState";
}

internal sealed class FileReadExecutor() : Executor<string, string>("FileReadExecutor")
{
    public override async ValueTask<string> HandleAsync(string message, IWorkflowContext context, CancellationToken cancellationToken = default)
    {
        // Read file content from embedded resource
        string fileContent = Resources.Read(message);
        // Store file content in a shared state for access by other executors
        string fileID = Guid.NewGuid().ToString("N");
        await context.QueueStateUpdateAsync(fileID, fileContent, scopeName: FileContentStateConstants.FileContentStateScope, cancellationToken);

        return fileID;
    }
}

internal sealed class FileStats
{
    public int ParagraphCount { get; set; }
    public int WordCount { get; set; }
}

internal sealed class WordCountingExecutor() : Executor<string, FileStats>("WordCountingExecutor")
{
    public override async ValueTask<FileStats> HandleAsync(string message, IWorkflowContext context, CancellationToken cancellationToken = default)
    {
        // Retrieve the file content from the shared state
        var fileContent = await context.ReadStateAsync<string>(message, scopeName: FileContentStateConstants.FileContentStateScope, cancellationToken)
            ?? throw new InvalidOperationException("File content state not found");

        int wordCount = fileContent.Split([' ', '\n', '\r'], StringSplitOptions.RemoveEmptyEntries).Length;

        return new FileStats { WordCount = wordCount };
    }
}

internal sealed class ParagraphCountingExecutor() : Executor<string, FileStats>("ParagraphCountingExecutor")
{
    public override async ValueTask<FileStats> HandleAsync(string message, IWorkflowContext context, CancellationToken cancellationToken = default)
    {
        // Retrieve the file content from the shared state
        var fileContent = await context.ReadStateAsync<string>(message, scopeName: FileContentStateConstants.FileContentStateScope, cancellationToken)
            ?? throw new InvalidOperationException("File content state not found");

        int paragraphCount = fileContent.Split(['\n', '\r'], StringSplitOptions.RemoveEmptyEntries).Length;

        return new FileStats { ParagraphCount = paragraphCount };
    }
}

internal sealed class AggregationExecutor() : Executor<FileStats>("AggregationExecutor")
{
    private readonly List<FileStats> _messages = [];

    public override async ValueTask HandleAsync(FileStats message, IWorkflowContext context, CancellationToken cancellationToken = default)
    {
        this._messages.Add(message);

        if (this._messages.Count == 2)
        {
            // Aggregate the results from both executors
            var totalParagraphCount = this._messages.Sum(m => m.ParagraphCount);
            var totalWordCount = this._messages.Sum(m => m.WordCount);
            await context.YieldOutputAsync($"Total Paragraphs: {totalParagraphCount}, Total Words: {totalWordCount}", cancellationToken);
        }
    }
}
