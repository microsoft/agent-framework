// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using Microsoft.Agents.Workflows;
using Microsoft.Agents.Workflows.Reflection;

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
            .AddFanOutEdge(fileRead, targets: [wordCount, paragraphCount])
            .AddFanInEdge(aggregate, sources: [wordCount, paragraphCount])
            .Build<string>();

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
}

/// <summary>
/// Constants for shared state scopes.
/// </summary>
internal static class FileContentStateConstants
{
    public const string FileContentStateScope = "FileContentState";
}

internal sealed class FileReadExecutor() : ReflectingExecutor<FileReadExecutor>("FileReadExecutor"), IMessageHandler<string, string>
{
    public async ValueTask<string> HandleAsync(string message, IWorkflowContext context)
    {
        // Read file content from embedded resource
        string fileContent = Resources.Read(message);
        // Store file content in a shared state for access by other executors
        string fileID = Guid.NewGuid().ToString();
        await context.QueueStateUpdateAsync(fileID, fileContent, scopeName: FileContentStateConstants.FileContentStateScope);

        return fileID;
    }
}

internal sealed class FileStats
{
    public int ParagraphCount { get; set; }
    public int WordCount { get; set; }
}

internal sealed class WordCountingExecutor() : ReflectingExecutor<WordCountingExecutor>("WordCountingExecutor"), IMessageHandler<string, FileStats>
{
    public async ValueTask<FileStats> HandleAsync(string message, IWorkflowContext context)
    {
        // Retrieve the file content from the shared state
        var fileContent = await context.ReadStateAsync<string>(message, scopeName: FileContentStateConstants.FileContentStateScope)
            ?? throw new InvalidOperationException("File content state not found");

        int wordCount = fileContent.Split([' ', '\n', '\r'], StringSplitOptions.RemoveEmptyEntries).Length;

        return new FileStats { WordCount = wordCount };
    }
}

internal sealed class ParagraphCountingExecutor() : ReflectingExecutor<ParagraphCountingExecutor>("ParagraphCountingExecutor"), IMessageHandler<string, FileStats>
{
    public async ValueTask<FileStats> HandleAsync(string message, IWorkflowContext context)
    {
        // Retrieve the file content from the shared state
        var fileContent = await context.ReadStateAsync<string>(message, scopeName: FileContentStateConstants.FileContentStateScope)
            ?? throw new InvalidOperationException("File content state not found");

        int paragraphCount = fileContent.Split(['\n', '\r'], StringSplitOptions.RemoveEmptyEntries).Length;

        return new FileStats { ParagraphCount = paragraphCount };
    }
}

internal sealed class AggregationExecutor() : ReflectingExecutor<AggregationExecutor>("AggregationExecutor"), IMessageHandler<FileStats>
{
    private readonly List<FileStats> _messages = [];

    public async ValueTask HandleAsync(FileStats message, IWorkflowContext context)
    {
        this._messages.Add(message);

        if (this._messages.Count == 2)
        {
            // Aggregate the results from both executors
            var totalParagraphCount = this._messages.Sum(m => m.ParagraphCount);
            var totalWordCount = this._messages.Sum(m => m.WordCount);
            await context.AddEventAsync(new WorkflowCompletedEvent($"Total Paragraphs: {totalParagraphCount}, Total Words: {totalWordCount}"));
        }
    }
}
