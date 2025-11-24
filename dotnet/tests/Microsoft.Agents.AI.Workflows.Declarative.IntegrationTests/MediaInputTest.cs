// Copyright (c) Microsoft. All rights reserved.

using System;
using System.IO;
using System.Net.Http;
using System.Threading.Tasks;
using Azure.AI.Projects;
using Azure.Identity;
using Microsoft.Agents.AI.Workflows.Declarative.IntegrationTests.Framework;
using Microsoft.Extensions.AI;
using OpenAI.Files;
using Xunit.Abstractions;

namespace Microsoft.Agents.AI.Workflows.Declarative.IntegrationTests;

/// <summary>
/// Tests execution of workflow created by <see cref="DeclarativeWorkflowBuilder"/>.
/// </summary>
public sealed class MediaInputTest(ITestOutputHelper output) : IntegrationTest(output)
{
    private const string WorkflowFileName = "MediaInput.yaml";
    private const string ImageReference = "https://sample-files.com/downloads/documents/pdf/basic-text.pdf";

    [Fact]
    public async Task ValidateImageUrlAsync()
    {
        this.Output.WriteLine($"Image: {ImageReference}");
        await this.ValidateImageAsync(new UriContent(ImageReference, "image/jpeg"));
    }

    [Fact]
    public async Task ValidateImageDataAsync()
    {
        byte[] imageData = await DownloadFileAsync();
        string encodedData = Convert.ToBase64String(imageData);
        string imageUrl = $"data:image/png;base64,{encodedData}";
        this.Output.WriteLine($"Image: {imageUrl.Substring(0, 112)}...");
        await this.ValidateImageAsync(new DataContent(imageUrl));
    }

    [Fact(Skip = "Not behaving will in git-hub build pipeline")]
    public async Task ValidateImageUploadAsync()
    {
        byte[] imageData = await DownloadFileAsync();
        AIProjectClient client = new(this.TestEndpoint, new AzureCliCredential());
        using MemoryStream contentStream = new(imageData);
        OpenAIFileClient fileClient = client.GetProjectOpenAIClient().GetOpenAIFileClient();
        OpenAIFile fileInfo = await fileClient.UploadFileAsync(contentStream, "basic-text.pdf", FileUploadPurpose.Assistants);
        try
        {
            this.Output.WriteLine($"Image: {fileInfo.Id}");
            await this.ValidateImageAsync(new HostedFileContent(fileInfo.Id));
        }
        finally
        {
            await fileClient.DeleteFileAsync(fileInfo.Id);
        }
    }

    private static async Task<byte[]> DownloadFileAsync()
    {
        using HttpClient client = new();
        client.DefaultRequestHeaders.UserAgent.ParseAdd("Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/110.0");
        return await client.GetByteArrayAsync(new Uri(ImageReference));
    }

    private async Task ValidateImageAsync(AIContent imageContent)
    {
        ChatMessage inputMessage = new(ChatRole.User, [new TextContent("Here is my image:"), imageContent]);

        DeclarativeWorkflowOptions options = await this.CreateOptionsAsync();
        Workflow workflow = DeclarativeWorkflowBuilder.Build<ChatMessage>(Path.Combine(Environment.CurrentDirectory, "Workflows", WorkflowFileName), options);

        WorkflowHarness harness = new(workflow, runId: Path.GetFileNameWithoutExtension(WorkflowFileName));
        WorkflowEvents workflowEvents = await harness.RunWorkflowAsync(inputMessage).ConfigureAwait(false);
        Assert.Single(workflowEvents.ConversationEvents);
        this.Output.WriteLine("CONVERSATION: " + workflowEvents.ConversationEvents[0].ConversationId);
        Assert.Single(workflowEvents.AgentResponseEvents);
        this.Output.WriteLine("RESPONSE: " + workflowEvents.AgentResponseEvents[0].Response.Text);
    }
}
