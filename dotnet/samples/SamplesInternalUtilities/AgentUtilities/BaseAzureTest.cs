// Copyright (c) Microsoft. All rights reserved.

using Azure.AI.Agents.Persistent;
using Azure.Identity;
using Microsoft.Agents.AzureAI;
using System.Diagnostics;
using Xunit.Abstractions;

/// <summary>
/// Base class for samples that demonstrate the usage of <see cref="AzureAIAgent"/>.
/// </summary>
public abstract class BaseAzureAgentTest : BaseAgentsTest<PersistentAgentsClient>
{
    protected BaseAzureAgentTest(ITestOutputHelper output) : base(output)
    {
        this.Client = AzureAIAgent.CreateAgentsClient(TestConfiguration.AzureAI.Endpoint, new AzureCliCredential());
    }

    protected override PersistentAgentsClient Client { get; }

    /* TODO
    protected async Task DownloadContentAsync(ChatMessage message)
    {
        foreach (KernelContent item in message.Items)
        {
            if (item is AnnotationContent annotation)
            {
                await this.DownloadFileAsync(annotation.ReferenceId!);
            }
        }
    }
    */

    protected async Task DownloadFileAsync(string fileId, bool launchViewer = false)
    {
        PersistentAgentFileInfo fileInfo = this.Client.Files.GetFile(fileId);
        if (fileInfo.Purpose == PersistentAgentFilePurpose.AgentsOutput)
        {
            string filePath = Path.Combine(Path.GetTempPath(), Path.GetFileName(fileInfo.Filename));
            if (launchViewer)
            {
                filePath = Path.ChangeExtension(filePath, ".png");
            }

            BinaryData content = await this.Client.Files.GetFileContentAsync(fileId);
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
