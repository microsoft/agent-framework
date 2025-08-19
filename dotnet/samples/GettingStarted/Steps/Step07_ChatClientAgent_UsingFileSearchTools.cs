// Copyright (c) Microsoft. All rights reserved.

using System.Text;
using Azure.AI.Agents.Persistent;
using Azure.Identity;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.AI.Agents;
using Microsoft.Shared.Samples;
using OpenAI.Files;
using OpenAI.VectorStores;

namespace Steps;

/// <summary>
/// Demonstrates how to use <see cref="ChatClientAgent"/> with file search tools and file references.
/// Shows uploading files to different providers and using them with file search capabilities to retrieve and analyze information from documents.
/// </summary>
public sealed class Step07_ChatClientAgent_UsingFileSearchTools(ITestOutputHelper output) : AgentSample(output)
{
    [Theory]
    [InlineData(ChatClientProviders.AzureAIAgentsPersistent)]
    [InlineData(ChatClientProviders.OpenAIAssistant)]
    public async Task RunningWithFileReferenceAsync(ChatClientProviders provider)
    {
        // Upload a file to the specified provider.
        var fileId = await UploadFileAsync("Resources/employees.pdf", provider);

        // Create a vector store for the uploaded file to enable file search capabilities.
        var vectorStoreId = await CreateVectorStoreAsync([fileId], provider);

        // Create a file search tool that can access the vector store.
        var fileSearchTool = new HostedFileSearchTool()
        {
            Inputs = [new HostedVectorStoreContent(vectorStoreId)],
        };

        var agentOptions = new ChatClientAgentOptions
        {
            Name = "FileSearchAssistant",
            Instructions = "You are a helpful assistant that can search through uploaded documents to answer questions. Use the file search tool to find relevant information from the uploaded files.",
            ChatOptions = new() { Tools = [fileSearchTool] }
        };

        // Create the server-side agent Id when applicable (depending on the provider).
        agentOptions.Id = await base.AgentCreateAsync(provider, agentOptions);

        using var chatClient = base.GetChatClient(provider, agentOptions);

        ChatClientAgent agent = new(chatClient, agentOptions);

        var thread = agent.GetNewThread();

        // Prompt which allows to verify that the file search functionality works correctly with the uploaded document.
        const string Prompt = "Who is the youngest employee?";

        var assistantOutput = new StringBuilder();

        await foreach (var update in agent.RunStreamingAsync(Prompt, thread))
        {
            if (!string.IsNullOrWhiteSpace(update.Text))
            {
                assistantOutput.Append(update.Text);
            }
        }

        Console.WriteLine("Assistant Output:");
        Console.WriteLine(assistantOutput.ToString());

        // Clean up the server-side agent after use when applicable (depending on the provider).
        await base.AgentCleanUpAsync(provider, agent, thread);
    }

    #region private

    /// <summary>
    /// Uploads a file to the specified chat client provider and returns the file ID.
    /// </summary>
    /// <param name="filePath">Path to the file to be uploaded.</param>
    /// <param name="provider">The chat client provider to use for uploading the file.</param>
    /// <returns>The ID of the uploaded file.</returns>
    /// <exception cref="NotSupportedException"></exception>
    private async Task<string> UploadFileAsync(string filePath, ChatClientProviders provider)
    {
        switch (provider)
        {
            case ChatClientProviders.OpenAIAssistant:
                var fileClient = new OpenAIFileClient(TestConfiguration.OpenAI.ApiKey);
                OpenAIFile openAIFileInfo = await fileClient.UploadFileAsync(filePath, FileUploadPurpose.Assistants);

                return openAIFileInfo.Id;
            case ChatClientProviders.AzureAIAgentsPersistent:
                var persistentAgentsClient = new PersistentAgentsClient(TestConfiguration.AzureAI.Endpoint, new AzureCliCredential());
                PersistentAgentFileInfo persistentAgentFileInfo = await persistentAgentsClient.Files.UploadFileAsync(filePath, PersistentAgentFilePurpose.Agents);

                return persistentAgentFileInfo.Id;

            default:
                throw new NotSupportedException($"Client provider {provider} is not supported.");
        }
    }

    private Task<string> CreateVectorStoreAsync(IEnumerable<string> fileIds, ChatClientProviders provider)
        => provider switch
        {
            ChatClientProviders.OpenAIAssistant => CreateVectorStoreOpenAIAssistantAsync(fileIds),
            ChatClientProviders.AzureAIAgentsPersistent => CreateVectorStoreAzureAIAgentsPersistentAsync(fileIds),
            _ => throw new NotSupportedException($"Client provider {provider} is not supported."),
        };

    private async Task<string> CreateVectorStoreOpenAIAssistantAsync(IEnumerable<string> fileIds)
    {
        var vectorStoreClient = new VectorStoreClient(TestConfiguration.OpenAI.ApiKey);
        VectorStoreCreationOptions options = new();
        foreach (var fileId in fileIds)
        {
            options.FileIds.Add(fileId);
        }

        var vectorStore = await vectorStoreClient.CreateVectorStoreAsync(waitUntilCompleted: true, options);
        return vectorStore.VectorStoreId;
    }

    private async Task<string> CreateVectorStoreAzureAIAgentsPersistentAsync(IEnumerable<string> fileIds)
    {
        var client = new PersistentAgentsClient(TestConfiguration.AzureAI.Endpoint, new AzureCliCredential());
        var vectorStore = await client.VectorStores.CreateVectorStoreAsync(fileIds);
        return vectorStore.Value.Id;
    }

    #endregion
}
