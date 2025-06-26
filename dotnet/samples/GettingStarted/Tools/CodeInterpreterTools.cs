// Copyright (c) Microsoft. All rights reserved.

using System.Text;
using GettingStarted.Tools.Abstractions;
using Microsoft.Agents;
using Microsoft.Extensions.AI;
using OpenAI;
using OpenAI.Assistants;
using OpenAI.Files;

#pragma warning disable OPENAI001

namespace GettingStarted.Tools;

public sealed class CodeInterpreterTools(ITestOutputHelper output) : AgentSample(output)
{
    [Theory]
    [InlineData(ChatClientProviders.OpenAIAssistant)]
    public async Task RunningWithFileReferenceAsync(ChatClientProviders provider)
    {
        using var chatClient = await base.GetChatClientAsync(provider);

        var fileId = await UploadTestFileAsync(provider);

        var chatOptions = new ChatOptions()
        {
            Tools = [new NewHostedCodeInterpreterTool { FileIds = [fileId] }]
        };

        ChatClientAgent agent = new(chatClient, new()
        {
            Name = "HelpfulAssistant",
            Instructions = "You are a helpful assistant.",
            // Transformation is required until the abstraction will be added to either SDK provider or M.E.AI and
            // implementations will handle new properties/classes.
            ChatOptions = TransformChatOptions(chatOptions, provider)
        });

        var thread = agent.GetNewThread();

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
        switch (provider)
        {
            case ChatClientProviders.OpenAIAssistant:
                // File references can be added on message attachment level only and not on code interpreter tool definition level.
                // Message attachment content should be non-empty.
                var threadInitializationMessage = new ThreadInitializationMessage(MessageRole.User, [MessageContent.FromText("attachments")]);
                var toolDefinitions = new List<ToolDefinition>();

                foreach (var tool in chatOptions.Tools!)
                {
                    if (tool is NewHostedCodeInterpreterTool codeInterpreterTool)
                    {
                        var codeInterpreterToolDefinition = new CodeInterpreterToolDefinition();
                        toolDefinitions.Add(codeInterpreterToolDefinition);

                        if (codeInterpreterTool.FileIds is { Count: > 0 })
                        {
                            foreach (var fileId in codeInterpreterTool.FileIds)
                            {
                                threadInitializationMessage.Attachments.Add(new(fileId, [codeInterpreterToolDefinition]));
                            }
                        }
                    }
                }

                var runCreationOptions = new RunCreationOptions();

                runCreationOptions.AdditionalMessages.Add(threadInitializationMessage);

                chatOptions.RawRepresentationFactory = (_) => runCreationOptions;

                break;
        }

        return chatOptions;
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

                OpenAIFile fileInfo = await fileClient.UploadFileAsync(filePath, FileUploadPurpose.Assistants);
                return fileInfo.Id;
            default:
                throw new NotSupportedException($"Client provider {provider} is not supported.");
        }
    }

    private static void ProcessRawRepresentationOutput(object rawRepresentation, StringBuilder builder, ChatClientProviders provider)
    {
        switch (provider)
        {
            case ChatClientProviders.OpenAIAssistant:
                if (rawRepresentation is RunStepDetailsUpdate stepUpdate)
                {
                    builder.Append(stepUpdate.CodeInterpreterInput);
                    builder.Append(string.Join("", stepUpdate.CodeInterpreterOutputs.SelectMany(l => l.Logs)));
                }

                break;
            default:
                throw new NotSupportedException($"Client provider {provider} is not supported.");
        }
    }

    private OpenAIFileClient GetOpenAIFileClient()
        => OpenAIClient.GetOpenAIFileClient();

    #endregion
}
