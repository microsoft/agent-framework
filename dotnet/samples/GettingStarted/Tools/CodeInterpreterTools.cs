// Copyright (c) Microsoft. All rights reserved.

using System.Text;
using Azure.AI.Agents.Persistent;
using GettingStarted.Tools.Abstractions;
using GettingStarted.Tools.Extensions;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.AI.Agents;
using OpenAI;
using OpenAI.Files;

#pragma warning disable OPENAI001

namespace GettingStarted.Tools;

public sealed class CodeInterpreterTools(ITestOutputHelper output) : AgentSample(output)
{
    [Theory]
    [InlineData(ChatClientProviders.OpenAIAssistant)]
    [InlineData(ChatClientProviders.AzureAIAgentsPersistent)]
    public async Task RunningWithFileReferenceAsync(ChatClientProviders provider)
    {
        var fileId = await UploadTestFileAsync(provider);

        var chatOptions = new ChatOptions()
        {
            Tools = [new NewHostedCodeInterpreterTool { FileIds = [fileId] }]
        };

        var agentOptions = new ChatClientAgentOptions
        {
            Name = "HelpfulAssistant",
            Instructions = "You are a helpful assistant.",
            // Transformation is required until the abstraction will be added to either SDK provider or M.E.AI and
            // implementations will handle new properties/classes.
            ChatOptions = TransformChatOptions(chatOptions, provider)
        };

        using var chatClient = await base.GetChatClientAsync(provider, agentOptions);

        ChatClientAgent agent = new(chatClient, agentOptions);

        var thread = agent.GetNewThread();

        // Prompt which allows to verify that the data was processed from file correctly and current datetime is returned.
        const string Prompt = "Calculate the total number of items, identify the most frequently puchased item and return the result with today's datetime.";

        var assistantOutput = new StringBuilder();
        var codeInterpreterOutput = new StringBuilder();

        await foreach (var update in agent.RunStreamingAsync(Prompt, thread))
        {
            if (!string.IsNullOrWhiteSpace(update.Text))
            {
                assistantOutput.Append(update.Text);
            }
            else if (update.RawRepresentation is not null)
            {
                ProcessRawRepresentationOutput(update.RawRepresentation, codeInterpreterOutput, provider);
            }
        }

        Console.WriteLine("Assistant Output:");
        Console.WriteLine(assistantOutput.ToString());

        Console.WriteLine("Code interpreter Output:");
        Console.WriteLine(codeInterpreterOutput.ToString());
    }

    #region private

    /// <summary>
    /// This method creates a raw representation of tools from newly proposed abstractions, so underlying SDKs can work with it.
    /// Once the tool abstraction is added to either SDK provider or M.E.AI, this method can be removed.
    /// The logic under each provider case should go to related SDK.
    /// </summary>
    private static ChatOptions TransformChatOptions(ChatOptions chatOptions, ChatClientProviders provider)
    {
        return provider switch
        {
            ChatClientProviders.OpenAIAssistant => chatOptions.ToOpenAIAssistantChatOptions(),
            ChatClientProviders.AzureAIAgentsPersistent => chatOptions.ToAzureAIPersistentAgentChatOptions(),
            _ => chatOptions
        };
    }

    private Task<string> UploadTestFileAsync(ChatClientProviders provider)
    {
        var filePath = Path.GetFullPath(Path.Combine(Environment.CurrentDirectory, "Tools", "Files", "groceries.txt"));
        return UploadFileAsync(filePath, provider);
    }

    private async Task<string> UploadFileAsync(string filePath, ChatClientProviders provider)
    {
        switch (provider)
        {
            case ChatClientProviders.OpenAIAssistant:
                var fileClient = GetOpenAIFileClient();
                OpenAIFile openAIFileInfo = await fileClient.UploadFileAsync(filePath, FileUploadPurpose.Assistants);

                return openAIFileInfo.Id;
            case ChatClientProviders.AzureAIAgentsPersistent:
                PersistentAgentFileInfo persistentAgentFileInfo = await AzureAIPersistentAgentsClient.Files.UploadFileAsync(filePath, PersistentAgentFilePurpose.Agents);

                return persistentAgentFileInfo.Id;

            default:
                throw new NotSupportedException($"Client provider {provider} is not supported.");
        }
    }

    private static void ProcessRawRepresentationOutput(object rawRepresentation, StringBuilder builder, ChatClientProviders provider)
    {
        switch (provider)
        {
            case ChatClientProviders.OpenAIAssistant:
                if (rawRepresentation is OpenAI.Assistants.RunStepDetailsUpdate openAIStepDetailsUpdate)
                {
                    builder.Append(openAIStepDetailsUpdate.CodeInterpreterInput);
                    builder.Append(string.Join(string.Empty, openAIStepDetailsUpdate.CodeInterpreterOutputs.SelectMany(l => l.Logs)));
                }

                break;
            case ChatClientProviders.AzureAIAgentsPersistent:
                if (rawRepresentation is Azure.AI.Agents.Persistent.RunStepDetailsUpdate persistentAgentStepDetailsUpdate)
                {
                    builder.Append(persistentAgentStepDetailsUpdate.CodeInterpreterInput);
                    builder.Append(string.Join(string.Empty, persistentAgentStepDetailsUpdate
                        .CodeInterpreterOutputs
                        .OfType<RunStepDeltaCodeInterpreterLogOutput>().SelectMany(l => l.Logs)));
                }

                break;
        }
    }

    private OpenAIFileClient GetOpenAIFileClient() => OpenAIClient.GetOpenAIFileClient();

    #endregion
}
