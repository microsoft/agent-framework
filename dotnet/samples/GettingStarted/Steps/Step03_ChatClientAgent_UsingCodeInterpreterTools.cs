// Copyright (c) Microsoft. All rights reserved.

using System.Text;
using Azure.AI.Agents.Persistent;
using Azure.Identity;
using Microsoft.Extensions.AI.Agents;
using Microsoft.Shared.Samples;
using OpenAI.Assistants;
using OpenAI.Files;

namespace Steps;

/// <summary>
/// Demonstrates how to use <see cref="ChatClientAgent"/> with code interpreter tools and file references.
/// Shows uploading files to different providers and using them with code interpreter capabilities to analyze data and generate responses.
/// </summary>
public sealed class Step03_ChatClientAgent_UsingCodeInterpreterTools(ITestOutputHelper output) : AgentSample(output)
{
    [Theory]
    [InlineData(ChatClientProviders.AzureAIAgentsPersistent)]
    [InlineData(ChatClientProviders.OpenAIAssistant)]
    public async Task RunningWithFileReferenceAsync(ChatClientProviders provider)
    {
        var codeInterpreterTool = new NewHostedCodeInterpreterTool();
        codeInterpreterTool.FileIds.Add(await UploadFileAsync("Resources/groceries.txt", provider));

        var agentOptions = new ChatClientAgentOptions(
            name: "HelpfulAssistant",
            instructions: "You are a helpful assistant.",
            tools: [codeInterpreterTool]);

        // Create the server-side agent Id when applicable (depending on the provider).
        agentOptions.Id = await base.AgentCreateAsync(provider, agentOptions);

        using var chatClient = base.GetChatClient(provider, agentOptions);

        ChatClientAgent agent = new(chatClient, agentOptions);

        var thread = agent.GetNewThread();

        // Prompt which allows to verify that the data was processed from file correctly and current datetime is returned.
        const string Prompt = "Calculate the total number of items, identify the most frequently purchased item and return the result with today's datetime.";

        var assistantOutput = new StringBuilder();
        var codeInterpreterOutput = new StringBuilder();

        await foreach (var update in agent.RunStreamingAsync(Prompt, thread))
        {
            if (!string.IsNullOrWhiteSpace(update.Text))
            {
                assistantOutput.Append(update.Text);
            }

            if (update.RawRepresentation is not null)
            {
                codeInterpreterOutput.Append(GetCodeInterpreterOutput(update.RawRepresentation, provider));
            }
        }

        Console.WriteLine("Assistant Output:");
        Console.WriteLine(assistantOutput.ToString());

        Console.WriteLine("Code interpreter Output:");
        Console.WriteLine(codeInterpreterOutput.ToString());

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

    /// <summary>
    /// Depending on the provider, different strategies are used to extract the code interpreter output from the response raw representation.
    /// </summary>
    /// <param name="rawRepresentation">Raw representation of the response containing code interpreter output.</param>
    /// <param name="provider">Provider of the chat client that is used to determine how to extract the output.</param>
    /// <returns>The code interpreter output as a string.</returns>
    private static string? GetCodeInterpreterOutput(object rawRepresentation, ChatClientProviders provider)
    {
        switch (provider)
        {
            case ChatClientProviders.OpenAIAssistant
                when rawRepresentation is OpenAI.Assistants.RunStepDetailsUpdate stepDetails:
                return $"{stepDetails.CodeInterpreterInput}{string.Join(
                        string.Empty,
                        stepDetails.CodeInterpreterOutputs.SelectMany(l => l.Logs)
                        )}";

            case ChatClientProviders.AzureAIAgentsPersistent
                when rawRepresentation is Azure.AI.Agents.Persistent.RunStepDetailsUpdate stepDetails:
                return $"{stepDetails.CodeInterpreterInput}{string.Join(
                    string.Empty,
                    stepDetails.CodeInterpreterOutputs.OfType<RunStepDeltaCodeInterpreterLogOutput>().SelectMany(l => l.Logs)
                    )}";
        }

        return null;
    }

    #endregion
}
