// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Threading.Tasks;
using AgentConformance.IntegrationTests;
using Azure.AI.Projects;
using Microsoft.Extensions.AI;
using OpenAI.Files;
using OpenAI.VectorStores;

namespace AzureAI.IntegrationTests;

public sealed class AIProjectClientAgentHostedToolsTests() : AgentTests<AIProjectClientFixture>(() => new())
{
    [Fact]
    public async Task CreateAIAgentAsync_WithCodeInterpreterTool_RenderResultsAsync()
    {
        // Arrange
        const string AgentName = "CodeInterpreterAgent";
        const string AgentInstructions = "You are an AI agent with code interpretation capabilities. Use the code interpreter tool to process data and generate insights.";

        var agent = await this.Fixture.CreateChatClientAgentAsync(name: AgentName, instructions: AgentInstructions, aiTools: [new HostedCodeInterpreterTool() { Inputs = [] }]);

        try
        {
            var response = await agent.RunAsync("I need to solve the equation sin(x) + x^2 = 42");

            // Get the CodeInterpreterToolCallContent
            var toolCallContent = response.Messages.SelectMany(m => m.Contents).OfType<CodeInterpreterToolCallContent>().FirstOrDefault();
            Assert.NotNull(toolCallContent);
        }
        finally
        {
            await this.Fixture.DeleteAgentAsync(agent);
        }
    }

    [Fact]
    public async Task CreateAIAgentAsync_WithHostedFileSearchTool_SearchesFilesAsync()
    {
        // Arrange.
        const string Name = "WordCodeLookupAgent";
        const string Instructions = """
            You are a helpful agent that can help fetch data from files you know about.
            Use the File Search Tool to look up codes for words.
            Do not answer a question unless you can find the answer using the File Search Tool.
            """;

        // Create a local file with deterministic content and upload it.
        var searchFilePath = Path.GetTempFileName() + "wordcodelookup.txt";
        File.WriteAllText(
            path: searchFilePath,
            contents: "The word 'apple' uses the code 442345, while the word 'banana' uses the code 673457.");

        var aiProjectClient = this.Fixture.Agent.GetService<AIProjectClient>()!;
        var fileClient = aiProjectClient.GetProjectOpenAIClient().GetProjectFilesClient();

        var uploadResult = await fileClient.UploadFileAsync(searchFilePath, FileUploadPurpose.Assistants);
        string uploadedFileId = uploadResult.Value.Id;

        // Create a vector store backing the file search (HostedFileSearchTool requires a vector store id).
        var vectorStoreClient = aiProjectClient.GetProjectOpenAIClient().GetProjectVectorStoresClient();
        var vectorStoreCreate = await vectorStoreClient.CreateVectorStoreAsync(options: new VectorStoreCreationOptions()
        {
            Name = "WordCodeLookup_VectorStore",
            FileIds = { uploadedFileId }
        });
        string vectorStoreId = vectorStoreCreate.Value.Id;

        // Wait for vector store indexing to complete before using it
        await WaitForVectorStoreReadyAsync(vectorStoreClient, vectorStoreId);

        var fileSearchTool = new HostedFileSearchTool() { Inputs = [new HostedVectorStoreContent(vectorStoreId)] };

        var agent = await this.Fixture.CreateChatClientAgentAsync(name: Name, instructions: Instructions, aiTools: [fileSearchTool]);

        try
        {
            // Act - ask about banana code which must be retrieved via file search.
            var response = await agent.RunAsync("Can you give me the documented code for 'banana'?");
            var text = response.ToString();
            Assert.Contains("673457", text);
        }
        finally
        {
            await this.Fixture.DeleteAgentAsync(agent);
            await vectorStoreClient.DeleteVectorStoreAsync(vectorStoreId);
            await fileClient.DeleteFileAsync(uploadedFileId);
            File.Delete(searchFilePath);
        }
    }

    [Fact]
    public async Task CreateAIAgentAsync_WithWebSearchTool_PerformsWebSearchAsync()
    {
        // Arrange
        const string Name = "WebSearchAgent";
        const string Instructions = "Use the bing grounding tool to answer questions.";

        var webSearchTool = this.Fixture.GetWebSearchTool();

        var agent = await this.Fixture.CreateChatClientAgentAsync(name: Name, instructions: Instructions, aiTools: [webSearchTool]);
        try
        {
            // Act
            var response = await agent.RunAsync("How does wikipedia explain Euler's Identity?");
            var text = response.ToString();

            var annotations = response.Messages
                .SelectMany(m => m.Contents)
                .OfType<TextContent>()
                .Where(c => c.Annotations is { Count: > 0 })
                .SelectMany(c => c.Annotations!);

            Assert.NotEmpty(annotations);
            Assert.NotEmpty(text);
        }
        finally
        {
            await this.Fixture.DeleteAgentAsync(agent);
        }
    }

    [Fact]
    public async Task CreateAIAgentAsync_WithHostedMcpTool_PerformCallsAsync()
    {
        // Arrange
        const string Name = "MicrosoftLearnAgentWithApproval";
        const string Instructions = "You answer questions by searching the Microsoft Learn content only.";
        var mcpTool = new HostedMcpServerTool(
         serverName: "microsoft_learn",
         serverAddress: "https://learn.microsoft.com/api/mcp")
        {
            AllowedTools = ["microsoft_docs_search"],
            ApprovalMode = HostedMcpServerToolApprovalMode.AlwaysRequire
        };

        var agent = await this.Fixture.CreateChatClientAgentAsync(name: Name, instructions: Instructions, aiTools: [mcpTool]);

        try
        {
            var response = await agent.RunAsync("Fetch me a list of available models.");
            Assert.NotEmpty(response.UserInputRequests.OfType<McpServerToolApprovalRequestContent>());
        }
        finally
        {
            await this.Fixture.DeleteAgentAsync(agent);
        }
    }

    /// <summary>
    /// Waits for a vector store to complete indexing by polling its status.
    /// </summary>
    /// <param name="client">The vector store client.</param>
    /// <param name="vectorStoreId">The ID of the vector store.</param>
    /// <param name="maxWaitSeconds">Maximum time to wait in seconds (default: 30).</param>
    /// <returns>A task that completes when the vector store is ready or throws on timeout/failure.</returns>
    private static async Task WaitForVectorStoreReadyAsync(
        VectorStoreClient client,
        string vectorStoreId,
        int maxWaitSeconds = 30)
    {
        Stopwatch sw = Stopwatch.StartNew();
        while (sw.Elapsed.TotalSeconds < maxWaitSeconds)
        {
            VectorStore vectorStore = await client.GetVectorStoreAsync(vectorStoreId);
            VectorStoreStatus status = vectorStore.Status;

            if (status == VectorStoreStatus.Completed)
            {
                if (vectorStore.FileCounts.Failed > 0)
                {
                    throw new InvalidOperationException("Vector store indexing failed for some files");
                }

                return;
            }

            if (status == VectorStoreStatus.Expired)
            {
                throw new InvalidOperationException("Vector store has expired");
            }

            await Task.Delay(1000);
        }

        throw new TimeoutException($"Vector store did not complete indexing within {maxWaitSeconds}s");
    }
}
