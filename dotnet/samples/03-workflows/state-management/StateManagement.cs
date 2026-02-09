// Copyright (c) Microsoft. All rights reserved.
// Description: Share state across workflow steps using shared state scopes.
// Docs: https://learn.microsoft.com/agent-framework/workflows/overview

using Microsoft.Agents.AI.Workflows;

namespace WorkflowSamples.StateManagement;

// <state_management_workflow>
/// <summary>
/// Demonstrates shared states within a workflow.
/// Multiple executors read from and write to shared states for data sharing
/// and coordination. Uses fan-out/fan-in for parallel word and paragraph counting.
/// </summary>
public static class Program
{
    private static async Task Main()
    {
        // Create the executors
        var fileRead = new FileReadExecutor();
        var wordCount = new WordCountingExecutor();
        var paragraphCount = new ParagraphCountingExecutor();
        var aggregate = new AggregationExecutor();

        // Build the workflow with fan-out/fan-in for parallel counting
        var workflow = new WorkflowBuilder(fileRead)
            .AddFanOutEdge(fileRead, [wordCount, paragraphCount])
            .AddFanInEdge([wordCount, paragraphCount], aggregate)
            .WithOutputFrom(aggregate)
            .Build();

        // Execute the workflow
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
// </state_management_workflow>

// <state_management_executors>
internal static class FileContentStateConstants
{
    public const string FileContentStateScope = "FileContentState";
}

internal sealed class FileReadExecutor() : Executor<string, string>("FileReadExecutor")
{
    public override async ValueTask<string> HandleAsync(string message, IWorkflowContext context, CancellationToken cancellationToken = default)
    {
        string fileContent = Resources.Read(message);
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
            var totalParagraphCount = this._messages.Sum(m => m.ParagraphCount);
            var totalWordCount = this._messages.Sum(m => m.WordCount);
            await context.YieldOutputAsync($"Total Paragraphs: {totalParagraphCount}, Total Words: {totalWordCount}", cancellationToken);
        }
    }
}
// </state_management_executors>
