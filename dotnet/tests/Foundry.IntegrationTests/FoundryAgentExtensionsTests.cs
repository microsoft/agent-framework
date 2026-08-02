// Copyright (c) Microsoft. All rights reserved.

using System;
using System.IO;
using System.Threading.Tasks;
using AgentConformance.IntegrationTests.Support;
using Azure.AI.Projects;
using Azure.AI.Projects.Agents;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Foundry;
using OpenAI.Files;
using OpenAI.Responses;
using OpenAI.VectorStores;
using Shared.IntegrationTests;

namespace Foundry.IntegrationTests;

/// <summary>
/// Integration tests for the file and vector-store forwarder extensions on
/// <see cref="FoundryAgent"/> declared in <see cref="FoundryAgentExtensions"/>. End-to-end
/// counterparts of the unit tests in
/// <c>FoundryAgentExtensionsTests</c> that exercise the live Foundry project pipeline.
/// </summary>
/// <remarks>
/// Mirrors <see cref="FoundryVersionedAgentCreateTests.CreateAgent_CreatesAgentWithVectorStoresAsync(string)"/>
/// in shape (file upload → vector store creation → FileSearchTool answer → cleanup), but routes
/// every helper call through the new <see cref="FoundryAgent"/> extensions instead of the raw
/// <c>projectOpenAIClient.GetProjectFilesClient()</c> / <c>GetProjectVectorStoresClient()</c>
/// path. Skipped by default for the same reasons as the existing vector-store IT (cost and
/// runtime); flip Skip to run manually after seeding the right Foundry project.
/// </remarks>
public class FoundryAgentExtensionsTests
{
    private readonly AIProjectClient _client = new(
        new Uri(TestConfiguration.GetRequiredValue(TestSettings.AzureAIProjectEndpoint)),
        TestAzureCliCredentials.CreateAzureCliCredential());

    [Fact(Skip = "For manual testing only")]
    public async Task UploadFileAsync_ViaAgentExtension_UploadsToProjectAsync()
    {
        // Arrange — non-versioned Responses Agent (Mode 1) so we do not have to provision a server-side agent.
        var agent = this._client.AsAIAgent(
            model: TestConfiguration.GetRequiredValue(TestSettings.AzureAIModelDeploymentName),
            instructions: "Be helpful.");
        var foundryAgent = this.WrapAsFoundryAgent(agent);

        var filePath = Path.GetTempFileName() + ".txt";
        File.WriteAllText(filePath, "agent-extensions integration test payload");

        OpenAIFile? uploaded = null;
        try
        {
            // Act.
            uploaded = await foundryAgent.UploadFileAsync(filePath, FileUploadPurpose.Assistants);

            // Assert.
            Assert.NotNull(uploaded);
            Assert.False(string.IsNullOrEmpty(uploaded.Id));
            Assert.Equal(Path.GetFileName(filePath), uploaded.Filename);
        }
        finally
        {
            if (uploaded is not null)
            {
                await foundryAgent.DeleteFileAsync(uploaded.Id);
            }

            File.Delete(filePath);
        }
    }

    [Fact(Skip = "For manual testing only")]
    public async Task DeleteFileAsync_ViaAgentExtension_RemovesUploadedFileAsync()
    {
        var agent = this._client.AsAIAgent(
            model: TestConfiguration.GetRequiredValue(TestSettings.AzureAIModelDeploymentName),
            instructions: "Be helpful.");
        var foundryAgent = this.WrapAsFoundryAgent(agent);

        var filePath = Path.GetTempFileName() + ".txt";
        File.WriteAllText(filePath, "delete-me payload");

        try
        {
            var uploaded = await foundryAgent.UploadFileAsync(filePath, FileUploadPurpose.Assistants);

            // Act.
            var result = await foundryAgent.DeleteFileAsync(uploaded.Id);

            // Assert.
            Assert.NotNull(result);
            Assert.Equal(uploaded.Id, result.FileId);
            Assert.True(result.Deleted);
        }
        finally
        {
            File.Delete(filePath);
        }
    }

    [Fact(Skip = "For manual testing only")]
    public async Task CreateVectorStoreAsync_ViaAgentExtension_BuildsStoreAndAnswersFileSearchQuestionAsync()
    {
        // Mirrors CreateAgent_CreatesAgentWithVectorStoresAsync but the upload-then-create-store
        // sequence routes through the FoundryAgent.CreateVectorStoreAsync extension (single call
        // that uploads, creates the store, and polls until ready). The resulting vector store id
        // is then wired to a versioned agent's FileSearch tool and queried for a known value.
        string AgentName = FoundryVersionedAgentFixture.GenerateUniqueAgentName("VectorStoreExtAgent");
        const string AgentInstructions = """
            You are a helpful agent that can help fetch data from files you know about.
            Use the File Search Tool to look up codes for words.
            Do not answer a question unless you can find the answer using the File Search Tool.
            """;

        // Non-versioned helper agent that owns the upload pipeline.
        var helperAgent = this._client.AsAIAgent(
            model: TestConfiguration.GetRequiredValue(TestSettings.AzureAIModelDeploymentName),
            instructions: "Be helpful.");
        var helperFoundryAgent = this.WrapAsFoundryAgent(helperAgent);

        var searchFilePath = Path.GetTempFileName() + "wordcodelookup.txt";
        File.WriteAllText(searchFilePath, "The word 'apple' uses the code 442345, while the word 'banana' uses the code 673457.");

        VectorStore? vectorStore = null;
        FoundryAgent? versionedAgent = null;
        try
        {
            // Act — single agent-level helper call uploads, creates, and waits until ready.
            vectorStore = await helperFoundryAgent.CreateVectorStoreAsync(
                "WordCodeLookup_ExtensionVectorStore",
                new[] { searchFilePath });

            Assert.NotNull(vectorStore);
            Assert.False(string.IsNullOrEmpty(vectorStore.Id));
            Assert.NotEqual(VectorStoreStatus.InProgress, vectorStore.Status);

            // Wire the store id into a versioned agent's FileSearch tool to prove it is actually usable.
            var definition = new DeclarativeAgentDefinition(TestConfiguration.GetRequiredValue(TestSettings.AzureAIModelDeploymentName))
            {
                Instructions = AgentInstructions,
                Tools = { ResponseTool.CreateFileSearchTool(vectorStoreIds: [vectorStore.Id]) },
            };

            var agentVersion = await this._client.AgentAdministrationClient.CreateAgentVersionAsync(
                AgentName,
                new ProjectsAgentVersionCreationOptions(definition));

            versionedAgent = this._client.AsAIAgent(agentVersion);

            // Assert.
            var result = await versionedAgent.RunAsync("Can you give me the documented code for 'banana'?");
            Assert.Contains("673457", result.ToString());
        }
        finally
        {
            if (versionedAgent is not null)
            {
                await this._client.AgentAdministrationClient.DeleteAgentAsync(versionedAgent.Name);
            }

            // Cleanup the vector store via the new extension too.
            if (vectorStore is not null)
            {
                await helperFoundryAgent.DeleteVectorStoreAsync(vectorStore.Id);
            }

            File.Delete(searchFilePath);
        }
    }

    [Fact(Skip = "For manual testing only")]
    public async Task DeleteVectorStoreAsync_ViaAgentExtension_RemovesStoreAsync()
    {
        var agent = this._client.AsAIAgent(
            model: TestConfiguration.GetRequiredValue(TestSettings.AzureAIModelDeploymentName),
            instructions: "Be helpful.");
        var foundryAgent = this.WrapAsFoundryAgent(agent);

        var filePath = Path.GetTempFileName() + ".txt";
        File.WriteAllText(filePath, "delete-store payload");

        VectorStore? vectorStore = null;
        try
        {
            vectorStore = await foundryAgent.CreateVectorStoreAsync(
                "DeleteVectorStore_ExtensionTest",
                new[] { filePath });

            // Act.
            var result = await foundryAgent.DeleteVectorStoreAsync(vectorStore.Id);

            // Assert.
            Assert.NotNull(result);
            Assert.Equal(vectorStore.Id, result.VectorStoreId);
            Assert.True(result.Deleted);
            vectorStore = null;
        }
        finally
        {
            if (vectorStore is not null)
            {
                await foundryAgent.DeleteVectorStoreAsync(vectorStore.Id);
            }

            File.Delete(filePath);
        }
    }

    /// <summary>
    /// Resolves the underlying <see cref="FoundryAgent"/> from an <see cref="AIAgent"/> handle
    /// returned by <c>AIProjectClient.AsAIAgent(model, instructions)</c>. The Mode 1 overload
    /// returns a <see cref="ChatClientAgent"/>; the extension forwarders we test live on
    /// <see cref="FoundryAgent"/>, so callers wanting them through this entry point need to
    /// reach for the FoundryAgent constructor instead. This helper makes the test setup
    /// consistent across the four IT scenarios.
    /// </summary>
    private FoundryAgent WrapAsFoundryAgent(AIAgent agent)
    {
        // The Mode 1 AsAIAgent overload returns ChatClientAgent rather than FoundryAgent; use
        // the FoundryAgent projectEndpoint+model+instructions ctor to get the same underlying
        // FoundryChatClient surfaced through a FoundryAgent typed handle.
        _ = agent;
        return new FoundryAgent(
            projectEndpoint: new Uri(TestConfiguration.GetRequiredValue(TestSettings.AzureAIProjectEndpoint)),
            credential: TestAzureCliCredentials.CreateAzureCliCredential(),
            model: TestConfiguration.GetRequiredValue(TestSettings.AzureAIModelDeploymentName),
            instructions: "Be helpful.");
    }
}
