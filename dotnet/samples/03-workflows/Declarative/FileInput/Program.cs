// Copyright (c) Microsoft. All rights reserved.

using Azure.AI.Projects;
using Azure.AI.Projects.Agents;
using Azure.Identity;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.Configuration;
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
    public static async Task Main(string[] args)
    {
        // Initialize configuration
        IConfiguration configuration = Application.InitializeConfig();
        Uri foundryEndpoint = new(configuration.GetValue(Application.Settings.FoundryEndpoint));

        // Ensure sample agents exist in Foundry.
        await CreateAgentAsync(foundryEndpoint, configuration);

        FileWorkflowInput workflowInput = ParseWorkflowInput(args);

        // Create the workflow factory. This class demonstrates how to initialize a
        // declarative workflow from a YAML file. Once the workflow is created, it
        // can be executed just like any regular workflow.
        WorkflowFactory workflowFactory = new("FileInput.yaml", foundryEndpoint);

        // Execute the workflow with a ChatMessage that contains both text and file content.
        // The workflow can inspect the message through System.LastMessage and forward it
        // to agent-backed actions.
        WorkflowRunner runner = new();
        await runner.ExecuteAsync(workflowFactory.CreateWorkflow, CreateInputMessage(workflowInput));
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

    private static FileWorkflowInput ParseWorkflowInput(string[] args)
    {
        string filePath = args.FirstOrDefault() ?? Path.Combine(AppContext.BaseDirectory, "ProductBrief.txt");
        if (!Path.IsPathFullyQualified(filePath))
        {
            filePath = Path.GetFullPath(filePath);
        }

        if (!File.Exists(filePath))
        {
            throw new FileNotFoundException($"Unable to locate input file: {filePath}", filePath);
        }

        string prompt =
            args.Length > 1 ?
                string.Join(' ', args.Skip(1)) :
                "Summarize the attached file for a launch announcement.";

        return new FileWorkflowInput(filePath, prompt);
    }

    private static ChatMessage CreateInputMessage(FileWorkflowInput input)
    {
        string fileName = Path.GetFileName(input.FilePath);
        string mediaType = InferMediaType(input.FilePath);
        byte[] fileBytes = File.ReadAllBytes(input.FilePath);
        string fileDataUri = $"data:{mediaType};base64,{Convert.ToBase64String(fileBytes)}";

        return new ChatMessage(
            ChatRole.User,
            [
                new TextContent($"{input.Prompt} File name: {fileName}"),
                new DataContent(fileDataUri)
                {
                    Name = fileName,
                },
            ]);
    }

    private static string InferMediaType(string filePath)
    {
        string extension = Path.GetExtension(filePath);
        return extension.ToUpperInvariant() switch
        {
            ".CSV" => "text/csv",
            ".GIF" => "image/gif",
            ".HTML" or ".HTM" => "text/html",
            ".JPEG" or ".JPG" => "image/jpeg",
            ".JSON" => "application/json",
            ".MD" => "text/markdown",
            ".PDF" => "application/pdf",
            ".PNG" => "image/png",
            ".TXT" => "text/plain",
            ".WEBP" => "image/webp",
            ".XML" => "application/xml",
            _ => "application/octet-stream",
        };
    }

    private sealed record FileWorkflowInput(string FilePath, string Prompt);
}
