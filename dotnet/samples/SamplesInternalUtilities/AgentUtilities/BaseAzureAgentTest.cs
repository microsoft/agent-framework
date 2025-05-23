// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Extensions.AI;
using OpenAI.Files;
using System.Collections.ObjectModel;
using System.Diagnostics;
using Xunit.Abstractions;

/// <summary>
/// Base class for samples that demonstrate the usage of agents.
/// </summary>
public abstract class BaseAzureTest(ITestOutputHelper output) : BaseTest(output, redirectSystemConsoleOutput: true)
{
    /// <summary>
    /// Metadata key to indicate the assistant as created for a sample.
    /// </summary>
    protected const string AssistantSampleMetadataKey = "sksample";

    protected override bool ForceOpenAI => false;

    /// <summary>
    /// Metadata to indicate the object was created for a sample.
    /// </summary>
    /// <remarks>
    /// While the samples do attempt delete the objects it creates, it is possible
    /// that some may remain.  This metadata can be used to identify and sample
    /// objects for manual clean-up.
    /// </remarks>
    protected static readonly ReadOnlyDictionary<string, string> SampleMetadata =
        new(new Dictionary<string, string>
        {
            { AssistantSampleMetadataKey, bool.TrueString }
        });

    /// <summary>
    /// Common method to write formatted agent chat content to the console.
    /// </summary>
    protected void WriteAgentChatMessage(ChatMessage message)
    {
        // Include ChatMessage.AuthorName in output, if present.
        string authorExpression = message.Role == ChatRole.User ? string.Empty : $" - {message.AuthorName ?? "*"}";
        // Include TextContent (via ChatMessage.Content), if present.
        string contentExpression = string.IsNullOrWhiteSpace(message.Text) ? string.Empty : message.Text;
        bool isCode = false; //message.Metadata?.ContainsKey(OpenAIAssistantAgent.CodeInterpreterMetadataKey) ?? false;
        string codeMarker = isCode ? "\n  [CODE]\n" : " ";
        Console.WriteLine($"\n# {message.Role}{authorExpression}:{codeMarker}{contentExpression}");

        /* TODO
        // Provide visibility for inner content (that isn't TextContent).
        foreach (KernelContent item in message.Items)
        {
            if (item is AnnotationContent annotation)
            {
                Console.WriteLine($"  [{item.GetType().Name}] {annotation.Label}: File #{annotation.ReferenceId}");
            }
            else if (item is FileReferenceContent fileReference)
            {
                Console.WriteLine($"  [{item.GetType().Name}] File #{fileReference.FileId}");
            }
            else if (item is ImageContent image)
            {
                Console.WriteLine($"  [{item.GetType().Name}] {image.Uri?.ToString() ?? image.DataUri ?? $"{image.Data?.Length} bytes"}");
            }
            else if (item is FunctionCallContent functionCall)
            {
                Console.WriteLine($"  [{item.GetType().Name}] {functionCall.Id}");
            }
            else if (item is FunctionResultContent functionResult)
            {
                Console.WriteLine($"  [{item.GetType().Name}] {functionResult.CallId} - {functionResult.Result?.AsJson() ?? "*"}");
            }
        }

        if (message.Metadata?.TryGetValue("Usage", out object? usage) ?? false)
        {
            if (usage is RunStepTokenUsage assistantUsage)
            {
                WriteUsage(assistantUsage.TotalTokenCount, assistantUsage.InputTokenCount, assistantUsage.OutputTokenCount);
            }
            else if (usage is RunStepCompletionUsage agentUsage)
            {
                WriteUsage(agentUsage.TotalTokens, agentUsage.PromptTokens, agentUsage.CompletionTokens);
            }
            else if (usage is ChatTokenUsage chatUsage)
            {
                WriteUsage(chatUsage.TotalTokenCount, chatUsage.InputTokenCount, chatUsage.OutputTokenCount);
            }
        }

        void WriteUsage(long totalTokens, long inputTokens, long outputTokens)
        {
            Console.WriteLine($"  [Usage] Tokens: {totalTokens}, Input: {inputTokens}, Output: {outputTokens}");
        }
        */
    }

    /* TODO
    protected async Task DownloadResponseContentAsync(OpenAIFileClient client, ChatMessage message)
    {
        foreach (KernelContent item in message.Items)
        {
            if (item is AnnotationContent annotation)
            {
                await this.DownloadFileContentAsync(client, annotation.ReferenceId!);
            }
        }
    }

    protected async Task DownloadResponseImageAsync(OpenAIFileClient client, ChatMessage message)
    {
        foreach (KernelContent item in message.Items)
        {
            if (item is FileReferenceContent fileReference)
            {
                await this.DownloadFileContentAsync(client, fileReference.FileId, launchViewer: true);
            }
        }
    }
    */

    private async Task DownloadFileContentAsync(OpenAIFileClient client, string fileId, bool launchViewer = false)
    {
        OpenAIFile fileInfo = client.GetFile(fileId);
        if (fileInfo.Purpose == FilePurpose.AssistantsOutput)
        {
            string filePath = Path.Combine(Path.GetTempPath(), Path.GetFileName(fileInfo.Filename));
            if (launchViewer)
            {
                filePath = Path.ChangeExtension(filePath, ".png");
            }

            BinaryData content = await client.DownloadFileAsync(fileId);
            File.WriteAllBytes(filePath, content.ToArray());
            Console.WriteLine($"  File #{fileId} saved to: {filePath}");

            if (launchViewer)
            {
                Process.Start(
                    new ProcessStartInfo
                    {
                        FileName = "cmd.exe",
                        Arguments = $"/C start {filePath}"
                    });
            }
        }
    }
}
