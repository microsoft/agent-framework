// Copyright (c) Microsoft. All rights reserved.

using System;
using System.IO;
using System.Net.Http;
using System.Threading.Tasks;
using Azure.AI.Projects;
using Azure.Identity;
using Microsoft.Agents.AI.Workflows.Declarative.IntegrationTests.Agents;
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
    private const string WorkflowWithConversationFileName = "MediaInputConversation.yaml";
    private const string WorkflowWithAutoSendFileName = "MediaInputAutoSend.yaml";
    private const string ImageReference = "https://sample-files.com/downloads/images/jpg/web_optimized_1200x800_97kb.jpg";
    private const string PdfReference = "https://sample-files.com/downloads/documents/pdf/basic-text.pdf";

    [Theory]
    [InlineData(ImageReference, "image/jpeg", true)]
    [InlineData(ImageReference, "image/jpeg", false)]
    public async Task ValidateFileUrlAsync(string fileSource, string mediaType, bool useConversation)
    {
        // Arrange
        this.Output.WriteLine($"File: {fileSource}");

        // Act & Assert
        await this.ValidateFileAsync(new UriContent(fileSource, mediaType), useConversation);
    }

    // Temporarily disabled
    [Theory]
    [Trait("Category", "IntegrationDisabled")]
    [InlineData(ImageReference, "image/jpeg", true)]
    [InlineData(ImageReference, "image/jpeg", false)]
    public async Task ValidateImageFileDataAsync(string fileSource, string mediaType, bool useConversation)
    {
        // Arrange
        byte[] fileData = await DownloadFileAsync(fileSource);
        string encodedData = Convert.ToBase64String(fileData);
        string fileUrl = $"data:{mediaType};base64,{encodedData}";
        this.Output.WriteLine($"Content: {fileUrl.Substring(0, Math.Min(112, fileUrl.Length))}...");

        // Act & Assert
        await this.ValidateFileAsync(new DataContent(fileUrl), useConversation);
    }

    [Theory]
    [InlineData(PdfReference, "application/pdf", true)]
    [InlineData(PdfReference, "application/pdf", false)]
    public async Task ValidateFileDataAsync(string fileSource, string mediaType, bool useConversation)
    {
        // Arrange
        byte[] fileData = await DownloadFileAsync(fileSource);
        string encodedData = Convert.ToBase64String(fileData);
        string fileUrl = $"data:{mediaType};base64,{encodedData}";
        this.Output.WriteLine($"Content: {fileUrl.Substring(0, Math.Min(112, fileUrl.Length))}...");

        // Act & Assert
        await this.ValidateFileAsync(new DataContent(fileUrl), useConversation);
    }

    // Temporarily disabled
    [Theory]
    [Trait("Category", "IntegrationDisabled")]
    [InlineData(PdfReference, "doc.pdf", true)]
    [InlineData(PdfReference, "doc.pdf", false)]
    public async Task ValidateFileUploadAsync(string fileSource, string documentName, bool useConversation)
    {
        // Arrange
        byte[] fileData = await DownloadFileAsync(fileSource);
        AIProjectClient client = new(this.TestEndpoint, new AzureCliCredential());
        using MemoryStream contentStream = new(fileData);
        OpenAIFileClient fileClient = client.GetProjectOpenAIClient().GetOpenAIFileClient();
        OpenAIFile fileInfo = await fileClient.UploadFileAsync(contentStream, documentName, FileUploadPurpose.Assistants);

        // Act & Assert
        try
        {
            this.Output.WriteLine($"File: {fileInfo.Id}");
            await this.ValidateFileAsync(new HostedFileContent(fileInfo.Id), useConversation);
        }
        finally
        {
            await fileClient.DeleteFileAsync(fileInfo.Id);
        }
    }

    private static async Task<byte[]> DownloadFileAsync(string uri)
    {
        using HttpClient client = new();
        client.DefaultRequestHeaders.UserAgent.ParseAdd("Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/110.0");
        return await client.GetByteArrayAsync(new Uri(uri));
    }

    private async Task ValidateFileAsync(AIContent fileContent, bool useConversation)
    {
        // Act
        AgentProvider agentProvider = AgentProvider.Create(this.Configuration, AgentProvider.Names.Vision);
        await agentProvider.CreateAgentsAsync().ConfigureAwait(false);

        ChatMessage inputMessage =
            new(ChatRole.User,
                [
                    new TextContent("I've provided a file:"),
                    fileContent
                ]);

        string workflowFileName = useConversation ? WorkflowWithConversationFileName : WorkflowWithAutoSendFileName;
        DeclarativeWorkflowOptions options = await this.CreateOptionsAsync();
        Workflow workflow = DeclarativeWorkflowBuilder.Build<ChatMessage>(Path.Combine(Environment.CurrentDirectory, "Workflows", workflowFileName), options);

        WorkflowHarness harness = new(workflow, runId: Path.GetFileNameWithoutExtension(workflowFileName));
        WorkflowEvents workflowEvents = await harness.RunWorkflowAsync(inputMessage).ConfigureAwait(false);

        // Assert
        Assert.Equal(useConversation ? 1 : 2, workflowEvents.ConversationEvents.Count);
        this.Output.WriteLine("CONVERSATION: " + workflowEvents.ConversationEvents[0].ConversationId);
        AgentResponseEvent agentResponseEvent = Assert.Single(workflowEvents.AgentResponseEvents);
        this.Output.WriteLine("RESPONSE: " + agentResponseEvent.Response.Text);
        Assert.NotEmpty(agentResponseEvent.Response.Text);
    }
}
