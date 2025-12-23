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
    private const string WorkflowFileName = "MediaInput.yaml";
    private const string PdfReference = "https://sample-files.com/downloads/documents/pdf/basic-text.pdf";
    private const string ImageReference = "https://sample-files.com/downloads/images/jpg/web_optimized_1200x800_97kb.jpg";

    [Theory]
    [InlineData(ImageReference, "image/jpeg", Skip = "Failing consistently in the agent service api")]
    [InlineData(PdfReference, "application/pdf", Skip = "Not currently supported by agent service api")]
    public async Task ValidateFileUrlAsync(string fileSource, string mediaType)
    {
        this.Output.WriteLine($"File: {ImageReference}");
        await this.ValidateFileAsync(new UriContent(fileSource, mediaType));
    }

    [Theory]
    [InlineData(ImageReference, "image/jpeg")]
    [InlineData(PdfReference, "application/pdf")]
    public async Task ValidateFileDataAsync(string fileSource, string mediaType)
    {
        byte[] fileData = await DownloadFileAsync(fileSource);
        string encodedData = Convert.ToBase64String(fileData);
        string fileUrl = $"data:{mediaType};base64,{encodedData}";
        this.Output.WriteLine($"Content: {fileUrl.Substring(0, 112)}...");
        await this.ValidateFileAsync(new DataContent(fileUrl));
    }

    [Fact(Skip = "Not currently supported by agent service api")]
    public async Task ValidateFileUploadAsync()
    {
        byte[] fileData = await DownloadFileAsync(PdfReference);
        AIProjectClient client = new(this.TestEndpoint, new AzureCliCredential());
        using MemoryStream contentStream = new(fileData);
        OpenAIFileClient fileClient = client.GetProjectOpenAIClient().GetOpenAIFileClient();
        OpenAIFile fileInfo = await fileClient.UploadFileAsync(contentStream, "basic-text.pdf", FileUploadPurpose.Assistants);
        try
        {
            this.Output.WriteLine($"File: {fileInfo.Id}");
            await this.ValidateFileAsync(new HostedFileContent(fileInfo.Id));
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

    private async Task ValidateFileAsync(AIContent fileContent)
    {
        AgentProvider agentProvider = AgentProvider.Create(this.Configuration, AgentProvider.Names.Vision);
        await agentProvider.CreateAgentsAsync().ConfigureAwait(false);

        ChatMessage inputMessage = new(ChatRole.User, [new TextContent("I've provided a file:"), fileContent]);

        DeclarativeWorkflowOptions options = await this.CreateOptionsAsync();
        Workflow workflow = DeclarativeWorkflowBuilder.Build<ChatMessage>(Path.Combine(Environment.CurrentDirectory, "Workflows", WorkflowFileName), options);

        WorkflowHarness harness = new(workflow, runId: Path.GetFileNameWithoutExtension(WorkflowFileName));
        WorkflowEvents workflowEvents = await harness.RunWorkflowAsync(inputMessage).ConfigureAwait(false);
        ConversationUpdateEvent conversationEvent = Assert.Single(workflowEvents.ConversationEvents);
        this.Output.WriteLine("CONVERSATION: " + conversationEvent.ConversationId);
        AgentRunResponseEvent agentResponseEvent = Assert.Single(workflowEvents.AgentResponseEvents);
        this.Output.WriteLine("RESPONSE: " + agentResponseEvent.Response.Text);
        Assert.NotEmpty(agentResponseEvent.Response.Text);
    }
}
