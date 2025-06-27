// Copyright (c) Microsoft. All rights reserved.

using GettingStarted.Tools.Abstractions;
using Microsoft.Extensions.AI;
using OpenAI.Assistants;

#pragma warning disable OPENAI001

namespace GettingStarted.Tools.Extensions;

/// <summary>
/// <see cref="ChatOptions"/> conversion for OpenAI Assistants.
/// When abstraction is in place, this logic should go to OpenAI Assistants SDK.
/// </summary>
internal static class OpenAIAssistantChatOptionsExtensions
{
    public static ChatOptions ToOpenAIAssistantChatOptions(this ChatOptions chatOptions)
    {
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

        return chatOptions;
    }
}
