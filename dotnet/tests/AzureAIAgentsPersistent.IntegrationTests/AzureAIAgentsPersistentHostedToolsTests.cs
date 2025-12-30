// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Threading.Tasks;
using AgentConformance.IntegrationTests;
using AgentConformance.IntegrationTests.Support;
using Azure.AI.Agents.Persistent;
using Azure.Identity;
using Microsoft.Extensions.AI;
using Shared.IntegrationTests;

namespace AzureAIAgentsPersistent.IntegrationTests;

public sealed class AzureAIAgentsPersistentHostedToolsTests() : AgentTests<AzureAIAgentsPersistentFixture>(() => new())
{
    private static readonly AzureAIConfiguration s_config = TestConfiguration.LoadSection<AzureAIConfiguration>();

    // Agents with Foundry Classic Agents don't give Code Interpreter Results back
    // Being tracked in issue https://github.com/microsoft/agent-framework/issues/2877
    [Fact(Skip = "Currently not working as expected")]
    public async Task CreateAIAgentAsync_WithCodeInterpreterTool_RenderResultsAsync()
    {
        // Arrange
        const string AgentName = "CodeInterpreterAgent";
        const string AgentInstructions = "You are an AI agent with code interpretation capabilities. Use the code interpreter tool to process data and generate insights.";

        var agent = await this.Fixture.CreateChatClientAgentAsync(
            name: AgentName,
            instructions: AgentInstructions,
            toolDefinitions: [new CodeInterpreterToolDefinition()],
            toolResources: new ToolResources() { CodeInterpreter = new() });

        try
        {
            var response = await agent.RunAsync("Use the python with the code interpreter tool to solve the equation sin(x) + x^2 = 42");

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

        var persistentAgentsClient = new PersistentAgentsClient(s_config.Endpoint, new AzureCliCredential());

        var uploadedAgentFile = persistentAgentsClient.Files.UploadFile(
            filePath: searchFilePath,
            purpose: PersistentAgentFilePurpose.Agents);
        string uploadedFileId = uploadedAgentFile.Value.Id;

        // Create a vector store backing the file search (HostedFileSearchTool requires a vector store id).
        var vectorStoreMetadata = await persistentAgentsClient.VectorStores.CreateVectorStoreAsync(
            [uploadedFileId],
            name: "WordCodeLookup_VectorStore");
        string vectorStoreId = vectorStoreMetadata.Value.Id;

        // Wait for vector store indexing to complete before using it
        await WaitForVectorStoreReadyAsync(persistentAgentsClient, vectorStoreId);

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
            await persistentAgentsClient.VectorStores.DeleteVectorStoreAsync(vectorStoreId);
            await persistentAgentsClient.Files.DeleteFileAsync(uploadedFileId);
            File.Delete(searchFilePath);
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

    // Due to a small bug in the ChatClient, annotations are only provided when there's a file id associated, the bug was corrected in the commit below but needs to be released.
    // https://github.com/Azure/azure-sdk-for-net/pull/54496/commits/d72f0b689e17d1b3d5cbaea20f77ea8ecbe4de0d
    [Fact(Skip = "Search tool disabled temporarily")]
    public async Task CreateAIAgentAsync_WithWebSearchTool_PerformsWebSearchAsync()
    {
        // Arrange
        const string Name = "WebSearchAgent";
        const string Instructions = "Use the bing grounding tool to answer questions.";

        var webSearchTool = this.Fixture.GetWebSearchTool();

        var agent = await this.Fixture.CreateChatClientAgentAsync(name: Name, instructions: Instructions, toolDefinitions: [webSearchTool], toolResources: null);
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

    /// <summary>
    /// Waits for a vector store to complete indexing by polling its status.
    /// </summary>
    /// <param name="client">The persistent agents client.</param>
    /// <param name="vectorStoreId">The ID of the vector store.</param>
    /// <param name="maxWaitSeconds">Maximum time to wait in seconds (default: 30).</param>
    /// <returns>A task that completes when the vector store is ready or throws on timeout/failure.</returns>
    private static async Task WaitForVectorStoreReadyAsync(
        PersistentAgentsClient client,
        string vectorStoreId,
        int maxWaitSeconds = 30)
    {
        Stopwatch sw = Stopwatch.StartNew();
        while (sw.Elapsed.TotalSeconds < maxWaitSeconds)
        {
            PersistentAgentsVectorStore vectorStore = await client.VectorStores.GetVectorStoreAsync(vectorStoreId);

            if (vectorStore.Status == VectorStoreStatus.Completed)
            {
                if (vectorStore.FileCounts.Failed > 0)
                {
                    throw new InvalidOperationException("Vector store indexing failed for some files");
                }

                return;
            }

            if (vectorStore.Status == VectorStoreStatus.Expired)
            {
                throw new InvalidOperationException("Vector store has expired");
            }

            await Task.Delay(1000);
        }

        throw new TimeoutException($"Vector store did not complete indexing within {maxWaitSeconds}s");
    }
}
