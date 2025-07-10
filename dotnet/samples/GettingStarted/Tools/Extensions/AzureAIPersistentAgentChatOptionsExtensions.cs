// Copyright (c) Microsoft. All rights reserved.

using Azure.AI.Agents.Persistent;
using GettingStarted.Tools.Abstractions;
using Microsoft.Extensions.AI;

namespace GettingStarted.Tools.Extensions;

/// <summary>
/// <see cref="ChatOptions"/> conversion for Azure AI Persistent Agent.
/// When abstraction is in place, this logic should go to Azure AI Persistent Agents SDK.
/// </summary>
internal static class AzureAIPersistentAgentChatOptionsExtensions
{
    public static ChatOptions ToAzureAIPersistentAgentChatOptions(this ChatOptions chatOptions)
    {
        var fileIds = new List<string>();

        foreach (var tool in chatOptions.Tools!)
        {
            if (tool is NewHostedCodeInterpreterTool codeInterpreterTool &&
                codeInterpreterTool.FileIds is { Count: > 0 })
            {
                fileIds.AddRange(codeInterpreterTool.FileIds);
            }
        }

        if (fileIds.Count > 0)
        {
            var toolResources = new Azure.AI.Agents.Persistent.ToolResources()
            {
                CodeInterpreter = new Azure.AI.Agents.Persistent.CodeInterpreterToolResource()
            };

            foreach (var fileId in fileIds)
            {
                toolResources.CodeInterpreter.FileIds.Add(fileId);
            }

            var threadAndRunOptions = new ThreadAndRunOptions { ToolResources = toolResources };

            chatOptions.RawRepresentationFactory = (_) => threadAndRunOptions;
        }

        return chatOptions;
    }
}
