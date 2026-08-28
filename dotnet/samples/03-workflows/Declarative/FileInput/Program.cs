// Copyright (c) Microsoft. All rights reserved.

using Azure.AI.Projects;
using Azure.AI.Projects.Agents;
using Azure.Identity;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.Configuration;
using OpenAI.Files;
using Shared.Foundry;
using Shared.Workflows;

namespace Demo.Workflows.Declarative.FileInput;

/// <summary>
/// Demonstrate how to provide file-based input to a declarative workflow.
/// </summary>
/// <remarks>
/// See the README.md file in this folder and the parent folder (../README.md) for
/// detailed information about the configuration required to run this sample.
/// </remarks>
internal sealed class Program
{
    public static async Task Main()
    {
        // Initialize configuration
        IConfiguration configuration = Application.InitializeConfig();
        Uri foundryEndpoint = new(configuration.GetValue(Application.Settings.FoundryEndpoint));

        // Ensure sample agents exist in Foundry.
        await CreateAgentAsync(foundryEndpoint, configuration);

        string filePath = Path.Combine(AppContext.BaseDirectory, "ProductBrief.txt");
        await using UploadedFile uploadedFile = await UploadInputFileAsync(foundryEndpoint, filePath);

        // Create the workflow factory. This class demonstrates how to initialize a
        // declarative workflow from a YAML file. Once the workflow is created, it
        // can be executed just like any regular workflow.
        WorkflowFactory workflowFactory = new("FileInput.yaml", foundryEndpoint);

        // Execute the workflow with a ChatMessage that contains both text and an uploaded
        // file reference. Agent-backed actions can use the same workflow conversation to
        // access the file.
        WorkflowRunner runner = new();
        await runner.ExecuteAsync(workflowFactory.CreateWorkflow, CreateInputMessage(uploadedFile.FileId));
    }

    private static async Task CreateAgentAsync(Uri foundryEndpoint, IConfiguration configuration)
    {
        // WARNING: DefaultAzureCredential is convenient for development but requires careful consideration in production.
        // In production, consider using a specific credential (e.g., ManagedIdentityCredential) to avoid
        // latency issues, unintended credential probing, and potential security risks from fallback mechanisms.
        AIProjectClient aiProjectClient = new(foundryEndpoint, new DefaultAzureCredential());

        await aiProjectClient.CreateAgentAsync(
            agentName: "FileInputAgent",
            agentDefinition: DefineFileInputAgent(configuration),
            agentDescription: "Summarizes files provided as declarative workflow input.");
    }

    private static DeclarativeAgentDefinition DefineFileInputAgent(IConfiguration configuration) =>
        new(configuration.GetValue(Application.Settings.FoundryModel))
        {
            Instructions =
                """
                You summarize files that are provided as user input to a workflow.

                When a file is attached, inspect the file content and provide:
                - A short summary
                - Important facts or entities
                - One suggested follow-up question

                If no file content is available, explain that you did not receive a file.
                """
        };

    private static async Task<UploadedFile> UploadInputFileAsync(Uri foundryEndpoint, string filePath)
    {
        // WARNING: DefaultAzureCredential is convenient for development but requires careful consideration in production.
        // In production, consider using a specific credential (e.g., ManagedIdentityCredential) to avoid
        // latency issues, unintended credential probing, and potential security risks from fallback mechanisms.
        AIProjectClient aiProjectClient = new(foundryEndpoint, new DefaultAzureCredential());
        OpenAIFileClient fileClient = aiProjectClient.GetProjectOpenAIClient().GetOpenAIFileClient();

        using FileStream fileStream = File.OpenRead(filePath);
        OpenAIFile openAIFile = await fileClient.UploadFileAsync(
            fileStream,
            Path.GetFileName(filePath),
            FileUploadPurpose.Assistants).ConfigureAwait(false);

        Console.ForegroundColor = ConsoleColor.Cyan;
        try
        {
            Console.WriteLine($"FILE: {openAIFile.Id}");
        }
        finally
        {
            Console.ResetColor();
        }

        return new UploadedFile(fileClient, openAIFile.Id);
    }

    private static ChatMessage CreateInputMessage(string fileId)
    {
        return new ChatMessage(
            ChatRole.User,
            [
                new TextContent("Summarize the attached file for a launch announcement. File name: ProductBrief.txt"),
                new HostedFileContent(fileId),
            ]);
    }

    private sealed record UploadedFile(OpenAIFileClient FileClient, string FileId) : IAsyncDisposable
    {
        public async ValueTask DisposeAsync()
        {
            try
            {
                await this.FileClient.DeleteFileAsync(this.FileId).ConfigureAwait(false);
            }
            catch (Exception ex)
            {
                Console.Error.WriteLine($"Unable to delete uploaded file {this.FileId}: {ex.Message}");
            }
        }
    }
}
